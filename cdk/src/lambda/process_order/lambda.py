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

# Cached values
AGENT_ARN = None


def get_agent_arn():
    """Retrieve agent ARN from SSM parameter"""
    global AGENT_ARN
    if AGENT_ARN is None:
        response = ssm.get_parameter(Name=AGENT_ARN_PARAM)
        AGENT_ARN = response["Parameter"]["Value"]
        logger.info(f"Retrieved agent ARN from SSM: {AGENT_ARN}")
    return AGENT_ARN


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

        # Handle different message types
        if customer_message["type"] == "image":
            handle_image_message(customer_message)
        elif customer_message["type"] == "text":
            reply(customer_message)
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


def reply(customer_message):
    """Reply to text messages"""
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
            # Create session ID that groups invocations within 10-minute windows
            current_time = time.time()
            time_window = int(current_time // 600)  # 600 seconds = 10 minutes
            session_id = f"whatsapp-session-{customer_message['from']}-{time_window}"

            # Create payload with user's text message
            payload = {
                "action": "TEXT_MESSAGE",
                "customer_id": customer_message["from"],
                "message": customer_message.get("message", ""),
            }

            logger.info(f"Invoking AgentCore with text message payload: {json.dumps(payload)}")

            agent_response = agentcore.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                runtimeSessionId=session_id,
                payload=json.dumps(payload),
                qualifier="DEFAULT",
            )

            response_body = agent_response["response"].read()
            response_data = json.loads(response_body)
            logger.info("Agent processing completed")

            # Send agent response to user
            send_whatsapp_message(
                {
                    "messaging_product": "whatsapp",
                    "to": f"+{customer_message['from']}",
                    "text": {
                        "preview_url": False,
                        "body": f"{response_data}",
                    },
                }
            )

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

    logger.debug("Send message request")
    social_messaging.send_whatsapp_message(
        originationPhoneNumberId=PHONE_NUMBER_ID,
        message=json.dumps(meta_message),
        metaApiVersion=meta_api_version,
    )
    logger.debug("Send message complete")




def handle_image_message(customer_message):
    """Handle image messages"""
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
        # Session ID must be at least 33 characters
        # Create session ID that groups invocations within 10-minute windows
        current_time = time.time()
        time_window = int(current_time // 600)  # 600 seconds = 10 minutes
        session_id = f"whatsapp-session-{customer_message['from']}-{time_window}"

        # Create structured payload with S3 details
        payload = {
            "action": "PROCESS_IMAGE",
            "customer_id": customer_message["from"],
            "s3_bucket": MEDIA_BUCKET_NAME,
            "s3_key": actual_s3_key,
        }

        logger.info(f"Invoking AgentCore with payload: {json.dumps(payload)}")

        agent_response = agentcore.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
            payload=json.dumps(payload),
            qualifier="DEFAULT",
        )

        response_body = agent_response["response"].read()
        response_data = json.loads(response_body)
        logger.info("Agent processing completed")

        # Send agent response to user
        send_whatsapp_message(
            {
                "messaging_product": "whatsapp",
                "to": f"+{customer_message['from']}",
                "text": {
                    "preview_url": False,
                    "body": f"{response_data}",
                },
            }
        )

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
