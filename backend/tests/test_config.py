import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults_target_local_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.environment == "local"
    assert ":5433/" in s.database_url
    assert s.llm_base_url.startswith("http://localhost:11434")
    assert s.embedding_dim == 1024


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "llama3.1:8b")
    monkeypatch.setenv("RERANK_ENABLED", "true")
    s = Settings(_env_file=None)
    assert s.llm_model == "llama3.1:8b"
    assert s.rerank_enabled is True


def test_production_rejects_dev_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production", cookie_secure=True)


def test_production_requires_secure_cookie() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(_env_file=None, environment="production", jwt_secret="x" * 48, cookie_secure=False)


def test_empty_aws_endpoint_means_real_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")
    assert Settings(_env_file=None).aws_endpoint_url is None
