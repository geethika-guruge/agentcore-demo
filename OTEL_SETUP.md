# OpenTelemetry Tracing Setup with Arize

This project is instrumented with OpenTelemetry to send traces to Arize for observability and debugging.

## Prerequisites

1. An Arize account with access to:
   - Space ID
   - API Key
   - Project name

2. Required Python packages (already in `requirements.txt`):
   - `openinference-instrumentation-bedrock`
   - `arize-otel`

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Arize Credentials

Edit the `.otel_config.yaml` file in the project root and replace the placeholder values:

```yaml
# .otel_config.yaml
space_id: "your-actual-space-id"
api_key: "your-actual-api-key"
project_name: "your-project-name"
```

**How to get your credentials:**
- Log in to your Arize account
- Navigate to Settings → API Keys
- Copy your Space ID and API Key
- Choose or create a project name for organizing your traces

### 3. Deploy the Application

The instrumentation will automatically activate when:
- The `.otel_config.yaml` file is present
- Valid credentials are configured (not placeholder values)
- The agents are initialized

Deploy as usual:
```bash
cd cdk
cdk deploy
```

## How It Works

### Agent Instrumentation

The `agentcore/runtime/core.py` file automatically:
1. Loads the OTel configuration from `.otel_config.yaml`
2. Initializes the Arize tracer provider
3. Instruments all Bedrock agent calls
4. Sends traces to Arize

### What Gets Traced

The instrumentation captures:
- **LLM calls** - All Claude/Bedrock model invocations
- **Agent executions** - Router, catalog, order, warehouse, and image processor agents
- **Tool calls** - MCP tool invocations (database queries, S3 operations, etc.)
- **Graph workflows** - Multi-agent coordination and routing decisions
- **Timing metrics** - Latency, token usage, and execution time

### Lambda Execution

The Lambda function (`cdk/src/lambda/process_order/lambda.py`) calls the AgentCore runtime, which has the instrumentation. No separate lambda instrumentation is needed since all agent execution happens in the instrumented runtime.

## Viewing Traces in Arize

1. Log in to your Arize account
2. Navigate to your project (the name you configured)
3. View traces in the AX (Arize Explorer) interface
4. Analyze:
   - Request flows through the multi-agent system
   - LLM token usage and costs
   - Performance bottlenecks
   - Tool call patterns
   - Error traces

## Troubleshooting

### Tracing is Disabled

If you see this log message:
```
OTel tracing disabled - configuration contains placeholder values
```

**Solution:** Update `.otel_config.yaml` with your actual Arize credentials.

### No Traces in Arize

1. **Check credentials:** Verify your Space ID and API Key are correct
2. **Check network:** Ensure the Lambda/AgentCore can reach Arize endpoints
3. **Check logs:** Look for OTel initialization messages in CloudWatch logs:
   - ✓ OTel tracing initialized successfully
   - ✓ Traces will be sent to Arize project: {project_name}

### Configuration File Not Found

If you see:
```
OTel config file not found. Tracing will be disabled.
```

**Solution:** Create `.otel_config.yaml` in the project root directory (same level as `cdk/` and `agentcore/`).

## Disabling Tracing

To disable tracing without removing the code:
1. Rename `.otel_config.yaml` to `.otel_config.yaml.disabled`, OR
2. Set the values back to placeholders (starting with "YOUR_")

The application will continue to work normally without tracing.

## References

- [Arize Documentation - Bedrock Agents Tracing](https://arize.com/docs/ax/integrations/llm-providers/amazon-bedrock/amazon-bedrock-agents-tracing)
- [OpenInference Bedrock Instrumentation](https://github.com/Arize-ai/openinference)
