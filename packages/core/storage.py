"""MinIO client wrapper"""
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from typing import Optional
import os


class MinIOClient:
    """MinIO/S3 client wrapper for artifact storage"""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        use_ssl: bool = False,
    ):
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.bucket = bucket or os.getenv("MINIO_BUCKET", "slidesherlock")
        self.use_ssl = use_ssl

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
            use_ssl=use_ssl,
            verify=False,
        )

        # Ensure bucket exists
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist"""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            # Bucket doesn't exist, create it
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError as e:
                print(f"Warning: Could not create bucket {self.bucket}: {e}")

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload data to MinIO"""
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
            return self.get_url(key)
        except ClientError as e:
            raise Exception(f"Failed to upload to MinIO: {e}")

    def get(self, key: str) -> bytes:
        """Download data from MinIO"""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            raise Exception(f"Failed to download from MinIO: {e}")

    def exists(self, key: str) -> bool:
        """Check if key exists in MinIO"""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def get_url(self, key: str) -> str:
        """Get URL for a key"""
        return f"{self.endpoint}/{self.bucket}/{key}"

    def delete(self, key: str) -> bool:
        """Delete a key from MinIO"""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
