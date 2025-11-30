#!/bin/bash

echo "Select environment:"
echo "1) sandpit-3"
echo "2) sandpit-4"
read -p "Enter choice (1 or 2): " choice

case $choice in
    1)
        env="sandpit_3"
        ;;
    2)
        env="sandpit_4"
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo "Setting up environment: $env"

# Copy gateway configs
cp config/$env/gateway_config_*.json agentcore/gateway/ 2>/dev/null
echo "✓ Gateway configs copied"

# Copy agentcore runtime configs
cp config/$env/.bedrock_agentcore.*.yaml agentcore/runtime/ 2>/dev/null
echo "✓ AgentCore runtime configs copied"

echo "✅ Environment $env ready for deployment"
