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
    # Get region from AWS session (uses AWS profile configuration)
    session = boto3.Session()
    region = session.region_name

    print("🚀 Setting up AgentCore Gateway...")
    print(f"Region: {region}\n")

    # Initialize clients
    client = GatewayClient(region_name=region)
    client.logger.setLevel(logging.INFO)
    ssm_client = session.client("ssm")
    secrets_client = session.client("secretsmanager")

    # Check if gateway config file already exists
    config_filename = f"gateway_config_{region}.json"
    existing_gateway_id = None

    if pathlib.Path(config_filename).exists():
        print(f"Found existing config file: {config_filename}")
        with open(config_filename, "r") as f:
            existing_config = json.load(f)
            existing_gateway_id = existing_config.get("gateway_id")

        if existing_gateway_id:
            # Verify the gateway exists in AWS by checking SSM
            try:
                ssm_gateway_id = ssm_client.get_parameter(Name="/order-assistant/gateway-id")["Parameter"]["Value"]
                if ssm_gateway_id == existing_gateway_id:
                    print(f"✓ Gateway already exists: {existing_gateway_id}")
                    print("Gateway is already configured. Use this gateway or delete the config file to create a new one.\n")

                    # Get gateway details from SSM
                    gateway_url = ssm_client.get_parameter(Name="/order-assistant/gateway-url")["Parameter"]["Value"]

                    print("=" * 60)
                    print("✅ Gateway already configured!")
                    print(f"Gateway URL: {gateway_url}")
                    print(f"Gateway ID: {existing_gateway_id}")
                    print(f"\nConfiguration file: {config_filename}")
                    print("=" * 60)

                    return {
                        "gateway_id": existing_gateway_id,
                        "gateway_url": gateway_url,
                        "region": region,
                    }
            except ssm_client.exceptions.ParameterNotFound:
                print(f"⚠️  Gateway ID in config file doesn't match SSM. Creating new gateway...\n")

    # Fetch Gateway execution role ARN from SSM
    try:
        response = ssm_client.get_parameter(
            Name="/order-assistant/gateway-execution-role-arn"
        )
        gateway_role_arn = response["Parameter"]["Value"]
        print(f"✓ Fetched Gateway execution role ARN from SSM: {gateway_role_arn}\n")
    except ssm_client.exceptions.ParameterNotFound:
        print("❌ Gateway execution role ARN not found in SSM.")
        print("Please deploy the CDK stack first using: cdk deploy\n")
        return None

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
        role_arn=gateway_role_arn,
        # the OAuth authorization server details. If you are providing your own authorization server,
        # then pass an input of the following form: {"customJWTAuthorizer": {"allowedClients": ["<INSERT CLIENT ID>"], "discoveryUrl": "<INSERT DISCOVERY URL>"}}
        authorizer_config=cognito_response["authorizer_config"],
        # enable semantic search
        enable_semantic_search=True,
    )
    print(f"✓ Gateway created: {gateway['gatewayUrl']}\n")

    # Step 2.3: Save minimal configuration for reference (gateway_url and client_info are in SSM/Secrets Manager)
    config = {
        "gateway_id": gateway["gatewayId"],
        "region": region,
    }

    config_filename = f"gateway_config_{region}.json"
    with open(config_filename, "w") as f:
        json.dump(config, f, indent=2)
    print(f"✓ Minimal configuration saved to: {config_filename}\n")

    # Step 2.4: Store gateway_id and gateway_url in SSM Parameter Store
    print("Step 2.4: Storing gateway configuration in SSM Parameter Store...")
    ssm_client.put_parameter(
        Name="/order-assistant/gateway-id",
        Value=gateway["gatewayId"],
        Description="AgentCore Gateway ID",
        Type="String",
        Overwrite=True,
    )
    ssm_client.put_parameter(
        Name="/order-assistant/gateway-url",
        Value=gateway["gatewayUrl"],
        Description="AgentCore Gateway URL",
        Type="String",
        Overwrite=True,
    )
    print(f"✓ Gateway URL stored in SSM: /order-assistant/gateway-url\n")

    # Step 2.5: Store client_info in AWS Secrets Manager
    print("Step 2.5: Storing credentials in AWS Secrets Manager...")
    secrets_client = session.client("secretsmanager")
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
    print(f"\nConfiguration saved to:")
    print(f"  - gateway/{config_filename}")
    print(f"\nNext step: Run 'python test_gateway.py' to test your Gateway")
    print("=" * 60)

    return config


if __name__ == "__main__":
    setup_gateway()
