"""
Lambda handler for Custom DynamoDB Tools
This Lambda function provides custom tools for order management
"""

import json
import os
import boto3
import logging
from datetime import datetime
from decimal import Decimal

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")


def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def convert_floats_to_decimal(obj):
    """
    Recursively convert all float values to Decimal for DynamoDB compatibility
    """
    if isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_floats_to_decimal(value) for key, value in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj


def place_order(customer_id, items, total_amount):
    """
    Place a new order in the orders table.
    Args:
        customer_id (str): Unique identifier for the customer (mobile number)
        items (list): List of order items with product details
        total_amount (float): Total order amount
    Returns:
        dict: Order confirmation with order_id and details
    """
    logger.info(f"Placing order for customer: {customer_id}")

    try:
        table_name = os.environ.get("ORDERS_TABLE_NAME")
        if not table_name:
            raise ValueError("ORDERS_TABLE_NAME environment variable not set")

        table = dynamodb.Table(table_name)

        # Generate order ID
        timestamp = datetime.utcnow()
        order_id = f"ORD-{timestamp.strftime('%Y%m%d%H%M%S')}-{customer_id[:8]}"

        # Convert all float values to Decimal for DynamoDB
        items_decimal = convert_floats_to_decimal(items)
        total_amount_decimal = Decimal(str(total_amount)) if isinstance(total_amount, (int, float)) else total_amount

        # Prepare order item - only store customer_id, order_id, items, total, status, and timestamps
        order = {
            "order_id": order_id,
            "customer_id": customer_id,
            "items": items_decimal,
            "total_amount": total_amount_decimal,
            "order_status": "PENDING",
            "created_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
        }

        # Put item in DynamoDB
        table.put_item(Item=order)

        logger.info(f"Order placed successfully: {order_id}")

        # Return confirmation (convert Decimal for JSON serialization)
        return {
            "order_id": order_id,
            "customer_id": customer_id,
            "total_amount": float(total_amount),
            "order_status": "PENDING",
            "created_at": timestamp.isoformat(),
            "message": f"Order {order_id} placed successfully",
        }

    except Exception as e:
        logger.error(f"Error placing order: {str(e)}", exc_info=True)
        raise


def get_order(order_id):
    """
    Retrieve order details by order_id.
    Args:
        order_id (str): The order ID to retrieve
    Returns:
        dict: Order details
    """
    logger.info(f"Retrieving order: {order_id}")

    try:
        table_name = os.environ.get("ORDERS_TABLE_NAME")
        if not table_name:
            raise ValueError("ORDERS_TABLE_NAME environment variable not set")

        table = dynamodb.Table(table_name)

        response = table.get_item(Key={"order_id": order_id})

        if "Item" not in response:
            logger.info(f"Order not found: {order_id}")
            return {"error": f"Order {order_id} not found"}

        order = response["Item"]
        logger.info(f"Order retrieved successfully: {order_id}")

        # Convert Decimal to float for JSON serialization
        return json.loads(json.dumps(order, default=decimal_default))

    except Exception as e:
        logger.error(f"Error retrieving order: {str(e)}", exc_info=True)
        raise


def update_order_status(order_id, new_status):
    """
    Update the status of an existing order.
    Args:
        order_id (str): The order ID to update
        new_status (str): New status (e.g., CONFIRMED, PROCESSING, SHIPPED, DELIVERED, CANCELLED)
    Returns:
        dict: Updated order details
    """
    logger.info(f"Updating order {order_id} status to {new_status}")

    try:
        table_name = os.environ.get("ORDERS_TABLE_NAME")
        if not table_name:
            raise ValueError("ORDERS_TABLE_NAME environment variable not set")

        table = dynamodb.Table(table_name)

        # Update the order status
        response = table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET order_status = :status, updated_at = :updated",
            ExpressionAttributeValues={
                ":status": new_status,
                ":updated": datetime.utcnow().isoformat(),
            },
            ReturnValues="ALL_NEW",
        )

        if "Attributes" not in response:
            logger.warning(f"Order not found for update: {order_id}")
            return {"error": f"Order {order_id} not found"}

        updated_order = response["Attributes"]
        logger.info(f"Order status updated successfully: {order_id}")

        # Convert Decimal to float for JSON serialization
        return json.loads(json.dumps(updated_order, default=decimal_default))

    except Exception as e:
        logger.error(f"Error updating order status: {str(e)}", exc_info=True)
        raise


def get_customer_postcode(customer_id):
    """
    Retrieve customer's postcode by customer_id.
    Args:
        customer_id (str): The customer ID (mobile number) to retrieve
    Returns:
        dict: Customer details with postcode
    """
    logger.info(f"Retrieving customer postcode: {customer_id}")

    try:
        table_name = os.environ.get("CUSTOMERS_TABLE_NAME")
        if not table_name:
            raise ValueError("CUSTOMERS_TABLE_NAME environment variable not set")

        table = dynamodb.Table(table_name)

        response = table.get_item(Key={"customer_id": customer_id})

        if "Item" not in response:
            logger.info(f"Customer not found: {customer_id}")
            return {
                "error": f"Customer {customer_id} not found",
                "customer_id": customer_id,
                "postcode": None
            }

        customer = response["Item"]
        logger.info(f"Customer retrieved successfully: {customer_id}, postcode: {customer.get('postcode')}")

        return {
            "customer_id": customer_id,
            "postcode": customer.get("postcode"),
            "message": f"Customer {customer_id} has postcode {customer.get('postcode')}"
        }

    except Exception as e:
        logger.error(f"Error retrieving customer: {str(e)}", exc_info=True)
        raise


def get_available_delivery_slots(start_date=None, end_date=None, postcode=None, status_filter=None, earliest_only=True):
    """
    Retrieve available delivery slots from the delivery slots table.

    Args:
        start_date (str, optional): Start date for the query (YYYY-MM-DD format)
        end_date (str, optional): End date for the query (YYYY-MM-DD format)
        postcode (str, optional): Postcode to filter slots by coverage area
        status_filter (str, optional): Filter by slot status (available, fully_booked, blocked).
                                       If None, returns all active slots.
        earliest_only (bool, optional): If True, returns only the earliest available slot. Defaults to True.

    Returns:
        dict: Single earliest slot (if earliest_only=True) or list of available delivery slots
    """
    logger.info(f"Retrieving delivery slots - start_date: {start_date}, end_date: {end_date}, postcode: {postcode}, status: {status_filter}, earliest_only: {earliest_only}")

    try:
        table_name = os.environ.get("DELIVERY_SLOTS_TABLE_NAME")
        if not table_name:
            raise ValueError("DELIVERY_SLOTS_TABLE_NAME environment variable not set")

        table = dynamodb.Table(table_name)

        # If no date range specified, default to today and next 7 days
        if not start_date:
            start_date = datetime.utcnow().strftime('%Y-%m-%d')
        if not end_date:
            from datetime import timedelta
            end_date_obj = datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=7)
            end_date = end_date_obj.strftime('%Y-%m-%d')

        logger.info(f"Querying slots from {start_date} to {end_date}")

        # Query using GSI for date-based lookup
        filter_expression = None
        expression_values = {}

        # Use the DateStatusIndex GSI if we're filtering by status
        if status_filter:
            # Query with GSI for efficient date + status filtering
            # GSI has slot_status as partition key, slot_date as sort key
            response = table.query(
                IndexName='DateStatusIndex',
                KeyConditionExpression='slot_status = :status AND slot_date BETWEEN :start_date AND :end_date',
                ExpressionAttributeValues={
                    ':status': status_filter,
                    ':start_date': start_date,
                    ':end_date': end_date,
                }
            )
        else:
            # Scan with date filter if no status specified
            from boto3.dynamodb.conditions import Attr, And

            conditions = [
                Attr('slot_date').between(start_date, end_date),
                Attr('is_active').eq(True)
            ]

            filter_expression = And(*conditions)
            response = table.scan(FilterExpression=filter_expression)

        slots = response.get('Items', [])

        # Filter by postcode if specified
        if postcode:
            filtered_slots = []
            for slot in slots:
                postcodes_covered = slot.get('postcode_coverage', '').split(',')
                postcodes_covered = [pc.strip() for pc in postcodes_covered]
                if postcode in postcodes_covered:
                    filtered_slots.append(slot)
            slots = filtered_slots

        # Sort by date and start time
        slots.sort(key=lambda x: (x.get('slot_date', ''), x.get('start_time', '')))

        logger.info(f"Found {len(slots)} delivery slots")

        # Convert Decimal to float for JSON serialization
        slots_json = json.loads(json.dumps(slots, default=decimal_default))

        # If earliest_only is True, return only the first slot
        if earliest_only and len(slots_json) > 0:
            earliest_slot = slots_json[0]
            logger.info(f"Returning earliest slot only: {earliest_slot['slot_date']} {earliest_slot['start_time']}-{earliest_slot['end_time']}")
            return {
                "earliest_slot": earliest_slot,
                "slot_date": earliest_slot['slot_date'],
                "start_time": earliest_slot['start_time'],
                "end_time": earliest_slot['end_time'],
                "slot_id": earliest_slot['slot_id'],
                "postcode_coverage": earliest_slot.get('postcode_coverage', ''),
                "message": f"Earliest available delivery slot: {earliest_slot['slot_date']} from {earliest_slot['start_time']} to {earliest_slot['end_time']}"
            }
        elif earliest_only and len(slots_json) == 0:
            logger.warning("No delivery slots available")
            return {
                "earliest_slot": None,
                "message": "No delivery slots available for the specified criteria",
                "query_params": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "postcode": postcode,
                    "status_filter": status_filter,
                }
            }

        # Otherwise return all slots
        return {
            "count": len(slots_json),
            "query_params": {
                "start_date": start_date,
                "end_date": end_date,
                "postcode": postcode,
                "status_filter": status_filter,
            },
            "slots": slots_json,
        }

    except Exception as e:
        logger.error(f"Error retrieving delivery slots: {str(e)}", exc_info=True)
        raise


def handler(event, context):
    """
    Lambda handler - Gateway sends tool parameters directly in event
    Event formats:
    - place_order: {"customer_id": "...", "items": [...], "total_amount": 123.45}
    - get_order: {"order_id": "ORD-..."}
    - update_order_status: {"order_id": "ORD-...", "new_status": "CONFIRMED"}
    - get_customer_postcode: {"customer_id": "..."}
    - get_available_delivery_slots: {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "postcode": "SW1A", "status_filter": "available"}
    """
    logger.info("=== DynamoDB Custom Tools Lambda Handler Started ===")
    logger.info(f"Request ID: {context.aws_request_id}")
    logger.info(f"Event: {json.dumps(event, default=str)}")

    try:
        # Check for get_available_delivery_slots first (uses optional params)
        if "query_delivery_slots" in event or any(k in event for k in ["start_date", "end_date", "postcode", "status_filter", "earliest_only"]) and "order_id" not in event and "customer_id" not in event:
            # get_available_delivery_slots
            logger.info("Tool: get_available_delivery_slots")
            start_date = event.get("start_date")
            end_date = event.get("end_date")
            postcode = event.get("postcode")
            status_filter = event.get("status_filter")
            earliest_only = event.get("earliest_only", True)  # Default to True

            result = get_available_delivery_slots(start_date, end_date, postcode, status_filter, earliest_only)

        # Check for get_customer_postcode (customer_id only, no items)
        elif "customer_id" in event and "items" not in event and "order_id" not in event:
            # get_customer_postcode
            logger.info("Tool: get_customer_postcode")
            customer_id = event.get("customer_id")

            if not customer_id:
                raise ValueError("customer_id is required")

            result = get_customer_postcode(customer_id)

        # Determine which tool based on event content
        elif "customer_id" in event and "items" in event:
            # place_order
            logger.info("Tool: place_order")
            customer_id = event.get("customer_id")
            items = event.get("items", [])
            total_amount = event.get("total_amount")

            if not customer_id or not items or total_amount is None:
                raise ValueError("customer_id, items, and total_amount are required")

            result = place_order(customer_id, items, total_amount)

        elif "order_id" in event and "new_status" in event:
            # update_order_status
            logger.info("Tool: update_order_status")
            order_id = event.get("order_id")
            new_status = event.get("new_status")

            if not order_id or not new_status:
                raise ValueError("order_id and new_status are required")

            result = update_order_status(order_id, new_status)

        elif "order_id" in event:
            # get_order
            logger.info("Tool: get_order")
            order_id = event.get("order_id")

            if not order_id:
                raise ValueError("order_id is required")

            result = get_order(order_id)

        else:
            # Unknown format
            logger.error("Unknown event format")
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {
                        "error": "Invalid request format",
                        "expected": "One of: place_order, get_order, update_order_status, get_customer_postcode, get_available_delivery_slots",
                        "received_keys": list(event.keys()),
                    }
                ),
            }

        logger.info(f"✓ Tool execution successful")

        # Return simple JSON response
        return {
            "statusCode": 200,
            "body": json.dumps(result, default=decimal_default),
        }

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        return {
            "statusCode": 400,
            "body": json.dumps(
                {
                    "error": "Validation error",
                    "details": str(e),
                }
            ),
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": str(e),
                    "type": type(e).__name__,
                }
            ),
        }
