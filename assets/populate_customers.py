#!/usr/bin/env python3
"""
Populate Customers DynamoDB table with sample data
Run this script after deploying the CDK stack to initialize customer records
"""

import boto3

region = "ap-southeast-2"

# Get table name from CloudFormation outputs
cfn = boto3.client("cloudformation", region_name=region)
response = cfn.describe_stacks(StackName="OrderAssistantStack")
outputs = response["Stacks"][0]["Outputs"]
table_name = next(
    o["OutputValue"] for o in outputs if o["OutputKey"] == "CustomersTableName"
)

print(f"Using DynamoDB table: {table_name}\n")

dynamodb = boto3.resource("dynamodb", region_name=region)
table = dynamodb.Table(table_name)

# Sample customers with customer_id (mobile number) and postcode
sample_customers = [
    {
        'customer_id': '6421344975',
        'postcode': 'SW1A'
    },
    {
        'customer_id': '64226475636',
        'postcode': 'SW1B'
    },
    {
        'customer_id': '6421234569',
        'postcode': 'SW1C'
    },
    {
        'customer_id': '6421234570',
        'postcode': 'EC1A'
    },
    {
        'customer_id': '6421234571',
        'postcode': 'W1A'
    },
    {
        'customer_id': '6421234572',
        'postcode': 'W1B'
    },
    {
        'customer_id': '6421234573',
        'postcode': 'EC1A'
    },
    {
        'customer_id': '6421234574',
        'postcode': 'SW1A'
    },
    {
        'customer_id': '6421234575',
        'postcode': 'SW1B'
    },
    {
        'customer_id': '6421234576',
        'postcode': 'W1A'
    },
]

print(f"Populating {len(sample_customers)} customers into DynamoDB table...\n")

with table.batch_writer() as batch:
    for customer in sample_customers:
        batch.put_item(Item=customer)
        print(f"  ✓ Added: Customer {customer['customer_id']} - Postcode {customer['postcode']}")

print(f"\n✅ Successfully populated {len(sample_customers)} customers!")

# Summary statistics
postcodes = {}
for customer in sample_customers:
    pc = customer['postcode']
    postcodes[pc] = postcodes.get(pc, 0) + 1

print(f"\nPostcode Distribution:")
for postcode, count in sorted(postcodes.items()):
    print(f"  - {postcode}: {count} customers")

print(f"\n💡 Use these customer IDs for testing orders!")
