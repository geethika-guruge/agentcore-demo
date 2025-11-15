# Use AWS Lambda Python base image
FROM public.ecr.aws/lambda/python:3.12

# Install uv (which includes uvx)
RUN pip install --no-cache-dir uv

# Pre-install the DynamoDB MCP server to speed up cold starts
RUN uvx --help && \
    pip install --no-cache-dir awslabs.dynamodb-mcp-server

# Copy function code
COPY lambda.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD [ "lambda.handler" ]
