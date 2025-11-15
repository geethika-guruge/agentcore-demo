#!/bin/bash

set -e

echo "📦 Populating DynamoDB catalog..."

cd "$(dirname "$0")/.."

cd assets && python populate_dynamodb.py

echo ""
echo "✅ Catalog populated successfully!"
