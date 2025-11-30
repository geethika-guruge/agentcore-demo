# Deploy Steps

## First Time Setup Instructions
- python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt
- cd cdk && cdk deploy
- cd agentcore/gateway && python setup_gateway.py
- cd agentcore/gateway && python test_gateway.py
- cd agentcore/gateway/targets/lambda_mcp_targets && python register_dynamodb_tools.py
- cd agentcore/runtime && agentcore configure --entrypoint order_assistant.py
- cd agentcore/runtime && agentcore launch
    When asks for IAM role, provide the AgentCore Runtime Execution Role ARN from cdk deploy outputs
    Rename the new .bedrock_agentcore.yaml with .bedrock_agentcore.<region-name>.yaml
- cd agentcore/runtime && python agentcore_deploy.py
- cd assets && python populate_customers.py
- cd assets && python populate_delivery_slots.py
- cd scripts && ./invoke_populate_catalog.sh
- cd scripts && ./test_agent.sh (local test path)

## Subsequent Deploy Instructions
- Run ./setup_env.sh and select the desried account
- cd cdk && cdk deploy
- cd agentcore/runtime && python agentcore_deploy.py