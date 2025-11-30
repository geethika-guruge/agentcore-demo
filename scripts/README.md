# Arize Telemetry Verification Script

This script verifies that OpenTelemetry data is being successfully sent to Arize from your order-assistant application.

## Prerequisites

```bash
pip install requests pyyaml
```

## Usage

Run the script from anywhere in the project:

```bash
# From the scripts directory
cd /Users/geethika/work/dini-shopping-agent/order-assistant/scripts
python3 check_arize_telemetry.py

# Or from the project root
python3 scripts/check_arize_telemetry.py
```

## What It Checks

The script performs the following checks:

1. **Configuration Validation**
   - Verifies `.otel_config.yaml` exists and has valid credentials
   - Checks that space_id, api_key, and project_name are configured

2. **GraphQL API Query**
   - Connects to Arize GraphQL API
   - Lists all models/projects in your space
   - Identifies if your project is receiving data

3. **Troubleshooting Guidance**
   - Provides actionable tips if data is not found
   - Suggests next steps for debugging

## Expected Output

### ✅ Success (Data is being received)

```
============================================================
🔍 ARIZE TELEMETRY VERIFICATION
============================================================

📊 Configuration:
   Space ID: U3BhY2U6MjEzMTI6WTJ...
   Project: order-assistant-prod

🔍 Checking for models in space...

✅ Found 3 model(s) in space:
👉 Model: order-assistant-prod
   Type: LLM
   Created: 2025-11-24T03:45:00Z

============================================================
✅ SUCCESS: Your project is receiving telemetry data!

🌐 View traces at: https://app.arize.com
   Navigate to project: order-assistant-prod
============================================================
```

### ⚠️ Pending (Data not yet visible)

```
============================================================
🔍 ARIZE TELEMETRY VERIFICATION
============================================================

📊 Configuration:
   Space ID: U3BhY2U6MjEzMTI6WTJ...
   Project: order-assistant-prod

🔍 Checking for models in space...

⚠️  No models found in space
   This is normal if you just started sending data

============================================================
⚠️  PENDING: Telemetry data not yet visible

📋 TROUBLESHOOTING TIPS
============================================================

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
...
============================================================
```

## Troubleshooting

### Authentication Errors

If you see authentication errors:
```
❌ GraphQL request failed: 401
```

**Solution:** Verify your API credentials in `.otel_config.yaml`:
- Ensure `space_id` and `api_key` are correct
- Log in to https://app.arize.com and go to Settings → API Keys
- Copy the correct values

### Network Errors

If you see connection timeouts or network errors:
```
❌ Error querying Arize API: Connection timeout
```

**Solution:** Check your internet connection and firewall settings.

### No Data Found

If no models are found but you've deployed:

1. **Wait 5 minutes** - Data ingestion can take time
2. **Trigger your application** - Send a test WhatsApp message
3. **Check logs:**
   ```bash
   # Check AgentCore runtime logs
   aws logs tail /aws/bedrock-agentcore/... --follow

   # Check Lambda logs
   aws logs tail /aws/lambda/OrderAssistantStack-ProcessOrder... --follow
   ```
4. **Verify initialization** - Look for OTel success messages

## Manual Verification in Arize UI

You can also manually verify in the Arize web interface:

1. Log in to https://app.arize.com
2. Select your Space (top dropdown)
3. Navigate to your project (e.g., "order-assistant-prod")
4. Click on "Traces" or "AX" in the left sidebar
5. You should see traces from your application

## Common Issues

### Issue: "space_id not configured"
- Update `.otel_config.yaml` with your actual Arize credentials

### Issue: "Project not found yet"
- Your application hasn't sent any data yet
- Deploy and trigger your application
- Wait a few minutes and try again

### Issue: GraphQL errors
- Check that your API key has the correct permissions
- Verify your space_id is correct

## API Rate Limits

The Arize GraphQL API has rate limits. If you see rate limit errors:
- Wait a few seconds between requests
- Reduce the frequency of checks
- Contact Arize support for higher limits if needed

## Support

- Arize Documentation: https://docs.arize.com
- GraphQL API Reference: https://arize.com/docs/ax/graphql-reference
- OpenTelemetry Integration: https://docs.arize.com/arize/observe/tracing-integrations-auto/opentelemetry-arize-otel
