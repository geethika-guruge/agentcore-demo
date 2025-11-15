import boto3
from decimal import Decimal

region = "ap-southeast-2"

# Get table name from CloudFormation outputs
cfn = boto3.client("cloudformation", region_name=region)
response = cfn.describe_stacks(StackName="OrderAssistantStack")
outputs = response["Stacks"][0]["Outputs"]
table_name = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "ProductCatalogTableName")

print(f"Using DynamoDB table: {table_name}\n")

dynamodb = boto3.resource("dynamodb", region_name=region)
table = dynamodb.Table(table_name)

products = [
    {
        "product_id": "MILK001",
        "name": "Full Cream Milk",
        "category": "Dairy",
        "price": Decimal("4.50"),
        "unit": "2L",
        "stock": 0,
        "description": "Fresh full cream milk",
    },
    {
        "product_id": "MILK002",
        "name": "Skim Milk",
        "category": "Dairy",
        "price": Decimal("4.20"),
        "unit": "2L",
        "stock": 120,
        "description": "Low fat skim milk",
    },
    {
        "product_id": "BREAD001",
        "name": "White Bread",
        "category": "Bakery",
        "price": Decimal("3.50"),
        "unit": "700g",
        "stock": 80,
        "description": "Fresh white bread loaf",
    },
    {
        "product_id": "BREAD002",
        "name": "Wholemeal Bread",
        "category": "Bakery",
        "price": Decimal("4.00"),
        "unit": "700g",
        "stock": 65,
        "description": "Healthy wholemeal bread",
    },
    {
        "product_id": "EGG001",
        "name": "Free Range Eggs",
        "category": "Dairy",
        "price": Decimal("7.50"),
        "unit": "12 pack",
        "stock": 200,
        "description": "Free range eggs",
    },
    {
        "product_id": "APPLE001",
        "name": "Royal Gala Apples",
        "category": "Fruit",
        "price": Decimal("5.99"),
        "unit": "1kg",
        "stock": 300,
        "description": "Sweet Royal Gala apples",
    },
    {
        "product_id": "APPLE002",
        "name": "Granny Smith Apples",
        "category": "Fruit",
        "price": Decimal("4.99"),
        "unit": "1kg",
        "stock": 250,
        "description": "Tart Granny Smith apples",
    },
    {
        "product_id": "CHICKEN001",
        "name": "Chicken Breast",
        "category": "Meat",
        "price": Decimal("12.99"),
        "unit": "1kg",
        "stock": 100,
        "description": "Fresh chicken breast fillets",
    },
    {
        "product_id": "CHICKEN002",
        "name": "Chicken Thighs",
        "category": "Meat",
        "price": Decimal("9.99"),
        "unit": "1kg",
        "stock": 85,
        "description": "Fresh chicken thigh fillets",
    },
    {
        "product_id": "RICE001",
        "name": "Jasmine Rice",
        "category": "Pantry",
        "price": Decimal("8.50"),
        "unit": "2kg",
        "stock": 150,
        "description": "Premium jasmine rice",
    },
    {
        "product_id": "RICE002",
        "name": "Basmati Rice",
        "category": "Pantry",
        "price": Decimal("9.99"),
        "unit": "2kg",
        "stock": 120,
        "description": "Aromatic basmati rice",
    },
    {
        "product_id": "TOMATO001",
        "name": "Tomatoes",
        "category": "Vegetables",
        "price": Decimal("6.99"),
        "unit": "1kg",
        "stock": 180,
        "description": "Fresh ripe tomatoes",
    },
    {
        "product_id": "CHEESE001",
        "name": "Cheddar Cheese",
        "category": "Dairy",
        "price": Decimal("10.99"),
        "unit": "500g",
        "stock": 75,
        "description": "Tasty cheddar cheese block",
    },
    {
        "product_id": "CHEESE002",
        "name": "Mozzarella Cheese",
        "category": "Dairy",
        "price": Decimal("8.99"),
        "unit": "500g",
        "stock": 60,
        "description": "Fresh mozzarella cheese",
    },
    {
        "product_id": "BUTTER001",
        "name": "Salted Butter",
        "category": "Dairy",
        "price": Decimal("5.50"),
        "unit": "500g",
        "stock": 90,
        "description": "Salted butter block",
    },
    {
        "product_id": "COFFEE001",
        "name": "Ground Coffee",
        "category": "Pantry",
        "price": Decimal("12.99"),
        "unit": "500g",
        "stock": 110,
        "description": "Medium roast ground coffee",
    },
    {
        "product_id": "COFFEE002",
        "name": "Instant Coffee",
        "category": "Pantry",
        "price": Decimal("8.99"),
        "unit": "200g",
        "stock": 95,
        "description": "Premium instant coffee",
    },
]

print(f"Populating {len(products)} products into DynamoDB table...")

with table.batch_writer() as batch:
    for product in products:
        batch.put_item(Item=product)
        print(f"  ✓ Added: {product['name']} ({product['product_id']})")

print(f"\n✅ Successfully populated {len(products)} products!")
print(f"\nCategories:")
categories = set(p["category"] for p in products)
for cat in sorted(categories):
    count = len([p for p in products if p["category"] == cat])
    print(f"  - {cat}: {count} products")
