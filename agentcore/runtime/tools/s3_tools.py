import os
import boto3
from strands import tool

s3_client = boto3.client("s3")


@tool(name="download_image_from_s3", description="Download files from Amazon S3 bucket")
def download_image_from_s3(bucket: str, key: str) -> str:
    """
    Download an image from S3 to a temporary location.

    Args:
        bucket: S3 bucket name
        key: S3 object key (e.g., 'grocery_list.pdf')

    Returns:
        Local file path where the image was downloaded
    """
    # Use /tmp directory which is writable in Lambda/container environments
    filename = os.path.basename(key)
    download_path = os.path.join("/tmp", filename)

    s3_client.download_file(bucket, key, download_path)

    return download_path
