from bedrock_agentcore.runtime import BedrockAgentCoreApp
import logging
import json
from agent import process_grocery_list

logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    """Handler for Bedrock agent invocation"""
    logger.info(f"Received payload type: {type(payload)}, value: {payload}")

    grocery_items = []

    # Handle list payload directly
    if isinstance(payload, list):
        grocery_items = payload
    # Handle dict payload
    elif isinstance(payload, dict):
        grocery_items = payload.get("grocery_items", [])
        if not grocery_items:
            text_input = payload.get("prompt", payload.get("inputText", ""))
            if text_input:
                grocery_items = text_input.split("\n")
    # Handle string payload
    elif isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, list):
                grocery_items = parsed
            else:
                grocery_items = parsed.get("grocery_items", [parsed])
        except:
            grocery_items = [payload]

    logger.info(f"Processing grocery items: {grocery_items}")

    result = process_grocery_list(grocery_items)

    logger.info(f"Processing completed")

    return result


if __name__ == "__main__":
    app.run()

