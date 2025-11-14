# Deploy Steps

- python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt
- cd cdk && cdk deploy
- cd agentcore/gateway && python setup_gateway.py
- cd agentcore/gateway && python test_gateway.py
- cd agentcore/gateway/targets/lambda_mcp_targets && python register_dynamodb_tools.py
- cd agentcore/runtime && agentcore configure --entrypoint order_assistant.py (For first time setup)
- cd agentcore/runtime && agentcore launch
- cd scripts && ./populate_catalog.sh
- cd scripts && ./test_agent.sh (local test path)
- cd scripts && ./upload_grocery_list.sh (textract path)
