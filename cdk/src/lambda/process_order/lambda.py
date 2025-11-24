import boto3
import json
import logging
import os
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

social_messaging = boto3.client("socialmessaging", region_name="ap-southeast-2")
agentcore = boto3.client("bedrock-agentcore", region_name="ap-southeast-2")
ssm = boto3.client("ssm", region_name="ap-southeast-2")
s3 = boto3.client("s3", region_name="ap-southeast-2")

# Environment variables
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
MEDIA_BUCKET_NAME = os.environ.get("MEDIA_BUCKET_NAME")
AGENT_ARN_PARAM = os.environ.get("AGENT_ARN_PARAM")
PENDING_ORDERS_TABLE = os.environ.get("PENDING_ORDERS_TABLE")

# Cached values
AGENT_ARN = None

# DynamoDB client for pending orders
dynamodb_client = boto3.client("dynamodb", region_name="ap-southeast-2")


def get_agent_arn():
    """Retrieve agent ARN from SSM parameter"""
    global AGENT_ARN
    if AGENT_ARN is None:
        response = ssm.get_parameter(Name=AGENT_ARN_PARAM)
        AGENT_ARN = response["Parameter"]["Value"]
        logger.info(f"Retrieved agent ARN from SSM: {AGENT_ARN}")
    return AGENT_ARN


def store_catalog_options(customer_id, catalog_message):
    """Store catalog options in DynamoDB for later retrieval"""
    try:
        ttl = int(time.time()) + 1800  # 30 minutes TTL
        dynamodb_client.put_item(
            TableName=PENDING_ORDERS_TABLE,
            Item={
                "customer_id": {"S": customer_id},
                "catalog_options": {"S": catalog_message},
                "created_at": {"N": str(int(time.time()))},
                "ttl": {"N": str(ttl)},
            },
        )
        logger.info(f"Stored catalog options for customer {customer_id}")
    except Exception as e:
        logger.error(f"Error storing catalog options: {e}", exc_info=True)


def get_catalog_options(customer_id):
    """Retrieve catalog options from DynamoDB"""
    try:
        response = dynamodb_client.get_item(
            TableName=PENDING_ORDERS_TABLE, Key={"customer_id": {"S": customer_id}}
        )
        if "Item" in response:
            catalog_message = response["Item"]["catalog_options"]["S"]
            logger.info(f"Retrieved catalog options for customer {customer_id}")
            return catalog_message
        else:
            logger.info(f"No catalog options found for customer {customer_id}")
            return None
    except Exception as e:
        logger.error(f"Error retrieving catalog options: {e}", exc_info=True)
        return None


def delete_catalog_options(customer_id):
    """Delete catalog options from DynamoDB after order is placed"""
    try:
        dynamodb_client.delete_item(
            TableName=PENDING_ORDERS_TABLE, Key={"customer_id": {"S": customer_id}}
        )
        logger.info(f"Deleted catalog options for customer {customer_id}")
    except Exception as e:
        logger.error(f"Error deleting catalog options: {e}", exc_info=True)


def extract_agent_message(response_data):
    """Extract message text from the router node (always the terminal node in our graph)

    The graph architecture ensures router is always the final node that formats
    responses for the user:
    - Path 1 (Image): router → image_processor → catalog → router [END]
    - Path 2 (Order): router → order → warehouse → router [END]

    Args:
        response_data: The parsed JSON response from agent

    Returns:
        str: Extracted message text from router node
    """
    import re

    if not isinstance(response_data, str):
        logger.warning("Response data is not a string, converting to string")
        response_data = str(response_data)

    logger.info("Extracting message from agent response")

    # Pattern to match node results with their message content
    # Captures: node_name and message text
    pattern = r"'(\w+)':\s*NodeResult\(.*?message=\{'role':\s*'assistant',\s*'content':\s*\[\{'text':\s*'((?:[^'\\]|\\.)*)'\}\]"

    # Find all node matches
    all_matches = []
    for match in re.finditer(pattern, response_data, re.DOTALL):
        node_name = match.group(1)
        message_content = match.group(2)
        all_matches.append({
            'node': node_name,
            'message': message_content
        })

    if not all_matches:
        logger.error("No node results found in response")
        return "Error: Unable to process the response. Please try again."

    # Log all found nodes for debugging
    node_names = [m['node'] for m in all_matches]
    logger.info(f"Found {len(all_matches)} node results: {node_names}")

    # Always use router node (terminal node in our graph)
    router_match = next((m for m in all_matches if m['node'] == 'router'), None)

    if not router_match:
        logger.warning("Router node not found! Using last node as fallback")
        router_match = all_matches[-1]
        logger.warning(f"Fallback node: '{router_match['node']}'")
    else:
        logger.info("Using router node (terminal node)")

    extracted_text = router_match['message']

    # Unescape Python string escape sequences
    # Order matters: handle \\ first to avoid double-unescaping
    message_text = (
        extracted_text
        .replace('\\\\', '\x00')  # Temporarily replace \\ to preserve it
        .replace('\\n', '\n')
        .replace('\\t', '\t')
        .replace('\\r', '\r')
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace('\x00', '\\')  # Restore single backslash
    )

    # Remove <thinking> tags and their content
    message_text = re.sub(r'<thinking>.*?</thinking>', '', message_text, flags=re.DOTALL)
    message_text = re.sub(r'</?thinking>', '', message_text)
    # Clean up extra whitespace
    message_text = re.sub(r'\n\s*\n\s*\n', '\n\n', message_text).strip()

    logger.info(f"Extracted message length: {len(message_text)} chars")
    logger.info(f"Message preview: {message_text[:200]}...")

    return message_text


def handler(event, _context):
    """Main Lambda handler for WhatsApp messages"""
    try:
        logger.info(f"Event type: {type(event)}")
        logger.info(f"Event is: {event}")
        logger.info(f"Event stringified: {json.dumps(event)}")
        logger.info(f"Event Records: {event.get('Records')}")

        customer_message = get_customer_message_details(event)

        if not customer_message:
            logger.info("Not a customer message")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Not a customer message"}),
            }

        logger.info(f"Message received from customer. Type: {customer_message['type']}")

        # Acknowledge the message
        acknowledge(customer_message)

        # Create session ID once in handler - groups invocations within 30-minute windows
        current_time = time.time()
        time_window = int(current_time // 300)  # 1800 seconds = 30 minutes
        session_id = f"whatsapp-session-{customer_message['from']}-{time_window}"
        logger.info(f"Session ID: {session_id}")

        # Handle different message types
        if customer_message["type"] == "image":
            handle_image_message(customer_message, session_id)
        elif customer_message["type"] == "text":
            reply(customer_message, session_id)
        else:
            # Handle other message types
            logger.info(f"Unsupported message type: {customer_message['type']}")
            send_whatsapp_message(
                {
                    "messaging_product": "whatsapp",
                    "to": f"+{customer_message['from']}",
                    "text": {
                        "preview_url": False,
                        "body": "Sorry, this message type is not supported yet. Please send text or images.",
                    },
                }
            )

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Message processed successfully"}),
        }
    except Exception as error:
        logger.error(
            f"Error occurred while processing the request: {error}", exc_info=True
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": "Error occurred while processing the message"}
            ),
        }


def acknowledge(customer_message):
    """Mark message as read"""
    send_whatsapp_message(
        {
            "messaging_product": "whatsapp",
            "message_id": customer_message["id"],
            "status": "read",
        }
    )


def reply(customer_message, session_id):
    """Reply to text messages

    Args:
        customer_message: Message details from WhatsApp
        session_id: Session ID created in the handler
    """
    message_text = customer_message.get("message", "").lower().strip()
    is_greeting = message_text.startswith(("hello", "hi", "hey", "hiya"))

    if is_greeting:
        react(customer_message)
        send_options(customer_message)
    else:
        # Handle text replies - send to agent for processing
        try:
            # Acknowledge the message
            acknowledge(customer_message)

            # Invoke AgentCore with the text message
            agent_arn = get_agent_arn()

            # Retrieve catalog options from DynamoDB if available
            catalog_options = get_catalog_options(customer_message["from"])

            # Create payload with user's text message and catalog options
            payload = {
                "action": "TEXT_MESSAGE",
                "customer_id": customer_message["from"],
                "message": customer_message.get("message", ""),
            }

            # Include catalog options in payload if available
            if catalog_options:
                payload["catalog_options"] = catalog_options
                logger.info("Including catalog options in payload for router agent")

            logger.info(f"Invoking AgentCore with text message payload: {json.dumps(payload)}")
            logger.info(f"Using session ID: {session_id}")

            agent_response = agentcore.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                runtimeSessionId=session_id,
                payload=json.dumps(payload),
                qualifier="DEFAULT",
            )

            # Read and parse response
            response_body = agent_response["response"].read()
            response_data = json.loads(response_body)

            # Extract message from router node (terminal node)
            message_text = extract_agent_message(response_data)
            logger.info("Agent processing completed")

            # Delete catalog options after successful order (Path 2 - warehouse confirmation)
            if "order confirmed" in message_text.lower() or "order id:" in message_text.lower():
                logger.info("Detected order confirmation - deleting catalog options")
                delete_catalog_options(customer_message["from"])

            # Send agent response to user
            logger.info(f"About to send agent response to customer {customer_message['from']}")
            logger.info(f"Response message length: {len(message_text)} characters")
            send_whatsapp_message(
                {
                    "messaging_product": "whatsapp",
                    "to": f"+{customer_message['from']}",
                    "text": {
                        "preview_url": False,
                        "body": message_text,
                    },
                }
            )
            logger.info("Finished sending agent response")

        except Exception as error:
            logger.error(f"Error handling text message: {error}", exc_info=True)
            send_whatsapp_message(
                {
                    "messaging_product": "whatsapp",
                    "to": f"+{customer_message['from']}",
                    "text": {
                        "preview_url": False,
                        "body": "Sorry, there was an error processing your message. Please try again.",
                    },
                }
            )


def react(customer_message):
    """Send reaction emoji to message"""
    wave_emoji = "\U0001f44b"  # 👋
    send_whatsapp_message(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": f"+{customer_message['from']}",
            "type": "reaction",
            "reaction": {"message_id": customer_message["id"], "emoji": wave_emoji},
        }
    )


def send_options(customer_message):
    """Send interactive buttons to user"""
    name = customer_message.get("name") or "there"

    # Send greeting text
    send_whatsapp_message(
        {
            "messaging_product": "whatsapp",
            "to": f"+{customer_message['from']}",
            "text": {
                "preview_url": False,
                "body": f"Hello {name}! How can we help you?",
            },
        }
    )

    # Send simple text reply instead of buttons
    send_whatsapp_message(
        {
            "messaging_product": "whatsapp",
            "to": f"+{customer_message['from']}",
            "text": {
                "preview_url": False,
                "body": "Welcome! You can:\n• Send an image of your grocery list to place an order\n• Send a text message to check your order status or ask questions",
            },
        }
    )


def send_whatsapp_message(meta_message):
    """Send WhatsApp message using AWS SocialMessaging"""
    meta_api_version = "v20.0"

    logger.info("Sending WhatsApp message")
    logger.info(f"Message type: {meta_message.get('type', 'text')}")
    social_messaging.send_whatsapp_message(
        originationPhoneNumberId=PHONE_NUMBER_ID,
        message=json.dumps(meta_message),
        metaApiVersion=meta_api_version,
    )
    logger.info("WhatsApp message sent successfully")




def handle_image_message(customer_message, session_id):
    """Handle image messages

    Args:
        customer_message: Message details from WhatsApp
        session_id: Session ID created in the handler
    """
    if not customer_message.get("image") or not customer_message["image"].get("id"):
        logger.warning("No image data found in message")
        return

    try:
        logger.info(f"Receiving image with media ID: {customer_message['image']['id']}")

        # Determine file extension from MIME type
        mime_type = customer_message["image"].get("mimeType", "image/jpeg")
        extension = mime_type.split("/")[1] if "/" in mime_type else "jpg"

        # Create unique filename
        file_name = f"{customer_message['from']}/{customer_message['timestamp']}_{customer_message['id']}.{extension}"

        # Download image from WhatsApp to S3
        response = social_messaging.get_whatsapp_message_media(
            mediaId=customer_message["image"]["id"],
            originationPhoneNumberId=PHONE_NUMBER_ID,
            destinationS3File={"bucketName": MEDIA_BUCKET_NAME, "key": file_name},
        )

        # Log the full response to understand the structure
        logger.info(
            f"Full get_whatsapp_message_media response: {json.dumps(response, default=str)}"
        )

        # AWS appends a suffix to the filename, so we need to find the actual file
        # List objects in S3 with the prefix to find the actual key
        s3_response = s3.list_objects_v2(
            Bucket=MEDIA_BUCKET_NAME, Prefix=file_name, MaxKeys=1
        )
        actual_s3_key = s3_response["Contents"][0]["Key"]

        logger.info(f"Image saved successfully to S3: {actual_s3_key}")
        logger.info(
            f"File size: {response.get('fileSize')} KB, MIME type: {response.get('mimeType')}"
        )

        # Invoke AgentCore to process the grocery list
        agent_arn = get_agent_arn()

        # Create structured payload with S3 details
        payload = {
            "action": "PROCESS_IMAGE",
            "customer_id": customer_message["from"],
            "s3_bucket": MEDIA_BUCKET_NAME,
            "s3_key": actual_s3_key,
        }

        logger.info(f"Invoking AgentCore with payload: {json.dumps(payload)}")
        logger.info(f"Using session ID: {session_id}")

        agent_response = agentcore.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
            payload=json.dumps(payload),
            qualifier="DEFAULT",
        )
        # Read and parse response
        response_body = agent_response["response"].read()
        response_data = json.loads(response_body)

        # Extract message from router node (terminal node)
        message_text = extract_agent_message(response_data)
        logger.info("Agent processing completed")

        # Store catalog options for Path 1 (catalog node returns options)
        if "catalog" in str(response_data).lower() and "option 1" in message_text.lower() and "option 2" in message_text.lower():
            logger.info("Detected catalog options in response - storing for later retrieval")
            store_catalog_options(customer_message["from"], message_text)

        # Send agent response to user
        logger.info(f"About to send agent response to customer {customer_message['from']}")
        logger.info(f"Response message length: {len(message_text)} characters")
        send_whatsapp_message(
            {
                "messaging_product": "whatsapp",
                "to": f"+{customer_message['from']}",
                "text": {
                    "preview_url": False,
                    "body": message_text,
                },
            }
        )
        logger.info("Finished sending agent response")

    except Exception as error:
        logger.error(f"Error handling image message: {error}", exc_info=True)

        # Notify user of error
        send_whatsapp_message(
            {
                "messaging_product": "whatsapp",
                "to": f"+{customer_message['from']}",
                "text": {
                    "preview_url": False,
                    "body": "Sorry, there was an error processing your image. Please try again.",
                },
            }
        )


def get_customer_message_details(event):
    """Extract customer message details from SNS event"""
    try:
        eum_message = json.loads(event["Records"][0]["Sns"]["Message"])
        webhook_data = eum_message.get("whatsAppWebhookEntry")

        if isinstance(webhook_data, str):
            webhook_data_parsed = json.loads(webhook_data)
        else:
            webhook_data_parsed = webhook_data

        message_object = (
            webhook_data_parsed.get("changes", [{}])[0]
            .get("value", {})
            .get("messages", [{}])[0]
        )
        message_type = message_object.get("type")

        # Extract button response if interactive message
        button_id = None
        button_text = None
        if message_type == "interactive":
            button_reply = message_object.get("interactive", {}).get("button_reply", {})
            button_id = button_reply.get("id")
            button_text = button_reply.get("title")

        message_details = {
            "name": webhook_data_parsed.get("changes", [{}])[0]
            .get("value", {})
            .get("contacts", [{}])[0]
            .get("profile", {})
            .get("name"),
            "from": message_object.get("from"),
            "id": message_object.get("id"),
            "timestamp": message_object.get("timestamp"),
            "type": message_type,
            "message": message_object.get("text", {}).get("body"),
            "button_id": button_id,
            "button_text": button_text,
            "image": (
                {
                    "id": message_object.get("image", {}).get("id"),
                    "mimeType": message_object.get("image", {}).get("mime_type"),
                    "sha256": message_object.get("image", {}).get("sha256"),
                }
                if message_type == "image"
                else None
            ),
        }

        return message_details if message_details.get("from") else None
    except Exception as e:
        logger.error(f"Error parsing customer message: {e}", exc_info=True)
        return None
