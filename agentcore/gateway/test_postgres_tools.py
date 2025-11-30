#!/usr/bin/env python3
"""
Test script for PostgreSQL Custom Tools via AgentCore Gateway
Tests search_products_by_product_names and list_product_catalogue tools
"""

import json
import sys
import boto3
from pathlib import Path

# Add parent directory to path to import gateway client
sys.path.insert(0, str(Path(__file__).parent.parent))

from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# Get region from AWS session (uses AWS profile configuration)
session = boto3.Session()
region = session.region_name

# Fetch gateway configuration from SSM Parameter Store
ssm_client = session.client("ssm")

gateway_id_response = ssm_client.get_parameter(Name="/order-assistant/gateway-id")
gateway_id = gateway_id_response["Parameter"]["Value"]

gateway_url_response = ssm_client.get_parameter(Name="/order-assistant/gateway-url")
gateway_url = gateway_url_response["Parameter"]["Value"]

# Get client_info from Secrets Manager
secrets_client = session.client("secretsmanager")
secret_name = f"agentcore/gateway/{gateway_id}/client-info"
response = secrets_client.get_secret_value(SecretId=secret_name)
client_info = json.loads(response["SecretString"])

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
    print("Testing PostgreSQL Custom Tools via AgentCore Gateway")
    print("=" * 80)
    print(f"Gateway URL: {gateway_url}")
    print(f"Gateway ID: {gateway_id}")
    print(f"Region: {region}\n")

    # Test 1: Search for specific products
    print("1. Testing search_products_by_product_names - Multiple products")
    print("-" * 80)
    search_result = call_tool(
        "PostgreSQLMCPTarget___search_products_by_product_names",
        {
            "product_names": [
                "butter unsalted",
                "chicken breasts",
                "salmon",
                "coffee"
            ]
        }
    )

    # Parse and display results
    try:
        lambda_response = json.loads(search_result["result"]["content"][0]["text"])
        products = json.loads(lambda_response["body"])
        print(f"✅ Found {len(products)} products:")
        for i, product in enumerate(products, 1):
            print(f"\n{i}. {product['product_name']}")
            print(f"   Category: {product['product_category']}")
            print(f"   Price: ${product['price']}")
            print(f"   Stock: {product.get('stock_level', 'N/A')}")
            print(f"   Description: {product['product_description'][:80]}...")
        print()
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse search results: {e}\n")

    # Test 2: Search for a product with special characters (parentheses)
    print("2. Testing search_products_by_product_names - Product with special chars")
    print("-" * 80)
    special_search_result = call_tool(
        "PostgreSQLMCPTarget___search_products_by_product_names",
        {
            "product_names": ["butter (unsalted)"]
        }
    )

    try:
        lambda_response = json.loads(special_search_result["result"]["content"][0]["text"])
        products = json.loads(lambda_response["body"])
        if products:
            print(f"✅ Successfully found product with parentheses in name:")
            for product in products:
                print(f"   - {product['product_name']} (${product['price']})")
        else:
            print(f"❌ No products found")
        print()
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse results: {e}\n")

    # Test 3: Search for a product that doesn't exist
    print("3. Testing search_products_by_product_names - Non-existent product")
    print("-" * 80)
    empty_search_result = call_tool(
        "PostgreSQLMCPTarget___search_products_by_product_names",
        {
            "product_names": ["unicorn meat", "dragon eggs"]
        }
    )

    try:
        lambda_response = json.loads(empty_search_result["result"]["content"][0]["text"])
        products = json.loads(lambda_response["body"])
        if not products:
            print(f"✅ Correctly returned empty results for non-existent products\n")
        else:
            print(f"⚠️  Unexpected: Found {len(products)} products\n")
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse results: {e}\n")

    # Test 4: List entire product catalogue
    print("4. Testing list_product_catalogue - Get all products")
    print("-" * 80)
    list_result = call_tool(
        "PostgreSQLMCPTarget___list_product_catalogue",
        {}  # No arguments needed
    )

    try:
        lambda_response = json.loads(list_result["result"]["content"][0]["text"])
        all_products = json.loads(lambda_response["body"])
        print(f"✅ Retrieved {len(all_products)} total products from catalogue\n")

        # Group by category
        categories = {}
        for product in all_products:
            category = product['product_category']
            if category not in categories:
                categories[category] = []
            categories[category].append(product)

        print("Products by Category:")
        print("-" * 40)
        for category, products in sorted(categories.items()):
            print(f"\n{category} ({len(products)} items):")
            for product in products:
                print(f"  - {product['product_name']}: ${product['price']} (Stock: {product.get('stock_level', 'N/A')})")
        print()
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse catalogue: {e}\n")

    # Test 5: Test flexible matching (word order)
    print("5. Testing flexible search - Word order variations")
    print("-" * 80)
    flexible_search_result = call_tool(
        "PostgreSQLMCPTarget___search_products_by_product_names",
        {
            "product_names": [
                "unsalted butter",  # Reversed word order
                "breasts chicken",  # Reversed
                "flour all purpose" # Reversed with space
            ]
        }
    )

    try:
        lambda_response = json.loads(flexible_search_result["result"]["content"][0]["text"])
        products = json.loads(lambda_response["body"])
        print(f"✅ Flexible matching found {len(products)} products with reversed word order:")
        for product in products:
            print(f"   - {product['product_name']}")
        print()
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Failed to parse results: {e}\n")

    print("=" * 80)
    print("✅ All PostgreSQL tool tests completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()
