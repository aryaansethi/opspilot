"""AWS client configuration: LocalStack gets dummy keys; real AWS uses the standard chain."""

from pathlib import Path

import pytest

from mcp_servers.aws_compat import aws_client


def _no_ambient_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


def test_localstack_endpoint_uses_dummy_keys_and_query_protocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_ambient_credentials(monkeypatch, tmp_path)
    c = aws_client("cloudwatch", endpoint_url="http://localhost:4566")
    assert c._request_signer._credentials.access_key == "test"
    assert c.meta.service_model.protocol == "query"


def test_real_aws_never_gets_dummy_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_ambient_credentials(monkeypatch, tmp_path)
    c = aws_client("logs", endpoint_url="")
    assert c.meta.endpoint_url.startswith("https://logs.")
    assert (
        c._request_signer._credentials is None
    )  # nothing configured -> boto3 finds nothing, no "test"


def test_real_aws_uses_profile_or_env_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_ambient_credentials(monkeypatch, tmp_path)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLEEXAMPLE00")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "example-secret")
    c = aws_client("logs", endpoint_url="")
    assert c._request_signer._credentials.access_key == "AKIAEXAMPLEEXAMPLE00"


def test_app_storage_client_follows_the_same_rule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core.config import get_settings
    from app.documents import storage

    _no_ambient_credentials(monkeypatch, tmp_path)
    monkeypatch.setattr(get_settings(), "aws_endpoint_url", None)
    storage._client.cache_clear()
    try:
        assert storage._client("s3")._request_signer._credentials is None
    finally:
        storage._client.cache_clear()


def test_named_profile_beats_dummy_env_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_ambient_credentials(monkeypatch, tmp_path)
    creds = tmp_path / "credentials"
    creds.write_text("[cw]\naws_access_key_id = AKIAPROFILEPROFILE00\naws_secret_access_key = s\n")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv(
        "AWS_ACCESS_KEY_ID", "test"
    )  # LocalStack dummy keys loaded from backend/.env
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    c = aws_client("logs", endpoint_url="", profile="cw")
    assert c._request_signer._credentials.access_key == "AKIAPROFILEPROFILE00"


@pytest.mark.parametrize(
    ("env", "expected_endpoint"),
    [
        ({}, "http://localhost:4566"),  # default: LocalStack
        ({"AWS_ENDPOINT_URL": "http://localstack:4566"}, "http://localstack:4566"),
        (
            {"AWS_ENDPOINT_URL": "http://localhost:4566", "CW_AWS_ENDPOINT_URL": ""},
            "https://logs.eu-west-1.amazonaws.com",
        ),
    ],
)
def test_cloudwatch_server_endpoint_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env: dict[str, str], expected_endpoint: str
) -> None:
    from mcp_servers.cloudwatch import server

    _no_ambient_credentials(monkeypatch, tmp_path)
    for var in ("AWS_ENDPOINT_URL", "CW_AWS_ENDPOINT_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CW_AWS_REGION", "eu-west-1")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    server._client.cache_clear()
    try:
        assert server._client("logs").meta.endpoint_url == expected_endpoint
    finally:
        server._client.cache_clear()


def test_environment_endpoint_cannot_override_an_explicit_real_aws_choice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_ambient_credentials(monkeypatch, tmp_path)
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    assert aws_client("logs", endpoint_url="", region="eu-west-1").meta.endpoint_url == (
        "https://logs.eu-west-1.amazonaws.com"
    )
