import boto3
import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

agentcore = boto3.client('bedrock-agentcore', region_name='ap-southeast-2')
textract = boto3.client('textract', region_name='ap-southeast-2')

def handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    response = textract.detect_document_text(
        Document={'S3Object': {'Bucket': bucket, 'Name': key}}
    )

    text_lines = [item['Text'] for item in response['Blocks'] if item['BlockType'] == 'LINE']

    print(json.dumps({'grocery_items': text_lines}))

    body = json.loads(event.get('body', '{}'))
    session_id = body.get('sessionId', f"session-{context.aws_request_id}")

    response = agentcore.invoke_agent_runtime(
        agentRuntimeArn='arn:aws:bedrock-agentcore:ap-southeast-2:354334841216:runtime/order_assistant-W4tp3BF8AV',
        runtimeSessionId=session_id,
        payload=json.dumps(text_lines),
        qualifier="DEFAULT"
    )
    response_body = response['response'].read()
    response_data = json.loads(response_body)
    logger.info("Agent Response received")

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(response_data)
    }
