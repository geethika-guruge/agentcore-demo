from bedrock_agentcore.runtime import BedrockAgentCoreApp
import logging
from core import process_grocery_list

logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    """Handler for Bedrock agent invocation"""
    print(f"Received payload type: {type(payload)}")
    print(f"Received payload value: {payload}")

    # Handle both dict and string payloads (AgentCore may send JSON string)
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
            print(f"Parsed string payload to dict: {payload}")
        except json.JSONDecodeError as e:
            print(f"Failed to parse payload as JSON: {e}")
            return "Error: Invalid JSON payload"

    if not isinstance(payload, dict):
        print(f"Invalid payload format. Expected dict, got {type(payload)}: {payload}")
        return "Error: Invalid payload format"

    action = payload.get("action", "UNKNOWN")
    customer_id = payload.get("customer_id", "unknown")

    print(f"Processing action '{action}' for customer {customer_id}")
    print(f"Full payload being sent to process_grocery_list: {payload}")

    # Pass full payload to orchestrator for processing
    result = process_grocery_list(payload)

    print(f"Processing completed")

    return result


if __name__ == "__main__":
    app.run()
