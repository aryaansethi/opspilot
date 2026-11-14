"""S3 (LocalStack locally) and SQS helpers. boto3 is sync, so calls run in a thread."""

import asyncio
import json
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import get_settings


@lru_cache
def _client(service: str, endpoint_url: str | None = None) -> Any:
    s = get_settings()
    return boto3.client(
        service,  # type: ignore[call-overload]
        region_name=s.aws_region,
        endpoint_url=endpoint_url or s.aws_endpoint_url,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key.get_secret_value(),
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def s3() -> Any:
    return _client("s3")


def sqs() -> Any:
    return _client("sqs")


async def presign_put(key: str, content_type: str) -> str:
    s = get_settings()
    # Browsers upload directly to S3, so the signed URL must use an address they can reach
    # (in Docker the API talks to http://localstack:4566, the browser to http://localhost:4566).
    signer = _client("s3", s.s3_public_endpoint_url) if s.s3_public_endpoint_url else s3()
    return await asyncio.to_thread(
        signer.generate_presigned_url,
        "put_object",
        Params={"Bucket": s.s3_documents_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=s.presign_ttl_seconds,
    )


async def head_object(key: str) -> dict[str, Any] | None:
    s = get_settings()
    try:
        return await asyncio.to_thread(s3().head_object, Bucket=s.s3_documents_bucket, Key=key)  # type: ignore[no-any-return]
    except s3().exceptions.ClientError:
        return None


async def get_object_bytes(key: str, max_bytes: int) -> bytes:
    s = get_settings()
    obj = await asyncio.to_thread(s3().get_object, Bucket=s.s3_documents_bucket, Key=key)
    body = obj["Body"]
    data: bytes = await asyncio.to_thread(body.read, max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Object exceeds maximum upload size")
    return data


async def put_object_bytes(key: str, data: bytes, content_type: str) -> None:
    s = get_settings()
    await asyncio.to_thread(
        s3().put_object, Bucket=s.s3_documents_bucket, Key=key, Body=data, ContentType=content_type
    )


async def delete_object(key: str) -> None:
    s = get_settings()
    await asyncio.to_thread(s3().delete_object, Bucket=s.s3_documents_bucket, Key=key)


@lru_cache
def _queue_url(name: str) -> str:
    return str(sqs().get_queue_url(QueueName=name)["QueueUrl"])


async def enqueue(queue: str, message: dict[str, Any]) -> None:
    url = await asyncio.to_thread(_queue_url, queue)
    await asyncio.to_thread(sqs().send_message, QueueUrl=url, MessageBody=json.dumps(message))


async def receive(
    queue: str, wait_seconds: int = 10, max_messages: int = 5
) -> list[dict[str, Any]]:
    url = await asyncio.to_thread(_queue_url, queue)
    resp = await asyncio.to_thread(
        sqs().receive_message,
        QueueUrl=url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds,
    )
    return list(resp.get("Messages", []))


async def ack(queue: str, receipt_handle: str) -> None:
    url = await asyncio.to_thread(_queue_url, queue)
    await asyncio.to_thread(sqs().delete_message, QueueUrl=url, ReceiptHandle=receipt_handle)
