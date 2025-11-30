#!/usr/bin/env python3
import aws_cdk as cdk
from stack import OrderAssistantStack
import boto3

# Get account and region from AWS session (uses AWS profile configuration)
session = boto3.Session()
sts_client = session.client("sts")
account = sts_client.get_caller_identity()["Account"]
region = session.region_name

# Account and region-specific phone number IDs
phone_number_ids = {
    "116354729252": {  # sandpit-4
        "ap-southeast-2": "phone-number-id-f82a097f349f44798c5926fb29db1ac1",
        "us-west-2": "phone-number-id-cd90e10a5b8e40de869491764db21904",
    },
    "054671736399": {  # sandpit-3
        "ap-southeast-2": "phone-number-id-ed322c4a4fd74422a861ee6422ac8576",
        "us-west-2": "phone-number-id-c50a0927e4ea4b8f94bb893c1d6f26c9",
    },
}

if account not in phone_number_ids:
    raise ValueError(f"Unsupported account: {account}. Supported accounts: {list(phone_number_ids.keys())}")

if region not in phone_number_ids[account]:
    raise ValueError(f"Unsupported region: {region} for account {account}. Supported regions: {list(phone_number_ids[account].keys())}")

phone_number_id = phone_number_ids[account][region]

app = cdk.App()
OrderAssistantStack(
    app,
    "OrderAssistantStack",
    phone_number_id=phone_number_id,
    env=cdk.Environment(account=account, region=region),
)

app.synth()
