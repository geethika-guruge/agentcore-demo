"""
Lambda handler for DynamoDB MCP Server
This Lambda function hosts the awslabs.dynamodb-mcp-server
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def handler(event, context):
    """
    Lambda handler that runs the DynamoDB MCP server

    The MCP server is executed using uvx (uv's command runner)
    Environment variables are passed through from Lambda configuration
    """

    # Set up environment variables from Lambda configuration
    env = os.environ.copy()

    # Parse the incoming MCP request
    try:
        body = (
            json.loads(event.get("body", "{}"))
            if isinstance(event.get("body"), str)
            else event.get("body", {})
        )

        # For MCP protocol, we need to handle JSON-RPC style requests
        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id", 1)

        # Run the MCP server command
        # Note: In a real deployment, you would need to package the MCP server
        # or use a Lambda layer with uvx and the necessary dependencies

        result = subprocess.run(
            ["uvx", "awslabs.dynamodb-mcp-server@latest"],
            input=json.dumps(body),
            capture_output=True,
            text=True,
            env=env,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            response_data = json.loads(result.stdout) if result.stdout else {}
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(response_data),
            }
        else:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {
                        "error": "MCP server error",
                        "stderr": result.stderr,
                        "returncode": result.returncode,
                    }
                ),
            }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e), "type": type(e).__name__}),
        }
