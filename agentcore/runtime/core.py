import os
import logging
import atexit
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from strands_tools import image_reader
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
from typing import Dict, Any
import json
import pathlib
import boto3

BASE_DIR = pathlib.Path(__file__).absolute().parent

# Use root logger to ensure logs appear in CloudWatch
logger = logging.getLogger()
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Global state
bedrock_model = None
mcp_client = None
mcp_tools = None
mcp_client_started = False  # Track if MCP client session is active
catalog_agent = None
order_agent = None
wm_agent = None
image_processor_agent = None
orchestrator_agent = None


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


def load_mcp_tools(tool_filter=None):
    """Load MCP tools from AgentCore Gateway

    Args:
        tool_filter: Optional list of tool name prefixes to filter (e.g., ['PostgreSQLMCPTarget___query'] for PostgreSQL)
    """
    global mcp_tools, mcp_client, mcp_client_started

    # Return cached tools if no filter is specified and we have cached tools
    if mcp_tools is not None and tool_filter is None:
        return mcp_tools

    try:
        # Only initialize MCP client once
        if mcp_client is None or not mcp_client_started:
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
                secrets_client = boto3.client("secretsmanager", region_name=region)
                secret_name = f"agentcore/gateway/{gateway_id}/client-info"
                response = secrets_client.get_secret_value(SecretId=secret_name)
                client_info = json.loads(response["SecretString"])
                logger.info(f"Retrieved client_info from Secrets Manager")
            except Exception as e:
                logger.warning(
                    f"Could not retrieve from Secrets Manager, using config file: {e}"
                )

            # Get access token
            logger.info("Getting access token for MCP gateway...")
            gateway_client = GatewayClient(region_name=region)
            access_token = gateway_client.get_access_token_for_cognito(client_info)
            logger.info("✓ Access token obtained")

            # Setup MCP client and keep it alive globally
            logger.info(f"Connecting to MCP gateway: {gateway_url}")

            # Clean up existing client if present
            if mcp_client is not None and mcp_client_started:
                try:
                    logger.info("Cleaning up existing MCP client session")
                    mcp_client.__exit__(None, None, None)
                    mcp_client_started = False
                except Exception as e:
                    logger.warning(f"Error cleaning up existing MCP client: {e}")

            mcp_client = MCPClient(
                lambda: create_streamable_http_transport(gateway_url, access_token)
            )
            # Start the client - it will stay alive for the lifetime of the application
            mcp_client.__enter__()
            mcp_client_started = True
            logger.info("✓ MCP client connected and active")

        # Get all tools from the MCP client
        if mcp_tools is None:
            all_tools = get_full_tools_list(mcp_client)
            mcp_tools = all_tools
            print(f"✓ Loaded {len(all_tools)} MCP tools: {[tool.tool_name for tool in all_tools]}")
            logger.info(
                f"✓ Loaded {len(all_tools)} MCP tools: {[tool.tool_name for tool in all_tools]}"
            )
        else:
            all_tools = mcp_tools

        # Filter tools if requested
        if tool_filter:
            filtered_tools = [
                tool
                for tool in all_tools
                if any(tool.tool_name.startswith(prefix) for prefix in tool_filter)
            ]
            print(f"✓ Filtered to {len(filtered_tools)} tools: {[tool.tool_name for tool in filtered_tools]}")
            logger.info(
                f"✓ Filtered to {len(filtered_tools)} tools: {[tool.tool_name for tool in filtered_tools]}"
            )
            return filtered_tools
        else:
            return all_tools

    except FileNotFoundError:
        logger.warning(
            "gateway_config.json not found. MCP tools will not be available."
        )
        logger.warning("Run 'python setup_gateway.py' to create the Gateway.")
        return []
    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}")
        import traceback

        traceback.print_exc()
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
    """Initialize the specialized agents"""
    global catalog_agent, order_agent, wm_agent, image_processor_agent, bedrock_model

    if bedrock_model is None:
        bedrock_model = create_bedrock_model()

    # Load custom PostgreSQL tools for product catalog
    postgres_tools = load_mcp_tools(
        tool_filter=[
            "PostgreSQLMCPTarget___search_products_by_product_names",
            "PostgreSQLMCPTarget___list_product_catalogue",
        ]
    )

    # Load custom DynamoDB tools for order management
    order_tools = load_mcp_tools(
        tool_filter=[
            "DynamoDBMCPTarget___place_order",
            "DynamoDBMCPTarget___get_order",
            "DynamoDBMCPTarget___update_order_status",
        ]
    )

    # Load DynamoDB tools for warehouse management and delivery slots
    wm_tools = load_mcp_tools(
        tool_filter=[
            "DynamoDBMCPTarget___scan_table",
            "DynamoDBMCPTarget___query_table",
            "DynamoDBMCPTarget___get_item",
            "DynamoDBMCPTarget___get_customer_postcode",
            "DynamoDBMCPTarget___get_available_delivery_slots",
        ]
    )

    # Import S3 tools from runtime/tools directory
    import sys

    sys.path.insert(0, str(BASE_DIR / "tools"))
    from s3_tools import download_image_from_s3

    # Catalog Agent - searches product catalog with PostgreSQL access
    catalog_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/catalog.md").read_text(),
        tools=postgres_tools,
        model=bedrock_model,
    )

    # Order Agent - handles order placement with custom DynamoDB tools
    order_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/order.md").read_text(),
        tools=order_tools,
        model=bedrock_model,
    )

    # WM Agent - handles warehouse management and delivery scheduling with DynamoDB access
    wm_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/wm.md").read_text(),
        tools=wm_tools,
        model=bedrock_model,
    )

    # Image Processor Agent - extracts grocery lists from images using S3 + image_reader
    image_processor_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/image_processor.md").read_text(),
        tools=[download_image_from_s3, image_reader],
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


@tool
def image_processor_specialist(s3_bucket: str, s3_key: str) -> str:
    """Extract grocery list from image in S3"""
    if image_processor_agent is None:
        initialize_agents()
    prompt = f"Extract the grocery list from the image at s3://{s3_bucket}/{s3_key}"
    response = image_processor_agent(prompt)
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
            tools=[
                catalog_specialist,
                order_specialist,
                wm_specialist,
                image_processor_specialist,
            ],
            model=bedrock_model,
        )

    return orchestrator_agent


def process_grocery_list(payload: dict) -> str:
    """Process a grocery list and return order proposal

    Args:
        payload: Dictionary containing:
            - customer_id: Customer's mobile number
            - action: Action type (PROCESS_IMAGE, TEXT_MESSAGE, etc.)
            - message: User's text message (for TEXT_MESSAGE action)
            - grocery_list: List of items (optional if s3_bucket/s3_key provided)
            - s3_bucket: S3 bucket name (optional, for image processing)
            - s3_key: S3 object key (optional, for image processing)
            - instruction: Additional instruction text (optional)
    """
    try:
        agent = get_orchestrator_agent()

        # Build prompt with customer_id and action-specific content
        customer_id = payload.get("customer_id", "")
        action = payload.get("action", "")
        message = payload.get("message", "")
        grocery_list = payload.get("grocery_list", [])
        s3_bucket = payload.get("s3_bucket")
        s3_key = payload.get("s3_key")
        instruction = payload.get("instruction", "")

        # Build structured prompt
        prompt_parts = []

        if customer_id:
            prompt_parts.append(f"Customer ID: {customer_id}")

        # Handle different action types
        if action == "TEXT_MESSAGE" and message:
            prompt_parts.append(f"User Message: {message}")
            prompt_parts.append("Please process this user input and continue with the order workflow.")
        elif s3_bucket and s3_key:
            prompt_parts.append(f"S3 Bucket: {s3_bucket}")
            prompt_parts.append(f"S3 Key: {s3_key}")
            prompt_parts.append("Please extract the grocery list from the image and create an order proposal.")
        elif grocery_list:
            items_text = "\n".join(grocery_list)
            prompt_parts.append(f"Grocery List:\n{items_text}")
            prompt_parts.append("Please create an order proposal for these items.")
        elif instruction:
            prompt_parts.append(instruction)

        prompt = "\n\n".join(prompt_parts)

        logger.info(f"Sending prompt to orchestrator:\n{prompt}")
        print(f"✓ Orchestrator prompt:\n{prompt}")

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
        "image_processor_ready": image_processor_agent is not None,
        "bedrock_model_ready": bedrock_model is not None,
        "aws_region": os.environ.get("AWS_REGION", "ap-southeast-2"),
    }


def cleanup_mcp_client():
    """Clean up MCP client resources"""
    global mcp_client, mcp_client_started

    try:
        if mcp_client is not None and mcp_client_started:
            logger.info("Cleaning up MCP client session")
            try:
                mcp_client.__exit__(None, None, None)
                logger.info("✓ MCP client session closed")
            except Exception as e:
                logger.error(f"Error closing MCP client session: {e}")
            finally:
                mcp_client_started = False
    except Exception as e:
        logger.error(f"Error during MCP client cleanup: {e}")


# Register cleanup handler
atexit.register(cleanup_mcp_client)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Testing Order Assistant Agents")

    test_items = ["2 Milk", "1 Bread", "12 Eggs", "5 Apples"]
    result = process_grocery_list(test_items)
    logger.info(f"Result: {result}")
