"""
Lambda function to populate the PostgreSQL RDS instance with product data.
This function is deployed in the same VPC as the RDS instance to have network access.
"""

import json
import os
import boto3
import psycopg2
from psycopg2.extras import execute_values


def get_db_credentials():
    """Retrieve database credentials from Secrets Manager."""
    secret_arn = os.environ["POSTGRES_SECRET_ARN"]
    region = os.environ.get("AWS_REGION", "ap-southeast-2")

    secrets_client = boto3.client("secretsmanager", region_name=region)
    secret_response = secrets_client.get_secret_value(SecretId=secret_arn)
    credentials = json.loads(secret_response["SecretString"])

    return credentials["username"], credentials["password"]


def get_products():
    """Return the list of products to insert - Restaurant/Wholesale Catalog."""
    return [
        {
            "product_id": "PROD-001",
            "name": "Romaine lettuce",
            "category": "Fresh Produce",
            "price": 48.99,
            "description": "Premium quality, fresh Romaine lettuce heads. Each case contains 24 carefully selected heads, triple-washed and individually wrapped. Ideal for restaurants, salad bars, and food service operations. Sourced from certified organic farms with consistent size and excellent shelf life.",
            "stock_level": 150,
        },
        {
            "product_id": "PROD-002",
            "name": "Chicken breasts",
            "category": "Poultry",
            "price": 89.99,
            "description": "Restaurant-grade, boneless, skinless chicken breasts. Each piece is hand-trimmed, portion-controlled (6-8 oz each), and individually vacuum-sealed. USDA Grade A, hormone-free, and air-chilled. Perfect for consistent portion control and easy inventory management.",
            "stock_level": 0,
        },
        {
            "product_id": "PROD-003",
            "name": "Salmon fillets",
            "category": "Seafood",
            "price": 159.99,
            "description": "Premium center-cut Atlantic salmon fillets, skin-on and pin-bone removed. Each fillet is precisely cut to 6-8 oz portions and individually vacuum-sealed. Farm-raised in cold Norwegian waters, certified sustainable, and delivered fresh never frozen. Ideal for fine dining establishments.",
            "stock_level": 85,
        },
        {
            "product_id": "PROD-004",
            "name": "Butter (unsalted)",
            "category": "Dairy",
            "price": 75.99,
            "description": "Premium European-style butter with 82% butterfat content. Perfect for baking, sauce making, and culinary applications requiring high-quality butter. Each case contains 40 quarter-pound blocks, individually wrapped. Made from pasteurized cream from grass-fed cows.",
            "stock_level": 120,
        },
        {
            "product_id": "PROD-005",
            "name": "All-purpose flour",
            "category": "Baking & Pastry",
            "price": 32.99,
            "description": "Professional-grade all-purpose flour milled from selected hard and soft wheat varieties. Consistent 10.5% protein content ideal for multiple applications. Unbleached, unbromated, and certified kosher. Perfect for bakeries, restaurants, and institutional kitchens.",
            "stock_level": 300,
        },
        {
            "product_id": "PROD-006",
            "name": "Sourdough Bread - Case of 5",
            "category": "Bakery",
            "price": 45.99,
            "description": "Handcrafted artisanal sourdough bread made with 100-year-old starter. Each loaf is naturally leavened for 24 hours, hearth-baked, and features a robust crust with complex flavor profile. Par-baked and flash-frozen to preserve quality. Perfect for high-end restaurants and cafes.",
            "stock_level": 95,
        },
        {
            "product_id": "PROD-007",
            "name": "Coffee Beans",
            "category": "Beverages",
            "price": 89.99,
            "description": "Premium single-origin Arabica coffee beans from Ethiopian Yirgacheffe region. Medium roast with notes of bergamot, jasmine, and citrus. Roasted in small batches and packed immediately to ensure maximum freshness. Fair Trade certified and organic. Ideal for specialty coffee shops and restaurants.",
            "stock_level": 175,
        },
        {
            "product_id": "PROD-008",
            "name": "Gourmet Dijon Mustard - 1 Gallon Jar",
            "category": "Condiments",
            "price": 29.99,
            "description": "Authentic French Dijon mustard made with brown mustard seeds and white wine. Smooth, creamy texture with balanced heat and acidity. Perfect for dressings, marinades, and sauce applications. Contains no artificial preservatives or flavors. Essential for professional kitchens.",
            "stock_level": 250,
        },
        {
            "product_id": "PROD-009",
            "name": "Aged Balsamic Vinegar - 5L Container",
            "category": "Condiments",
            "price": 189.99,
            "description": "Premium aged balsamic vinegar from Modena, Italy. Aged for 12 years in wooden barrels with perfect balance of sweetness and acidity. IGP certified with optimal density for glazing and finishing dishes. Ideal for fine dining establishments and gourmet food preparation.",
            "stock_level": 60,
        },
        {
            "product_id": "PROD-010",
            "name": "Wild Mushroom Blend - 5 lb Case",
            "category": "Specialty Produce",
            "price": 249.99,
            "description": "Premium selection of wild mushrooms including porcini, chanterelles, and morels. Carefully cleaned, flash-frozen at peak freshness, and IQF packaged for easy portion control. Each variety hand-foraged from sustainable sources. Perfect for high-end restaurants and specialty cuisine.",
            "stock_level": 45,
        },
        {
            "product_id": "PROD-011",
            "name": "Chicken thighs",
            "category": "Poultry",
            "price": 79.99,
            "description": "Premium bone-in, skin-on chicken thighs. Each piece is carefully selected for consistent size (6-8 oz each) and vacuum-sealed for freshness. USDA Grade A, hormone-free, and air-chilled. Perfect for roasting, braising, and grilling applications in professional kitchens.",
            "stock_level": 180,
        },
    ]


def handler(event, context):
    """Lambda handler to populate the database."""

    # Get environment variables
    db_host = os.environ["POSTGRES_HOST"]
    db_port = os.environ["POSTGRES_PORT"]
    db_name = os.environ["POSTGRES_DB"]

    # Check operation mode
    operation = event.get("operation", "insert")  # Options: "insert" or "select"
    clear_existing = event.get("clear_existing", False)

    try:
        # Get credentials
        print("Retrieving database credentials...")
        db_username, db_password = get_db_credentials()

        # Connect to database
        print(f"Connecting to database at {db_host}:{db_port}...")
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_username,
            password=db_password,
            connect_timeout=10,
        )
        cursor = conn.cursor()
        print("Connected successfully!")

        # If operation is "select", just display the catalog and return
        if operation == "select":
            print("Operation: SELECT - Displaying product catalog...")

            # Check if table exists
            cursor.execute(
                """
                SELECT COUNT(*) FROM product_catalog
            """
            )
            total_count = cursor.fetchone()[0]

            if total_count == 0:
                message = "No products found in the catalog."
                print(message)
                cursor.close()
                conn.close()
                return {
                    "statusCode": 200,
                    "body": json.dumps({"message": message, "total_products": 0}),
                }

            # Retrieve and display all products
            print("\n" + "=" * 80)
            print("PRODUCT CATALOG - ALL ITEMS")
            print("=" * 80)
            cursor.execute(
                """
                SELECT product_id, product_name, product_category, product_price, product_description, stock_level
                FROM product_catalog
                ORDER BY product_category, product_name
            """
            )
            all_products = cursor.fetchall()

            catalog_list = []
            for product in all_products:
                product_id, name, category, price, description, stock_level = product
                print(f"\n{product_id} | {name}")
                print(f"  Category: {category}")
                print(f"  Price: ${price}")
                print(f"  Stock Level: {stock_level}")
                print(f"  Description: {description}")

                catalog_list.append(
                    {
                        "product_id": product_id,
                        "product_name": name,
                        "product_category": category,
                        "product_price": float(price),
                        "product_description": description,
                        "stock_level": stock_level,
                    }
                )

            print("\n" + "=" * 80)

            cursor.close()
            conn.close()

            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": f"Retrieved {len(catalog_list)} products",
                        "total_products": len(catalog_list),
                        "products": catalog_list,
                    }
                ),
            }

        # Create product_catalog table if it doesn't exist (for insert operation)
        print("Operation: INSERT - Populating product catalog...")
        print("Creating product_catalog table if it doesn't exist...")
        drop_table_query = "DROP TABLE IF EXISTS product_catalog;"
        cursor.execute(drop_table_query)
        conn.commit()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS product_catalog (
            id SERIAL PRIMARY KEY,
            product_id VARCHAR(50) UNIQUE NOT NULL,
            product_name VARCHAR(255) NOT NULL,
            product_description TEXT,
            product_category VARCHAR(100) NOT NULL,
            product_price DECIMAL(10, 2) NOT NULL,
            stock_level INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_query)
        conn.commit()
        print("Product catalog table created/verified")

        # Check existing data
        cursor.execute("SELECT COUNT(*) FROM product_catalog")
        existing_count = cursor.fetchone()[0]
        print(f"Found {existing_count} existing products in the database")

        if existing_count > 0 and clear_existing:
            print("Clearing existing products...")
            cursor.execute("DELETE FROM product_catalog")
            conn.commit()
            print("Existing products deleted")
        elif existing_count > 0:
            message = f"Database already contains {existing_count} products. Pass 'clear_existing': true in the event to clear them first."
            print(message)
            cursor.close()
            conn.close()
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": message,
                        "existing_count": existing_count,
                        "inserted": 0,
                    }
                ),
            }

        # Insert products
        products = get_products()
        print(f"Inserting {len(products)} products...")

        insert_query = """
        INSERT INTO product_catalog (product_id, product_name, product_category, product_price, product_description, stock_level)
        VALUES %s
        ON CONFLICT (product_id) DO UPDATE SET
            product_name = EXCLUDED.product_name,
            product_category = EXCLUDED.product_category,
            product_price = EXCLUDED.product_price,
            product_description = EXCLUDED.product_description,
            stock_level = EXCLUDED.stock_level,
            updated_at = CURRENT_TIMESTAMP
        """

        values = [
            (
                p["product_id"],
                p["name"],
                p["category"],
                p["price"],
                p["description"],
                p["stock_level"],
            )
            for p in products
        ]

        execute_values(cursor, insert_query, values)
        conn.commit()

        print(f"Successfully inserted/updated {len(products)} products")

        # Get category summary
        categories = {}
        for p in products:
            categories[p["category"]] = categories.get(p["category"], 0) + 1

        # Verify data
        cursor.execute("SELECT COUNT(*) FROM product_catalog")
        final_count = cursor.fetchone()[0]

        # Retrieve and display all products in the catalog
        print("\n" + "=" * 80)
        print("PRODUCT CATALOG - ALL ITEMS")
        print("=" * 80)
        cursor.execute(
            """
            SELECT product_id, product_name, product_category, product_price, product_description, stock_level
            FROM product_catalog
            ORDER BY product_category, product_name
        """
        )
        all_products = cursor.fetchall()

        for product in all_products:
            product_id, name, category, price, description, stock_level = product
            print(f"\n{product_id} | {name}")
            print(f"  Category: {category}")
            print(f"  Price: ${price}")
            print(f"  Stock Level: {stock_level}")
            print(f"  Description: {description}")

        print("\n" + "=" * 80)

        cursor.close()
        conn.close()

        result = {
            "message": f"Successfully populated {len(products)} products",
            "total_products": final_count,
            "categories": categories,
            "inserted": len(products),
        }

        print(json.dumps(result, indent=2))

        return {"statusCode": 200, "body": json.dumps(result)}

    except Exception as e:
        error_message = f"Error populating database: {str(e)}"
        print(error_message)
        import traceback

        traceback.print_exc()

        return {"statusCode": 500, "body": json.dumps({"error": error_message})}
