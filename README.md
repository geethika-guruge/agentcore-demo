# Deploy Steps

- python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt
- cd cdk && cdk deploy
- cd agentcore/gateway && python setup_gateway.py
- cd agentcore/gateway && python test_gateway.py
- cd agentcore/gateway/targets/lambda_mcp_targets && python register_dynamodb_tools.py
- cd agentcore/runtime && agentcore configure --entrypoint order_assistant.py
    Use for first time setup
    When asks for IAM role, provide the AgentCore Runtime Execution Role ARN from CloudFormation outputs
- cd agentcore/runtime && agentcore launch
- cd scripts && ./invoke_populate_catalog.sh
- cd scripts && ./test_agent.sh (local test path)
