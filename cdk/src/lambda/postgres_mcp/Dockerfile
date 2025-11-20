FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt --no-cache-dir

# Copy function code
COPY lambda.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "lambda.handler" ]
