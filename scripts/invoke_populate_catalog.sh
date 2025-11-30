#!/bin/bash

# Script to invoke the populate database Lambda function
# This runs the Lambda to populate the PostgreSQL database with product data

set -e

# Get region from AWS CLI configuration
REGION=$(aws configure get region)
if [ -z "$REGION" ]; then
    echo "❌ Error: No AWS region configured"
    echo "   Run: aws configure set region <your-region>"
    exit 1
fi

echo "Using AWS region: $REGION"
STACK_NAME="OrderAssistantStack"

echo "🔍 Getting Lambda function name from CloudFormation stack..."
LAMBDA_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='PopulateCatalogLambdaName'].OutputValue" \
    --output text)

if [ -z "$LAMBDA_NAME" ]; then
    echo "❌ Error: Could not find PopulateCatalogLambdaName in stack outputs"
    echo "   Make sure the stack is deployed with the populate catalog Lambda"
    exit 1
fi

echo "✓ Found Lambda function: $LAMBDA_NAME"
echo ""

# Parse command line arguments
OPERATION="insert"
CLEAR_EXISTING="false"

if [ "$1" == "--select" ]; then
    OPERATION="select"
    echo "📋 Operation: SELECT - Will display product catalog"
elif [ "$1" == "--clear" ]; then
    CLEAR_EXISTING="true"
    echo "⚠️  Operation: INSERT - Will clear existing data before inserting"
else
    echo "📦 Operation: INSERT - Will populate database with products"
fi

echo ""
echo "Usage:"
echo "  $0              # Insert/update products (default)"
echo "  $0 --select     # Display current product catalog"
echo "  $0 --clear      # Insert/update products after clearing existing data"
echo ""

echo "🚀 Invoking Lambda function..."
echo ""

# Invoke the Lambda function
RESPONSE=$(aws lambda invoke \
    --function-name $LAMBDA_NAME \
    --payload "{\"operation\": \"$OPERATION\", \"clear_existing\": $CLEAR_EXISTING}" \
    --cli-binary-format raw-in-base64-out \
    /tmp/populate_db_response.json)

echo "Response metadata:"
echo "$RESPONSE" | jq '.'
echo ""

echo "Lambda function output:"
cat /tmp/populate_db_response.json | jq '.'
echo ""

# Check if the invocation was successful
STATUS_CODE=$(cat /tmp/populate_db_response.json | jq -r '.statusCode // 0')

if [ "$STATUS_CODE" -eq 200 ]; then
    if [ "$OPERATION" == "select" ]; then
        echo "✅ Product catalog retrieved successfully!"
    else
        echo "✅ Database populated successfully!"
    fi

    # Show summary
    BODY=$(cat /tmp/populate_db_response.json | jq -r '.body')
    echo ""
    echo "Summary:"
    echo "$BODY" | jq '.'
else
    echo "❌ Error: Operation failed"
    cat /tmp/populate_db_response.json | jq '.'
    exit 1
fi

# Clean up
rm /tmp/populate_db_response.json
