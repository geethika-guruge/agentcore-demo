import os
import logging
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
from typing import Dict, Any
import json
import pathlib
import boto3

BASE_DIR = pathlib.Path(__file__).absolute().parent

logger = logging.getLogger(__name__)

# Global agents
orchestrator_agent = None
catalog_agent = None
order_agent = None
wm_agent = None
bedrock_model = None
mcp_tools = None


def create_streamable_http_transport(mcp_url: str, access_token: str):
    """Create HTTP transport for MCP client"""
    return streamablehttp_client(
        mcp_url, headers={"Authorization": f"Bearer {access_token}"}
    )


def get_full_tools_list(client):
    """Get all tools with pagination support"""
    more_tools = True
    tools = []
    pagination_token = None
    while more_tools:
        tmp_tools = client.list_tools_sync(pagination_token=pagination_token)
        tools.extend(tmp_tools)
        if tmp_tools.pagination_token is None:
            more_tools = False
        else:
            more_tools = True
            pagination_token = tmp_tools.pagination_token
    return tools


def load_mcp_tools():
    """Load DynamoDB MCP tools from AgentCore Gateway"""
    global mcp_tools

    if mcp_tools is not None:
        return mcp_tools

    try:
        # Load gateway configuration
        gateway_config_path = BASE_DIR / "gateway_config.json"
        with open(gateway_config_path, "r") as f:
            config = json.load(f)

        gateway_url = config["gateway_url"]
        gateway_id = config["gateway_id"]
        region = config["region"]

        # Get client_info from Secrets Manager
        client_info = config.get("client_info")
        try:
            secrets_client = boto3.client('secretsmanager', region_name=region)
            secret_name = f"agentcore/gateway/{gateway_id}/client-info"
            response = secrets_client.get_secret_value(SecretId=secret_name)
            client_info = json.loads(response['SecretString'])
            logger.info(f"Retrieved client_info from Secrets Manager")
        except Exception as e:
            logger.warning(f"Could not retrieve from Secrets Manager, using config file: {e}")

        # Get access token
        logger.info("Getting access token for MCP gateway...")
        client = GatewayClient(region_name=region)
        access_token = client.get_access_token_for_cognito(client_info)
        logger.info("✓ Access token obtained")

        # Setup MCP client and get tools
        logger.info(f"Connecting to MCP gateway: {gateway_url}")
        mcp_client = MCPClient(
            lambda: create_streamable_http_transport(gateway_url, access_token)
        )
        mcp_client.start()

        with mcp_client:
            tools = get_full_tools_list(mcp_client.list_tools_sync())
            mcp_tools = tools
            logger.info(
                f"✓ Loaded {len(tools)} MCP tools: {[tool.tool_name for tool in tools]}"
            )
            return tools

    except FileNotFoundError:
        logger.warning(
            "gateway_config.json not found. DynamoDB MCP tools will not be available."
        )
        logger.warning("Run 'python setup_gateway.py' to create the Gateway.")
        return []
    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}")
        return []


def create_bedrock_model() -> BedrockModel:
    """Create a BedrockModel for the agents"""
    region = os.environ.get("AWS_REGION", "ap-southeast-2")
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "apac.anthropic.claude-sonnet-4-20250514-v1:0"
    )

    try:
        logger.info(f"Creating Bedrock model: {model_id}")
        model = BedrockModel(
            model_id=model_id,
            region_name=region,
            temperature=0.1,
            max_tokens=4000,
        )
        logger.info(f"Successfully created Bedrock model")
        return model
    except Exception as e:
        logger.error(f"Failed to create model: {e}")
        raise


def initialize_agents():
    """Initialize the four specialized agents"""
    global catalog_agent, order_agent, wm_agent, bedrock_model

    if bedrock_model is None:
        bedrock_model = create_bedrock_model()

    # Load DynamoDB MCP tools from gateway
    dynamodb_tools = load_mcp_tools()

    # Catalog Agent - searches product catalog with DynamoDB access
    catalog_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/catalog.md").read_text(),
        tools=dynamodb_tools,
        model=bedrock_model,
    )

    # Order Agent - handles order placement with DynamoDB access
    order_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/order.md").read_text(),
        tools=dynamodb_tools,
        model=bedrock_model,
    )

    # WM Agent - handles warehouse management and delivery scheduling with DynamoDB access
    wm_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/wm.md").read_text(),
        tools=dynamodb_tools,
        model=bedrock_model,
    )


@tool
def catalog_specialist(query: str) -> str:
    """Search product catalog and suggest items"""
    if catalog_agent is None:
        initialize_agents()
    response = catalog_agent(query)
    return str(response)


@tool
def order_specialist(order_details: str) -> str:
    """Place order and send confirmation"""
    if order_agent is None:
        initialize_agents()
    response = order_agent(order_details)
    return str(response)


@tool
def wm_specialist(delivery_request: str) -> str:
    """Get available delivery slots from warehouse"""
    if wm_agent is None:
        initialize_agents()
    response = wm_agent(delivery_request)
    return str(response)


def get_orchestrator_agent() -> Agent:
    """Get or create the orchestrator agent"""
    global orchestrator_agent, bedrock_model

    if orchestrator_agent is None:
        if bedrock_model is None:
            bedrock_model = create_bedrock_model()

        initialize_agents()

        orchestrator_agent = Agent(
            system_prompt=(BASE_DIR / "prompts/orchestrator.md").read_text(),
            tools=[catalog_specialist, order_specialist, wm_specialist],
            model=bedrock_model,
        )

    return orchestrator_agent


def process_grocery_list(grocery_items: list) -> str:
    """Process a grocery list and return order proposal"""
    try:
        agent = get_orchestrator_agent()

        items_text = "\n".join(grocery_items)
        prompt = (
            f"Process this grocery list and create an order proposal:\n{items_text}"
        )

        response = agent(prompt)
        return str(response)

    except Exception as e:
        logger.error(f"Error processing grocery list: {e}")
        return f"Error: {str(e)}"


def health_check() -> Dict[str, Any]:
    """Health check for the agent system"""
    return {
        "orchestrator_ready": orchestrator_agent is not None,
        "catalog_ready": catalog_agent is not None,
        "order_ready": order_agent is not None,
        "wm_ready": wm_agent is not None,
        "bedrock_model_ready": bedrock_model is not None,
        "aws_region": os.environ.get("AWS_REGION", "ap-southeast-2"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Testing Order Assistant Agents")

    test_items = ["2 Milk", "1 Bread", "12 Eggs", "5 Apples"]
    result = process_grocery_list(test_items)
    logger.info(f"Result: {result}")
