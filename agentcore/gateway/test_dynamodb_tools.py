#!/usr/bin/env python3
"""
Test script for DynamoDB Custom Tools via AgentCore Gateway
Tests place_order, get_order, and update_order_status tools
"""

import json
import sys
import os
from pathlib import Path

# Add parent directory to path to import gateway client
sys.path.insert(0, str(Path(__file__).parent.parent))

from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# Load gateway configuration
gateway_config_path = Path(__file__).parent.parent / "runtime" / "gateway_config.json"
with open(gateway_config_path, "r") as f:
    config = json.load(f)

gateway_url = config["gateway_url"]
gateway_id = config["gateway_id"]
region = config["region"]
client_info = config.get("client_info")

# Get access token
print("Getting access token for MCP gateway...")
gateway_client = GatewayClient(region_name=region)
access_token = gateway_client.get_access_token_for_cognito(client_info)
print("✓ Access token obtained\n")


def call_tool(tool_name, arguments):
    """Call a tool via the Gateway MCP endpoint"""
    import requests

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    payload = {
        "jsonrpc": "2.0",
        "id": "call-tool-request",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    print(f"Calling tool: {tool_name}")
    print(f"Arguments: {json.dumps(arguments, indent=2)}")

    response = requests.post(gateway_url, headers=headers, json=payload)
    result = response.json()

    print(f"Response: {json.dumps(result, indent=2)}\n")
    return result


def main():
    print("=" * 80)
    print("Testing DynamoDB Custom Tools via AgentCore Gateway")
    print("=" * 80)
    print(f"Gateway URL: {gateway_url}")
    print(f"Gateway ID: {gateway_id}")
    print(f"Region: {region}\n")

    # Test 1: Place Order
    print("1. Testing place_order")
    print("-" * 80)
    order_result = call_tool(
        "DynamoDBMCPTarget___place_order",
        {
            "customer_id": "CUST-TEST-001",
            "items": [
                {
                    "product_name": "Butter (unsalted)",
                    "product_category": "Dairy",
                    "quantity": 2,
                    "price": 75.99
                },
                {
                    "product_name": "Coffee Beans",
                    "product_category": "Beverages",
                    "quantity": 1,
                    "price": 89.99
                }
            ],
            "total_amount": 241.97,            
        }
    )

    # Extract order_id from response
    try:
        # The response is double-encoded: first parse the Lambda response, then parse the body
        lambda_response = json.loads(order_result["result"]["content"][0]["text"])
        order_data = json.loads(lambda_response["body"])
        order_id = order_data.get("order_id")
        print(f"✅ Created Order ID: {order_id}\n")
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to extract order_id: {e}\n")
        print(f"Raw response: {order_result}\n")
        return

    # Test 2: Get Order
    print("2. Testing get_order")
    print("-" * 80)
    get_result = call_tool(
        "DynamoDBMCPTarget___get_order",
        {
            "order_id": order_id
        }
    )

    try:
        lambda_response = json.loads(get_result["result"]["content"][0]["text"])
        order_details = json.loads(lambda_response["body"])
        print(f"✅ Retrieved order: {order_details['order_id']}")
        print(f"   Customer: {order_details['customer_name']}")
        print(f"   Status: {order_details['order_status']}")
        print(f"   Total: ${order_details['total_amount']}\n")
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse order details: {e}\n")

    # Test 3: Update Order Status
    print("3. Testing update_order_status")
    print("-" * 80)
    update_result = call_tool(
        "DynamoDBMCPTarget___update_order_status",
        {
            "order_id": order_id,
            "new_status": "CONFIRMED"
        }
    )

    try:
        lambda_response = json.loads(update_result["result"]["content"][0]["text"])
        updated_order = json.loads(lambda_response["body"])
        print(f"✅ Updated order status: {updated_order['order_status']}\n")
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse update response: {e}\n")

    # Test 4: Verify Status Update
    print("4. Verifying status update")
    print("-" * 80)
    verify_result = call_tool(
        "DynamoDBMCPTarget___get_order",
        {
            "order_id": order_id
        }
    )

    try:
        lambda_response = json.loads(verify_result["result"]["content"][0]["text"])
        final_order = json.loads(lambda_response["body"])
        print(f"✅ Final order status: {final_order['order_status']}")
        print(f"   Order ID: {final_order['order_id']}")
        print(f"   Customer: {final_order['customer_name']}")
        print(f"   Total: ${final_order['total_amount']}\n")
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse verification response: {e}\n")

    print("=" * 80)
    print("✅ All tests completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()
