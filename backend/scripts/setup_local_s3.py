import os
import time
import json

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError


def env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None else value


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_s3_client():
    endpoint = env("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    region = env("S3_REGION", "us-east-1")
    access_key = env("S3_ACCESS_KEY", "minioadmin")
    secret_key = env("S3_SECRET_KEY", "minioadmin")
    force_path_style = env_bool("S3_FORCE_PATH_STYLE", True)

    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if force_path_style else "auto"},
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=config,
    )


def wait_for_s3(client, timeout_seconds: int = 60):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            client.list_buckets()
            return
        except (EndpointConnectionError, ClientError):
            time.sleep(1)
    raise RuntimeError("S3 endpoint is not reachable")


def ensure_bucket(client, bucket_name: str):
    buckets = client.list_buckets().get("Buckets", [])
    names = {bucket["Name"] for bucket in buckets}
    if bucket_name in names:
        print(f"Bucket already exists: {bucket_name}")
        return

    client.create_bucket(Bucket=bucket_name)
    print(f"Bucket created: {bucket_name}")


def configure_cors(client, bucket_name: str):
    cors = {
        "CORSRules": [
            {
                "AllowedHeaders": ["*"],
                "AllowedMethods": ["GET", "POST", "PUT", "HEAD"],
                "AllowedOrigins": [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3000,
            }
        ]
    }
    client.put_bucket_cors(Bucket=bucket_name, CORSConfiguration=cors)
    print(f"CORS configured for bucket: {bucket_name}")


def configure_public_read(client, bucket_name: str):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
            }
        ],
    }
    client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
    print(f"Public read policy configured for bucket: {bucket_name}")


def main():
    bucket = env("S3_BUCKET", "jewelry-media")
    client = build_s3_client()
    wait_for_s3(client)
    ensure_bucket(client, bucket)
    configure_cors(client, bucket)
    configure_public_read(client, bucket)
    print("Local S3 setup complete")


if __name__ == "__main__":
    main()
