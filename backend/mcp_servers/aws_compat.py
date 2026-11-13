"""boto3 client factory with a LocalStack compatibility shim.

Recent botocore talks to CloudWatch with the smithy-rpc-v2-cbor protocol, which
LocalStack's free edition does not understand. Real AWS still accepts the older
`query` protocol, so when an endpoint override is set (LocalStack) we pin
CloudWatch to `query`. Against real AWS (no endpoint override) nothing changes.
"""

import os
from typing import Any

import boto3
import botocore.session

_QUERY_ONLY = {"cloudwatch"}


def aws_client(service: str, *, endpoint_url: str | None = None, region: str | None = None) -> Any:
    endpoint = endpoint_url if endpoint_url is not None else os.environ.get("AWS_ENDPOINT_URL")
    core = botocore.session.get_session()
    if endpoint and service in _QUERY_ONLY:
        model = core.get_component("data_loader").load_service_model(service, "service-2")
        model["metadata"]["protocols"] = ["query"]
        model["metadata"]["protocol"] = "query"
    return boto3.Session(botocore_session=core).client(
        service,  # type: ignore[call-overload]
        region_name=region or os.environ.get("AWS_REGION", "us-east-1"),
        endpoint_url=endpoint or None,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )
