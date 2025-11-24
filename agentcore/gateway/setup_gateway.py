"""
Setup script to create Gateway with Lambda target and save configuration
Run this first: python setup_gateway.py
"""

from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
import json
import logging
import time
import boto3
import pathlib
import shutil


def setup_gateway():
    # Configuration
    region = "ap-southeast-2"  # Change to your preferred region

    print("🚀 Setting up AgentCore Gateway...")
    print(f"Region: {region}\n")

    # Initialize client
    client = GatewayClient(region_name=region)
    client.logger.setLevel(logging.INFO)

    # Step 2.1: Create OAuth authorizer
    print("Step 2.1: Creating OAuth authorization server...")
    cognito_response = client.create_oauth_authorizer_with_cognito("TestGateway")
    print("✓ Authorization server created\n")

    # Step 2.2: Create Gateway
    print("Step 2.2: Creating Gateway...")
    gateway = client.create_mcp_gateway(
        # the name of the Gateway - if you don't set one, one will be generated.
        name=None,
        # the role arn that the Gateway will use - if you don't set one, one will be created.
        # NOTE: if you are using your own role make sure it has a trust policy that trusts bedrock-agentcore.amazonaws.com
        role_arn=None,
        # the OAuth authorization server details. If you are providing your own authorization server,
        # then pass an input of the following form: {"customJWTAuthorizer": {"allowedClients": ["<INSERT CLIENT ID>"], "discoveryUrl": "<INSERT DISCOVERY URL>"}}
        authorizer_config=cognito_response["authorizer_config"],
        # enable semantic search
        enable_semantic_search=True,
    )
    print(f"✓ Gateway created: {gateway['gatewayUrl']}\n")

    # If role_arn was not provided, fix IAM permissions
    # NOTE: This is handled internally by the toolkit when no role is provided
    client.fix_iam_permissions(gateway)
    print("⏳ Waiting 30s for IAM propagation...")
    time.sleep(30)
    print("✓ IAM permissions configured\n")

    # Step 2.3: Save configuration for agent
    config = {
        "gateway_url": gateway["gatewayUrl"],
        "gateway_id": gateway["gatewayId"],
        "region": region,
        "client_info": cognito_response["client_info"],
    }

    with open("gateway_config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    # Copy gateway_config.json to runtime directory for Docker build
    runtime_dir = pathlib.Path(__file__).parent.parent / "runtime"
    runtime_config_path = runtime_dir / "gateway_config.json"
    shutil.copy("gateway_config.json", runtime_config_path)
    print(f"✓ Configuration copied to: {runtime_config_path}\n")

    # Step 2.4: Store client_info in AWS Secrets Manager
    print("Step 2.4: Storing credentials in AWS Secrets Manager...")
    secrets_client = boto3.client("secretsmanager", region_name=region)
    secret_name = f"agentcore/gateway/{gateway['gatewayId']}/client-info"

    try:
        secrets_client.create_secret(
            Name=secret_name,
            Description=f"Gateway client credentials for {gateway['gatewayId']}",
            SecretString=json.dumps(cognito_response["client_info"]),
        )
        print(f"✓ Credentials stored in Secrets Manager: {secret_name}\n")
    except secrets_client.exceptions.ResourceExistsException:
        secrets_client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(cognito_response["client_info"]),
        )
        print(f"✓ Credentials updated in Secrets Manager: {secret_name}\n")

    print("=" * 60)
    print("✅ Gateway setup complete!")
    print(f"Gateway URL: {gateway['gatewayUrl']}")
    print(f"Gateway ID: {gateway['gatewayId']}")
    print("\nConfiguration saved to:")
    print("  - gateway/gateway_config.json")
    print("  - runtime/gateway_config.json (for Docker build)")
    print("\nNext step: Run 'python test_gateway.py' to test your Gateway")
    print("=" * 60)

    return config


if __name__ == "__main__":
    setup_gateway()
