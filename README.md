# Deploy Steps

- Create and activate virtual environment
  ```
  python -m venv .venv && source .venv/bin/activate
  ```
- Install Python dependencies
  ```
  pip install -r requirements.txt
  ```
- Deploy CDK stack
  ```
  cd cdk && cdk deploy
  ```
- Setup gateway
  ```
  cd agentcore/gateway && python setup_gateway.py
  ```
- Test gateway
  ```
  cd agentcore/gateway && python test_gateway.py
  ```
- Register DynamoDB tools
  ```
  cd agentcore/gateway/targets/lambda_mcp_targets && python register_dynamodb_tools.py
  ```
- First time setup: configure agentcore with entrypoint
  - When asks for IAM role, provide the AgentCore Runtime Execution Role ARN from CloudFormation outputs
  ```
  cd agentcore/runtime && agentcore configure --entrypoint order_assistant.py
  ```
- Launch agentcore runtime
  ```
  cd agentcore/runtime && agentcore launch
  ```
- Populate catalog data
  ```
  cd scripts && ./invoke_populate_catalog.sh
  ```
- Populate customer data
  ```
  cd assets && python populate_customers.py
  ```
- Populate delivery slot data
  ```
  cd assets && python populate_delivery_slots.py
  ```
- Test DynamoDB tools after populating data
  ```
  cd agentcore/gateway && python test_dynamodb_tools.py
  ```
- Test Postgres tools after populating data
  ```
  cd agentcore/gateway && python test_postgres_tools.py
  ```
- Test agent (local test path)
  ```
  cd scripts && ./test_agent.sh
  ```
