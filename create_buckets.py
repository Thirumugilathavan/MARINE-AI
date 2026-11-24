import json
import boto3
from botocore.config import Config

path = r"D:\SSTRIX_MARINE_PLATFORM\config\s3.json"

with open(path, encoding="utf-8-sig") as f:
    cfg = json.load(f)

cred = cfg["identities"][0]["credentials"][0]

s3 = boto3.client(
    "s3",
    endpoint_url="http://127.0.0.1:8333",
    aws_access_key_id=cred["accessKey"],
    aws_secret_access_key=cred["secretKey"],
    region_name="us-east-1",
    config=Config(signature_version="s3v4")
)

buckets = [
    "marine-raw",
    "marine-curated",
    "marine-derived",
    "marine-media",
    "marine-edna",
    "marine-models",
    "marine-research"
]

for bucket in buckets:
    s3.create_bucket(Bucket=bucket)
    print("Created:", bucket)

print("\nAll marine storage buckets created!")
