import json
import boto3
from botocore.config import Config

config_path = r"D:\SSTRIX_MARINE_PLATFORM\config\s3.json"

with open(config_path, "r", encoding="utf-8-sig") as f:
    config = json.load(f)

identity = config["identities"][0]
credentials = identity["credentials"][0]

s3 = boto3.client(
    "s3",
    endpoint_url="http://127.0.0.1:8333",
    aws_access_key_id=credentials["accessKey"],
    aws_secret_access_key=credentials["secretKey"],
    region_name="us-east-1",
    config=Config(signature_version="s3v4")
)

try:
    response = s3.list_buckets()
    print("SUCCESS: S3 authentication worked!")
    print("Existing buckets:", [b["Name"] for b in response["Buckets"]])
except Exception as e:
    print("S3 connection test failed:", type(e).__name__, str(e))
