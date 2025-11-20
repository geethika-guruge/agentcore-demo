"""
Lambda handler for Custom PostgreSQL Tools
This Lambda function provides custom tools for product catalog queries
"""

import json
import os
import boto3
import logging
import psycopg2

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_client = boto3.client("secretsmanager")


def get_db_credentials():
    """Retrieve database credentials from Secrets Manager"""
    logger.info("Retrieving database credentials from Secrets Manager")
    secret_arn = os.environ.get("POSTGRES_SECRET_ARN")
    if not secret_arn:
        logger.error("POSTGRES_SECRET_ARN environment variable not set")
        raise ValueError("POSTGRES_SECRET_ARN environment variable not set")

    logger.info(f"Fetching secret from ARN: {secret_arn}")
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response["SecretString"])

    logger.info(f"Successfully retrieved credentials for user: {secret['username']}")
    return {
        "host": os.environ.get("POSTGRES_HOST"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "database": os.environ.get("POSTGRES_DB"),
        "user": secret["username"],
        "password": secret["password"],
    }


def get_database_connection():
    """Establish database connection"""
    try:
        credentials = get_db_credentials()

        logger.info(
            f"Connecting to database: {credentials['host']}:{credentials['port']}/{credentials['database']}"
        )
        conn = psycopg2.connect(
            host=credentials["host"],
            port=credentials["port"],
            database=credentials["database"],
            user=credentials["user"],
            password=credentials["password"],
        )
        logger.info("✓ Database connection established")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}", exc_info=True)
        raise


def search_products_by_product_names(product_names):
    """
    Search for multiple products by their names in the product_catalog table.
    Args:
        product_names (list): List of product names to search for
    Returns:
        list: List of matching products with details
    """
    logger.info(f"Searching for products: {product_names}")

    try:
        conn = get_database_connection()
        cursor = conn.cursor()

        search_query = """
        SELECT
            id,
            product_id,
            product_name,
            product_description,
            product_category,
            product_price,
            stock_level
        FROM product_catalog
        WHERE LOWER(product_name) LIKE ANY(%s)
        ORDER BY product_category, product_name;
        """

        search_patterns = [f"%{name.lower()}%" for name in product_names]
        cursor.execute(search_query, (search_patterns,))
        results = cursor.fetchall()

        cursor.close()
        conn.close()

        if not results:
            logger.info("No products found matching the search criteria")
            return []

        formatted_results = []
        for row in results:
            product = {
                "product_name": row[2],
                "product_description": row[3],
                "product_category": row[4],
                "price": float(row[5]),
                "stock_level": row[6],
            }
            formatted_results.append(product)

        logger.info(f"Found {len(formatted_results)} matching products")
        return formatted_results

    except Exception as e:
        logger.error(f"Error searching products: {str(e)}", exc_info=True)
        raise


def list_product_catalogue():
    """Retrieve all products from the catalogue"""
    logger.info("Retrieving all products from catalogue")

    try:
        conn = get_database_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT product_id, product_name, product_description, product_category, product_price, stock_level
            FROM public.product_catalog
            ORDER BY product_category, product_name
            """
        )
        results = cursor.fetchall()

        cursor.close()
        conn.close()

        if not results:
            logger.info("No products found in catalogue")
            return []

        formatted_results = []
        for row in results:
            product = {
                "product_name": row[1],
                "product_description": row[2],
                "product_category": row[3],
                "price": float(row[4]),
                "stock_level": row[5],
            }
            formatted_results.append(product)

        logger.info(f"Retrieved {len(formatted_results)} products from catalogue")
        return formatted_results

    except Exception as e:
        logger.error(f"Error retrieving catalogue: {str(e)}", exc_info=True)
        raise


def handler(event, context):
    """
    Lambda handler - Gateway sends tool parameters directly in event
    Event formats:
    - search_products_by_product_names: {"product_names": ["milk", "bread"]}
    - list_product_catalogue: {} (empty)
    """
    logger.info("=== PostgreSQL Custom Tools Lambda Handler Started ===")
    logger.info(f"Request ID: {context.aws_request_id}")
    logger.info(f"Event: {json.dumps(event, default=str)}")

    try:
        # Determine which tool based on event content
        if "product_names" in event:
            # search_products_by_product_names
            logger.info("Tool: search_products_by_product_names")
            product_names = event.get("product_names", [])

            if not product_names:
                raise ValueError("product_names parameter is required")

            result = search_products_by_product_names(product_names)

        elif not event or event == {}:
            # list_product_catalogue (empty event)
            logger.info("Tool: list_product_catalogue")
            result = list_product_catalogue()

        else:
            # Unknown format
            logger.error(f"Unknown event format")
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {
                        "error": "Invalid request format",
                        "expected": "Either {'product_names': [...]} or empty {}",
                        "received_keys": list(event.keys()),
                    }
                ),
            }

        logger.info(f"✓ Tool execution successful, returning {len(result)} results")

        # Return simple JSON response
        return {
            "statusCode": 200,
            "body": json.dumps(result),
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
