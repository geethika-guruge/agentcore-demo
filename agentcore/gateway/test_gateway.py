import requests
import json
import boto3

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

CLIENT_ID = client_info["client_id"]
CLIENT_SECRET = client_info["client_secret"]
TOKEN_URL = client_info["token_endpoint"]

print(f"Using credentials from Secrets Manager: {secret_name}\n")


def fetch_access_token(client_id, client_secret, token_url):
    response = requests.post(
        token_url,
        data="grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}".format(
            client_id=client_id, client_secret=client_secret
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    return response.json()["access_token"]


def list_tools(gateway_url, access_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    payload = {"jsonrpc": "2.0", "id": "list-tools-request", "method": "tools/list"}

    response = requests.post(gateway_url, headers=headers, json=payload)
    return response.json()


# Example usage
print(f"Testing gateway: {gateway_url}\n")

access_token = fetch_access_token(CLIENT_ID, CLIENT_SECRET, TOKEN_URL)
tools = list_tools(gateway_url, access_token)
print(json.dumps(tools, indent=2))
