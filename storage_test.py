from pathlib import Path
import json
import boto3
from botocore.config import Config

base = Path(r"D:\SSTRIX_MARINE_PLATFORM")

with open(base / "config" / "s3.json", encoding="utf-8-sig") as f:
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

source = base / "upload-test.txt"
download = base / "download-test.txt"

source.write_text("SSTRIX Marine AI Platform - Storage Test Successful", encoding="utf-8")

s3.upload_file(str(source), "marine-raw", "system-tests/upload-test.txt")
print("UPLOAD SUCCESS")

s3.download_file("marine-raw", "system-tests/upload-test.txt", str(download))
print("DOWNLOAD SUCCESS")

print("Downloaded content:", download.read_text(encoding="utf-8"))
