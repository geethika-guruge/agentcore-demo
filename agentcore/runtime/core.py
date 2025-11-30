import os
import logging
import atexit
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from strands_tools import image_reader
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
from typing import Dict, Any
import json
import pathlib
import boto3
from strands.multiagent import GraphBuilder
import yaml

# OpenTelemetry imports for tracing
from arize.otel import register
from openinference.instrumentation.bedrock import BedrockInstrumentor

BASE_DIR = pathlib.Path(__file__).absolute().parent

# Use root logger to ensure logs appear in CloudWatch
logger = logging.getLogger()
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Load model configuration
MODEL_CONFIG = None
OTEL_CONFIG = None
TRACER_PROVIDER = None
AWS_REGION = None


def get_aws_region() -> str:
    """Get AWS region from session (uses AWS profile configuration)"""
    global AWS_REGION

    if AWS_REGION is not None:
        return AWS_REGION

    session = boto3.Session()
    AWS_REGION = session.region_name
    logger.info(f"Using AWS region from session: {AWS_REGION}")
    return AWS_REGION


def load_model_config() -> Dict[str, Any]:
    """Load model configuration from region-specific YAML file"""
    global MODEL_CONFIG

    if MODEL_CONFIG is not None:
        return MODEL_CONFIG

    region = get_aws_region()

    # Try region-specific config first
    region_config_path = BASE_DIR / f"model_config.{region}.yaml"

    try:
        if region_config_path.exists():
            with open(region_config_path, "r") as f:
                MODEL_CONFIG = yaml.safe_load(f)
            logger.info(f"Loaded region-specific model configuration from {region_config_path}")
            return MODEL_CONFIG
        else:
            logger.error(f"Region-specific model config file not found at {region_config_path}")
            raise FileNotFoundError(f"Model config for region {region} not found. Expected: {region_config_path}")
    except Exception as e:
        logger.error(f"Error loading model config: {e}")
        raise


def load_otel_config() -> Dict[str, Any]:
    """Load OpenTelemetry configuration from YAML file"""
    global OTEL_CONFIG

    if OTEL_CONFIG is not None:
        return OTEL_CONFIG

    # Try multiple possible locations for the config file
    possible_paths = [
        BASE_DIR / ".otel_config.yaml",  # Same directory as core.py (in container)
        pathlib.Path("/app/.otel_config.yaml"),  # Container root
        BASE_DIR.parent.parent / ".otel_config.yaml",  # Project root (local dev)
    ]

    for config_path in possible_paths:
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    OTEL_CONFIG = yaml.safe_load(f)
                print(f"[OTel] Loaded configuration from {config_path}")

                # Validate required fields
                required_fields = ["space_id", "api_key", "project_name"]
                for field in required_fields:
                    if not OTEL_CONFIG.get(field) or OTEL_CONFIG[field].startswith("YOUR_"):
                        print(f"[OTel] WARNING: Config field '{field}' not configured - using placeholder")

                return OTEL_CONFIG
        except Exception as e:
            print(f"[OTel] Error loading config from {config_path}: {e}")
            continue

    print(f"[OTel] Config file not found in any of the expected locations: {[str(p) for p in possible_paths]}")
    print("[OTel] Tracing will be disabled.")
    return None


def initialize_otel_tracing():
    """Initialize OpenTelemetry tracing with Arize"""
    global TRACER_PROVIDER

    if TRACER_PROVIDER is not None:
        return TRACER_PROVIDER

    try:
        config = load_otel_config()

        if not config:
            print("[OTel] Tracing disabled - no configuration found")
            return None

        # Check if config has placeholder values
        if (config.get("space_id", "").startswith("YOUR_") or
            config.get("api_key", "").startswith("YOUR_") or
            config.get("project_name", "").startswith("YOUR_")):
            print("[OTel] Tracing disabled - configuration contains placeholder values")
            return None

        # Register with Arize
        print("[OTel] Initializing tracing with Arize...")
        TRACER_PROVIDER = register(
            space_id=config["space_id"],
            api_key=config["api_key"],
            project_name=config["project_name"],
        )

        # Instrument Bedrock
        BedrockInstrumentor().instrument(tracer_provider=TRACER_PROVIDER)

        print("[OTel] ✓ Tracing initialized successfully")
        print(f"[OTel] ✓ Traces will be sent to Arize project: {config['project_name']}")

        return TRACER_PROVIDER

    except Exception as e:
        print(f"[OTel] ERROR: Failed to initialize tracing: {e}")
        print("[OTel] Continuing without tracing...")
        return None


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
            # Get region from AWS session
            region = get_aws_region()

            # Fetch gateway configuration from SSM Parameter Store
            session = boto3.Session()
            ssm_client = session.client("ssm")

            gateway_id_response = ssm_client.get_parameter(
                Name="/order-assistant/gateway-id"
            )
            gateway_id = gateway_id_response["Parameter"]["Value"]
            logger.info(f"Retrieved gateway_id from SSM: {gateway_id}")

            gateway_url_response = ssm_client.get_parameter(
                Name="/order-assistant/gateway-url"
            )
            gateway_url = gateway_url_response["Parameter"]["Value"]
            logger.info(f"Retrieved gateway_url from SSM: {gateway_url}")

            # Get client_info from Secrets Manager
            secrets_client = session.client("secretsmanager")
            secret_name = f"agentcore/gateway/{gateway_id}/client-info"
            response = secrets_client.get_secret_value(SecretId=secret_name)
            client_info = json.loads(response["SecretString"])
            logger.info(f"Retrieved client_info from Secrets Manager: {secret_name}")

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
            logger.info(f"Loaded {len(all_tools)} MCP tools")
        else:
            all_tools = mcp_tools

        # Filter tools if requested
        if tool_filter:
            filtered_tools = [
                tool
                for tool in all_tools
                if any(tool.tool_name.startswith(prefix) for prefix in tool_filter)
            ]
            logger.info(f"Filtered to {len(filtered_tools)} tools")
            return filtered_tools
        else:
            return all_tools

    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}")
        import traceback

        traceback.print_exc()
        return []


def create_bedrock_model(agent_name: str) -> BedrockModel:
    """Create a BedrockModel for a specific agent

    Args:
        agent_name: Name of the agent (e.g., 'orchestrator', 'catalog', 'order', 'warehouse', 'image_processor')
    """
    config = load_model_config()

    # Get agent-specific config
    if agent_name not in config.get("agents", {}):
        raise ValueError(f"No configuration found for agent '{agent_name}' in model_config.yaml")

    agent_config = config["agents"][agent_name]

    # Read directly from config
    model_id = agent_config.get("model_id")

    # Get region from AWS session
    region = get_aws_region()

    try:
        logger.info(f"Creating Bedrock model for '{agent_name}' agent using model: {model_id}")
        model = BedrockModel(
            model_id=model_id,
            region_name=region,
        )
        logger.info(f"'{agent_name}' agent created with model: {model_id}")
        return model
    except Exception as e:
        logger.error(f"Failed to create model for {agent_name}: {e}")
        raise


def initialize_agents():
    """Initialize the specialized agents with individual model configurations"""
    global catalog_agent, order_agent, wm_agent, image_processor_agent, bedrock_model

    # Initialize OpenTelemetry tracing
    initialize_otel_tracing()

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

    # Create agent-specific models
    logger.info("Initializing agents...")

    catalog_model = create_bedrock_model("catalog")
    order_model = create_bedrock_model("order")
    wm_model = create_bedrock_model("warehouse")
    image_processor_model = create_bedrock_model("image_processor")

    # Catalog Agent - searches product catalog with PostgreSQL access
    catalog_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/catalog.md").read_text(),
        tools=postgres_tools,
        model=catalog_model,
    )
    logger.info("✓ Catalog agent initialized")

    # Order Agent - handles order placement with custom DynamoDB tools
    order_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/order.md").read_text(),
        tools=order_tools,
        model=order_model,
    )
    logger.info("✓ Order agent initialized")

    # WM Agent - handles warehouse management and delivery scheduling with DynamoDB access
    wm_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/wm.md").read_text(),
        tools=wm_tools,
        model=wm_model,
    )
    logger.info("✓ Warehouse agent initialized")

    # Image Processor Agent - extracts grocery lists from images using S3 + image_reader
    image_processor_agent = Agent(
        system_prompt=(BASE_DIR / "prompts/image_processor.md").read_text(),
        tools=[download_image_from_s3, image_reader],
        model=image_processor_model,
    )
    logger.info("✓ Image processor agent initialized")
    logger.info("All agents initialized successfully")


def create_router_agent() -> Agent:
    """Create router agent that routes requests and returns responses to user"""
    router_model = create_bedrock_model("orchestrator")

    router = Agent(
        system_prompt=(BASE_DIR / "prompts/router.md").read_text(),
        model=router_model,
    )
    logger.info("✓ Router (orchestrator) agent initialized")

    return router


def build_order_processing_graph():
    """Build a graph with two workflow paths:

    Path 1 (New Order - Image):
        router (routing) → image_processor → catalog → router (return) [END]
        Router returns catalog options to user

    Path 2 (User Confirmation):
        router (routing) → order → warehouse → router (return) [END]
        Router returns final order confirmation with delivery details to user
    """
    global catalog_agent, order_agent, wm_agent, image_processor_agent

    # Initialize agents first
    if catalog_agent is None:
        initialize_agents()

    # Create router agent
    router = create_router_agent()
    logger.info("Router agent created")

    # Create graph builder
    builder = GraphBuilder()

    # Add all nodes
    builder.add_node(router, "router")
    builder.add_node(image_processor_agent, "image_processor")
    builder.add_node(catalog_agent, "catalog")
    builder.add_node(order_agent, "order")
    builder.add_node(wm_agent, "warehouse")
    logger.info("Graph nodes added")

    # Set entry point
    builder.set_entry_point("router")

    # Path 1: Image flow (router → image_processor → catalog)
    def is_image_request(result):
        """Check if this is an image processing request"""
        # Extract just the router's latest output from GraphState.results
        router_output = ""

        if hasattr(result, 'results') and 'router' in result.results:
            router_result = result.results['router']
            if hasattr(router_result, 'result'):
                agent_result = router_result.result
                if hasattr(agent_result, 'message'):
                    message = agent_result.message
                    # Message is a dict with structure: {'role': 'assistant', 'content': [{'text': '...'}]}
                    if isinstance(message, dict) and 'content' in message and len(message['content']) > 0:
                        router_output = str(message['content'][0].get('text', ''))

        # Fallback to string conversion if extraction failed
        if not router_output:
            router_output = str(result)

        result_str = router_output.lower()
        is_image = "route_to_image" in result_str

        if is_image:
            logger.info("Router routing to image processor (Path 1)")

        return is_image

    builder.add_edge("router", "image_processor", condition=is_image_request)
    builder.add_edge("image_processor", "catalog")
    builder.add_edge("catalog", "router")  # Return to router to relay options to user

    # Path 2: Confirmation flow (router → order → warehouse)
    def is_order_request(result):
        """Check if this is a user confirmation for order placement"""
        # Extract just the router's latest output from GraphState.results
        router_output = ""

        # Extract just the router's latest output from GraphState.results
        if hasattr(result, 'results') and 'router' in result.results:
            router_result = result.results['router']
            if hasattr(router_result, 'result'):
                agent_result = router_result.result
                if hasattr(agent_result, 'message'):
                    message = agent_result.message
                    # Message is a dict with structure: {'role': 'assistant', 'content': [{'text': '...'}]}
                    if isinstance(message, dict) and 'content' in message and len(message['content']) > 0:
                        router_output = str(message['content'][0].get('text', ''))

        # Fallback to string conversion if extraction failed
        if not router_output:
            router_output = str(result)

        result_str = router_output.lower()

        # Router outputs order details with "Selected Option" and "Items to Order"
        # Must NOT contain "route_to_image" to avoid confusion with Path 1
        has_order_keywords = "selected option" in result_str and "items to order" in result_str
        has_total_and_customer = "total amount" in result_str and "customer id" in result_str
        is_not_image_route = "route_to_image" not in result_str

        is_order = (has_order_keywords or has_total_and_customer) and is_not_image_route

        if is_order:
            logger.info("Router routing to order placement (Path 2)")

        return is_order

    builder.add_edge("router", "order", condition=is_order_request)
    builder.add_edge("order", "warehouse")
    builder.add_edge("warehouse", "router")  # Return to router to relay final confirmation to user

    # Set execution limits
    builder.set_execution_timeout(300)  # 5 minutes
    builder.set_max_node_executions(10)  # Prevent infinite loops

    logger.info("Graph built with two workflow paths")
    return builder.build()


def process_grocery_list(payload: dict) -> str:
    """Process a grocery list using graph-based multi-agent system

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
        # Build the graph
        graph = build_order_processing_graph()

        # Build prompt with customer_id and action-specific content
        customer_id = payload.get("customer_id", "")
        action = payload.get("action", "")
        message = payload.get("message", "")
        grocery_list = payload.get("grocery_list", [])
        s3_bucket = payload.get("s3_bucket")
        s3_key = payload.get("s3_key")
        instruction = payload.get("instruction", "")
        catalog_options = payload.get("catalog_options", "")

        # Build minimal structured prompt - let orchestrator decide routing
        prompt_parts = []

        if customer_id:
            prompt_parts.append(f"Customer ID: {customer_id}")

        # Just provide the data - orchestrator will decide what to do
        if action == "TEXT_MESSAGE" and message:
            prompt_parts.append(f"User Message: {message}")
        elif s3_bucket and s3_key:
            prompt_parts.append(f"S3 Bucket: {s3_bucket}")
            prompt_parts.append(f"S3 Key: {s3_key}")
        elif grocery_list:
            items_text = "\n".join(grocery_list)
            prompt_parts.append(f"Grocery List:\n{items_text}")
        elif instruction:
            prompt_parts.append(instruction)

        # Include catalog options if available (for Path 2)
        if catalog_options:
            prompt_parts.append(f"Catalog Options:\n{catalog_options}")

        prompt = "\n\n".join(prompt_parts)

        logger.info(f"Executing graph with prompt:\n{prompt}")

        # Execute the graph
        result = graph(prompt)

        logger.info("Graph execution completed")

        # Extract the router node's message from the result
        try:
            # result is a GraphResult object with results dict
            if hasattr(result, 'results') and 'router' in result.results:
                router_result = result.results['router']
                # Navigate: NodeResult -> result -> message -> content -> text
                if hasattr(router_result, 'result'):
                    agent_result = router_result.result
                    if hasattr(agent_result, 'message'):
                        message = agent_result.message
                        # message is a dict: {'role': 'assistant', 'content': [{'text': '...'}]}
                        if isinstance(message, dict) and 'content' in message:
                            content = message['content']
                            if content and isinstance(content, list) and len(content) > 0:
                                text = content[0].get('text', '')
                                if text:
                                    logger.info(f"Successfully extracted router message ({len(text)} chars)")
                                    return text

            # Fallback if extraction fails
            logger.warning("Could not extract router message, returning string representation")
            return str(result)

        except Exception as e:
            logger.error(f"Error extracting message from result: {e}")
            return str(result)

    except Exception as e:
        logger.error(f"Error processing grocery list: {e}")
        import traceback
        traceback.print_exc()
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
