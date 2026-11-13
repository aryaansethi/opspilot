"""Chat LLM over an OpenAI-compatible API (Ollama locally, OpenAI optionally)."""

import json
import re
from typing import Any, Protocol

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    model: str

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]: ...


def parse_json_reply(content: str) -> dict[str, Any]:
    content = _THINK.sub("", content).strip()
    m = _FENCED_JSON.search(content)
    if m:
        content = m.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model reply contained no JSON object")
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"Model reply was not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise LLMError("Model reply JSON was not an object")
    return data


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.model = s.llm_model
        self._suffix = s.llm_prompt_suffix
        self._client = AsyncOpenAI(
            base_url=s.llm_base_url,
            api_key=s.llm_api_key.get_secret_value(),
            timeout=s.llm_timeout_seconds,
            max_retries=1,
        )

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]:
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user + self._suffix},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        )
        content = resp.choices[0].message.content or ""
        return parse_json_reply(content)


_llm: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = OpenAICompatibleLLM()
    return _llm


def set_llm(llm: LLMProvider | None) -> None:
    """Test hook."""
    global _llm
    _llm = llm
