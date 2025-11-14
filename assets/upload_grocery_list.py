from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import boto3


def create_grocery_list():
    filename = "grocery_list.pdf"

    c = canvas.Canvas(filename, pagesize=letter)

    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "Grocery List")

    c.setFont("Helvetica", 16)
    items = [
        "2 Milk",
        "1 Bread",
        "12 Eggs",
        "5 Apples",
        "1 kg Chicken",
        "2 kg Rice",
        "6 Tomatoes",
        "500g Cheese",
        "1 Butter",
        "1 Coffee",
    ]

    y = 700
    for item in items:
        c.drawString(100, y, f"• {item}")
        y -= 30

    c.save()
    print(f"Created {filename}")

    return filename


def upload_to_s3(filename):
    region = "ap-southeast-2"

    # Get bucket name from CloudFormation outputs
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stacks(StackName="OrderAssistantStack")
    outputs = response["Stacks"][0]["Outputs"]
    bucket_name = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "OrderAssistantBucketName")

    print(f"Uploading to S3 bucket: {bucket_name}")

    # Upload to S3
    s3 = boto3.client("s3", region_name=region)
    s3.upload_file(filename, bucket_name, filename)

    print(f"✓ Uploaded {filename} to s3://{bucket_name}/{filename}")
    return bucket_name


if __name__ == "__main__":
    pdf_file = create_grocery_list()
    upload_to_s3(pdf_file)
