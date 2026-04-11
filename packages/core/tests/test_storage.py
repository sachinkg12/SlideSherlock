"""Unit tests for storage.py (MinIOClient)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

# boto3 and botocore may not be installed in CI; mock them at the module level
_mock_boto3 = MagicMock()
_mock_botocore = MagicMock()
_mock_botocore_client = MagicMock()
_mock_botocore_exceptions = MagicMock()

# ClientError needs to be a real exception class so pytest.raises works
class _FakeClientError(Exception):
    def __init__(self, error_response, operation_name):
        self.response = error_response
        super().__init__(str(error_response))

_mock_botocore_exceptions.ClientError = _FakeClientError

sys.modules.setdefault("boto3", _mock_boto3)
sys.modules.setdefault("botocore", _mock_botocore)
sys.modules.setdefault("botocore.client", _mock_botocore_client)
sys.modules.setdefault("botocore.exceptions", _mock_botocore_exceptions)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def _import_minio():
    """Import MinIOClient fresh with mocked boto3."""
    # Remove cached module so each test gets a fresh import with current mocks
    sys.modules.pop("storage", None)
    from storage import MinIOClient
    return MinIOClient


def _make_client(bucket="slidesherlock"):
    """Create a MinIOClient with a mocked boto3 s3 client."""
    MinIOClient = _import_minio()

    mock_s3 = MagicMock()
    _mock_boto3.client.return_value = mock_s3
    mock_s3.head_bucket.return_value = {}

    client = MinIOClient(
        endpoint="http://localhost:9000",
        access_key="admin",
        secret_key="password",
        bucket=bucket,
    )
    client.client = mock_s3
    return client, mock_s3


def test_minio_client_instantiates():
    """MinIOClient can be instantiated with mocked boto3."""
    MinIOClient = _import_minio()
    mock_s3 = MagicMock()
    _mock_boto3.client.return_value = mock_s3
    mock_s3.head_bucket.return_value = {}

    client = MinIOClient(
        endpoint="http://localhost:9000",
        access_key="key",
        secret_key="secret",
        bucket="test-bucket",
    )
    assert client.bucket == "test-bucket"
    assert client.endpoint == "http://localhost:9000"


def test_minio_client_creates_bucket_if_missing():
    """If head_bucket raises ClientError, create_bucket is called."""
    MinIOClient = _import_minio()
    mock_s3 = MagicMock()
    _mock_boto3.client.return_value = mock_s3

    mock_s3.head_bucket.side_effect = _FakeClientError({"Error": {"Code": "NoSuchBucket"}}, "head_bucket")
    mock_s3.create_bucket.return_value = {}

    client = MinIOClient(bucket="newbucket")
    mock_s3.create_bucket.assert_called_once_with(Bucket="newbucket")


def test_put_calls_put_object():
    """put() calls s3.put_object with correct args and returns URL."""
    client, mock_s3 = _make_client()
    mock_s3.put_object.return_value = {}

    url = client.put("some/key.json", b'{"a":1}', "application/json")

    mock_s3.put_object.assert_called_once_with(
        Bucket="slidesherlock",
        Key="some/key.json",
        Body=b'{"a":1}',
        ContentType="application/json",
    )
    assert "some/key.json" in url


def test_put_raises_on_s3_error():
    """put() raises Exception when put_object fails."""
    client, mock_s3 = _make_client()
    mock_s3.put_object.side_effect = _FakeClientError({"Error": {"Code": "AccessDenied"}}, "put_object")

    # The storage module catches botocore.exceptions.ClientError — we need to inject our fake
    # into the storage module's namespace
    sys.modules.pop("storage", None)
    import storage as storage_mod
    storage_mod.ClientError = _FakeClientError
    client.client = mock_s3

    with pytest.raises(Exception, match="Failed to upload to MinIO"):
        client.put("key", b"data")


def test_get_calls_get_object_and_returns_bytes():
    """get() calls s3.get_object and returns body bytes."""
    client, mock_s3 = _make_client()
    mock_body = MagicMock()
    mock_body.read.return_value = b"file contents"
    mock_s3.get_object.return_value = {"Body": mock_body}

    result = client.get("path/to/file.json")

    mock_s3.get_object.assert_called_once_with(Bucket="slidesherlock", Key="path/to/file.json")
    assert result == b"file contents"


def test_get_raises_on_s3_error():
    """get() raises Exception when object doesn't exist."""
    client, mock_s3 = _make_client()

    sys.modules.pop("storage", None)
    import storage as storage_mod
    storage_mod.ClientError = _FakeClientError
    client.client = mock_s3

    mock_s3.get_object.side_effect = _FakeClientError({"Error": {"Code": "NoSuchKey"}}, "get_object")

    with pytest.raises(Exception, match="Failed to download from MinIO"):
        client.get("missing/key")


def test_exists_returns_true_when_head_succeeds():
    """exists() returns True when head_object succeeds."""
    client, mock_s3 = _make_client()
    mock_s3.head_object.return_value = {}

    assert client.exists("some/key") is True


def test_exists_returns_false_on_error():
    """exists() returns False when head_object raises ClientError."""
    client, mock_s3 = _make_client()

    sys.modules.pop("storage", None)
    import storage as storage_mod
    storage_mod.ClientError = _FakeClientError
    client.client = mock_s3

    mock_s3.head_object.side_effect = _FakeClientError({"Error": {"Code": "404"}}, "head_object")

    assert client.exists("missing/key") is False


def test_delete_returns_true_on_success():
    """delete() calls delete_object and returns True."""
    client, mock_s3 = _make_client()
    mock_s3.delete_object.return_value = {}

    result = client.delete("path/to/file")

    mock_s3.delete_object.assert_called_once_with(Bucket="slidesherlock", Key="path/to/file")
    assert result is True


def test_delete_returns_false_on_error():
    """delete() returns False when delete_object raises ClientError."""
    client, mock_s3 = _make_client()

    sys.modules.pop("storage", None)
    import storage as storage_mod
    storage_mod.ClientError = _FakeClientError
    client.client = mock_s3

    mock_s3.delete_object.side_effect = _FakeClientError({"Error": {"Code": "Error"}}, "delete_object")

    result = client.delete("bad/key")
    assert result is False


def test_get_url_format():
    """get_url() returns expected URL string."""
    client, _ = _make_client()
    url = client.get_url("jobs/123/render/deck.pdf")
    assert url == "http://localhost:9000/slidesherlock/jobs/123/render/deck.pdf"


def test_uses_env_vars_as_defaults(monkeypatch):
    """MinIOClient reads endpoint, keys, and bucket from environment."""
    monkeypatch.setenv("MINIO_ENDPOINT", "http://envhost:9001")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "envkey")
    monkeypatch.setenv("MINIO_SECRET_KEY", "envsecret")
    monkeypatch.setenv("MINIO_BUCKET", "envbucket")

    MinIOClient = _import_minio()
    mock_s3 = MagicMock()
    _mock_boto3.client.return_value = mock_s3
    mock_s3.head_bucket.return_value = {}

    client = MinIOClient()

    assert client.endpoint == "http://envhost:9001"
    assert client.access_key == "envkey"
    assert client.bucket == "envbucket"
