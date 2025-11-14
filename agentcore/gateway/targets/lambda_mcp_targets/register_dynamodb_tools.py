"""
Script to register DynamoDB MCP tools with AgentCore Gateway
Usage: python register_dynamodb_tools.py
"""

import json
import pathlib
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# Load gateway configuration
config_path = pathlib.Path(__file__).parent.parent.parent / "gateway_config.json"
with open(config_path, "r") as f:
    gateway_config = json.load(f)

# Initialize client
region = gateway_config["region"]
gateway_id = gateway_config["gateway_id"]

print(f"🔧 Registering DynamoDB MCP tools with Gateway: {gateway_id}")
print(f"Region: {region}\n")

client = GatewayClient(region_name=region)

# Load tool definitions from tools folder
tools_dir = pathlib.Path(__file__).parent / "dynamodb" / "tools"
tools_list = []

for tool_file in sorted(tools_dir.glob("*.json")):
    with open(tool_file, "r") as f:
        tool_def = json.load(f)
        tools_list.append(tool_def)

tools_config = {"tools": tools_list}

# Get Lambda ARN from CloudFormation outputs
import boto3

cfn = boto3.client("cloudformation", region_name=region)
response = cfn.describe_stacks(StackName="OrderAssistantStack")
outputs = response["Stacks"][0]["Outputs"]
lambda_arn = next(
    o["OutputValue"] for o in outputs if o["OutputKey"] == "DynamoDBMCPLambdaArn"
)

print(f"Lambda ARN: {lambda_arn}\n")

# Get or create the gateway
gateway = {"gatewayId": gateway_id, "gatewayUrl": gateway_config["gateway_url"]}

# Create Lambda target with tool definitions
print("Creating Lambda target with tool definitions...")

# Prepare the target payload with tool schema using inlinePayload
# inlinePayload expects a list of tools, not a JSON string
target_payload = {
    "lambdaArn": lambda_arn,
    "toolSchema": {"inlinePayload": tools_config["tools"]},
}

lambda_target = client.create_mcp_gateway_target(
    gateway=gateway,
    name="DynamoDBMCPTarget",
    target_type="lambda",
    target_payload=target_payload,
    credentials=None,
)

print(f"✅ Lambda target created: {lambda_target.get('targetId', 'N/A')}\n")

# Register each tool
print(f"Registering {len(tools_config['tools'])} tools...\n")
for tool in tools_config["tools"]:
    print(f"  📌 {tool['name']}: {tool['description'][:60]}...")

print("\n" + "=" * 60)
print("✅ All DynamoDB MCP tools registered successfully!")
print("\nAvailable tools:")
for tool in tools_config["tools"]:
    print(f"  • {tool['name']}")
print("\nNext: Use these tools in your AgentCore agent configuration")
print("=" * 60)
