#!/usr/bin/env python3
"""
Script to verify that telemetry data is being successfully sent to Arize.

This script queries the Arize API to check for recent traces and spans.
"""

import requests
import yaml
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Load Arize credentials from .otel_config.yaml
def load_arize_config():
    """Load Arize configuration from .otel_config.yaml"""
    config_path = Path(__file__).parent.parent / ".otel_config.yaml"

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        space_id = config.get("space_id")
        api_key = config.get("api_key")
        project_name = config.get("project_name")

        if not space_id or space_id.startswith("YOUR_"):
            print("❌ Error: space_id not configured in .otel_config.yaml")
            sys.exit(1)

        if not api_key or api_key.startswith("YOUR_"):
            print("❌ Error: api_key not configured in .otel_config.yaml")
            sys.exit(1)

        return {
            "space_id": space_id,
            "api_key": api_key,
            "project_name": project_name
        }

    except FileNotFoundError:
        print(f"❌ Error: .otel_config.yaml not found at {config_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        sys.exit(1)


def query_arize_graphql(space_id, api_key, query):
    """
    Query Arize GraphQL API

    Args:
        space_id: Arize space ID
        api_key: Arize API key
        query: GraphQL query string

    Returns:
        Response JSON or None if error
    """
    # Arize GraphQL endpoint
    url = "https://app.arize.com/graphql"

    # Try multiple authentication methods
    auth_methods = [
        {
            "name": "Bearer token with space-id header",
            "headers": {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "space-id": space_id
            }
        },
        {
            "name": "x-api-key header",
            "headers": {
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "space-id": space_id
            }
        },
        {
            "name": "API key without Bearer",
            "headers": {
                "Authorization": api_key,
                "Content-Type": "application/json",
                "space-id": space_id
            }
        },
        {
            "name": "authorization header lowercase",
            "headers": {
                "authorization": api_key,
                "Content-Type": "application/json",
                "arize-space-id": space_id
            }
        }
    ]

    for method in auth_methods:
        try:
            response = requests.post(
                url,
                json={"query": query},
                headers=method["headers"],
                timeout=30
            )

            if response.status_code == 200:
                print(f"✅ Authentication successful using: {method['name']}")
                return response.json()
            elif response.status_code == 401:
                print(f"⚠️  {method['name']}: 401 Unauthorized")
                continue
            else:
                print(f"⚠️  {method['name']}: {response.status_code}")
                continue

        except Exception as e:
            print(f"⚠️  {method['name']}: Error - {e}")
            continue

    print(f"\n❌ All authentication methods failed")
    print(f"   This might mean:")
    print(f"   1. The GraphQL API requires web browser authentication (not API key)")
    print(f"   2. Your API key doesn't have GraphQL access permissions")
    print(f"   3. The GraphQL endpoint requires a different authentication method")
    return None


def check_models_in_space(space_id, api_key, project_name):
    """Check if the project/model exists in the space"""

    query = f"""
    query {{
      node(id: "{space_id}") {{
        ... on Space {{
          models(first: 100) {{
            edges {{
              node {{
                id
                name
                modelType
                createdAt
              }}
            }}
          }}
        }}
      }}
    }}
    """

    print(f"\n🔍 Checking for models in space {space_id}...")
    result = query_arize_graphql(space_id, api_key, query)

    if not result:
        return False

    if "errors" in result:
        print(f"❌ GraphQL errors: {json.dumps(result['errors'], indent=2)}")
        return False

    try:
        models = result["data"]["node"]["models"]["edges"]

        if not models:
            print(f"⚠️  No models found in space")
            print(f"   This is normal if you just started sending data")
            return False

        print(f"\n✅ Found {len(models)} model(s) in space:")

        target_found = False
        for edge in models:
            model = edge["node"]
            model_name = model.get("name", "Unknown")
            model_type = model.get("modelType", "Unknown")
            created_at = model.get("createdAt", "Unknown")

            is_target = project_name.lower() in model_name.lower()
            marker = "👉" if is_target else "  "

            print(f"{marker} Model: {model_name}")
            print(f"   Type: {model_type}")
            print(f"   Created: {created_at}")
            print()

            if is_target:
                target_found = True

        if target_found:
            print(f"✅ Found your project: {project_name}")
        else:
            print(f"⚠️  Project '{project_name}' not found yet")
            print(f"   Available models listed above")

        return target_found

    except KeyError as e:
        print(f"❌ Unexpected response structure: {e}")
        print(f"Response: {json.dumps(result, indent=2)}")
        return False


def check_recent_traces_via_phoenix():
    """
    Alternative method: Use Arize Phoenix client if available
    """
    try:
        from phoenix.otel import register
        print("\n🔍 Checking via Phoenix client...")
        print("⚠️  Note: This requires phoenix package to be installed")
        print("   Install with: pip install arize-phoenix")
        return False
    except ImportError:
        print("\n⚠️  Phoenix client not available (optional)")
        return False


def print_manual_verification_steps(project_name):
    """Print manual verification steps for Arize UI"""
    print("\n" + "="*60)
    print("🌐 MANUAL VERIFICATION (Recommended)")
    print("="*60)
    print(f"""
Since the GraphQL API requires enterprise access, use the Arize UI instead:

1. Open your browser and go to: https://app.arize.com

2. Log in with your Arize account

3. Select your Space from the dropdown (top right)

4. Look for your project: "{project_name}"
   - If it appears, click on it
   - Navigate to "Traces" or "AX" tab
   - You should see traces from your application

5. Check the time range:
   - Make sure you're looking at "Last 24 hours" or appropriate range
   - Traces appear within 1-5 minutes of generation

6. If no project found:
   - Send a WhatsApp message to trigger your application
   - Wait 5 minutes
   - Refresh the Arize UI
""")
    print("="*60)


def print_troubleshooting_tips(project_name):
    """Print troubleshooting tips"""
    print("\n" + "="*60)
    print("📋 TROUBLESHOOTING TIPS")
    print("="*60)
    print("""
1. Verify telemetry is being sent:
   - Check AgentCore runtime logs for:
     [OTel] ✓ Tracing initialized successfully

   - Check Lambda logs for:
     [Lambda OTel] ✓ Tracing initialized

2. Wait for data to appear:
   - It can take 1-5 minutes for data to appear in Arize
   - Try running this script again in a few minutes

3. Test your application:
   - Send a WhatsApp message to trigger the workflow
   - Check CloudWatch logs for OTel initialization messages

4. View traces in Arize UI:
   - Log in to: https://app.arize.com
   - Navigate to your project: {project_name}
   - Check the "Traces" or "AX" section

5. Verify credentials:
   - Ensure space_id and api_key in .otel_config.yaml are correct
   - Check that the values don't start with "YOUR_"

6. Check network connectivity:
   - Ensure Lambda/AgentCore can reach Arize endpoints
   - Check VPC/security group settings if applicable
""")
    print("="*60)


def main():
    print("="*60)
    print("🔍 ARIZE TELEMETRY VERIFICATION")
    print("="*60)

    # Load configuration
    config = load_arize_config()
    space_id = config["space_id"]
    api_key = config["api_key"]
    project_name = config["project_name"]

    print(f"\n📊 Configuration:")
    print(f"   Space ID: {space_id[:20]}...")
    print(f"   Project: {project_name}")

    # Check for models/projects in the space
    found = check_models_in_space(space_id, api_key, project_name)

    # Try Phoenix client method (optional)
    check_recent_traces_via_phoenix()

    # Print results
    print("\n" + "="*60)
    if found:
        print("✅ SUCCESS: Your project is receiving telemetry data!")
        print(f"\n🌐 View traces at: https://app.arize.com")
        print(f"   Navigate to project: {project_name}")
    else:
        print("⚠️  NOTE: GraphQL API verification requires enterprise access")
        print_manual_verification_steps(project_name)
        print_troubleshooting_tips(project_name)
    print("="*60)

    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
