import boto3
from botocore.config import Config

from app.core.config import settings


s3_client = boto3.client(
    "s3",
    endpoint_url=settings.seaweedfs_endpoint,
    aws_access_key_id=settings.seaweedfs_access_key,
    aws_secret_access_key=settings.seaweedfs_secret_key,
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)


def test_storage_connection():
    response = s3_client.list_buckets()

    return [
        bucket["Name"]
        for bucket in response.get("Buckets", [])
    ]