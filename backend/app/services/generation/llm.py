from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from backend.app.services.generation.prompts import SYSTEM_PROMPT


class GenerationError(RuntimeError):
    """A provider failure with an HTTP status suitable for API responses.

    Messages never include credentials or raw provider payloads.
    """

    def __init__(self, message: str, status_code: int = 503, kind: str = "unavailable") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


class Generator(Protocol):
    provider: str
    model: str

    @property
    def configured(self) -> bool: ...

    async def generate(self, prompt: str, seed: int = 42) -> str: ...

    def stream(self, prompt: str, seed: int = 42) -> AsyncIterator[str]: ...


def _classify(error: Exception, provider_label: str) -> GenerationError:
    if isinstance(error, GenerationError):
        return error
    if isinstance(error, httpx.TimeoutException):
        return GenerationError(f"{provider_label} timed out. Try again shortly.", 504, "timeout")
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {401, 403}:
            return GenerationError(
                f"{provider_label} rejected the configured credentials. "
                "Check GENERATOR_API_KEY in the API service.",
                503,
                "auth",
            )
        if status == 404:
            return GenerationError(
                f"{provider_label} does not recognise the configured model. "
                "Check GENERATOR_MODEL.",
                503,
                "model",
            )
        if status == 429:
            return GenerationError(
                f"{provider_label} rate limit or quota exceeded. Try again later.",
                503,
                "rate_limit",
            )
        return GenerationError(
            f"{provider_label} returned an error (HTTP {status}).", 502, "provider_error"
        )
    if isinstance(error, httpx.HTTPError):
        return GenerationError(f"{provider_label} is unreachable.", 503, "unreachable")
    if isinstance(error, ValueError | KeyError | TypeError):
        return GenerationError(f"{provider_label} returned a malformed response.", 502, "malformed")
    return GenerationError(f"{provider_label} request failed.", 502, "provider_error")


class OllamaGenerator:
    provider = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b-instruct",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.timeout, connect=10.0)

    def _payload(self, prompt: str, seed: int, stream: bool) -> dict[str, object]:
        return {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": stream,
            "options": {"temperature": 0, "seed": seed},
        }

    async def generate(self, prompt: str, seed: int = 42) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate", json=self._payload(prompt, seed, False)
                )
                response.raise_for_status()
                result = response.json().get("response")
        except Exception as error:
            raise _classify(error, "The local Ollama model service") from error
        if not isinstance(result, str) or not result.strip():
            raise GenerationError(
                "The local Ollama model service returned an empty answer.", 502, "empty"
            )
        return result.strip()

    async def stream(self, prompt: str, seed: int = 42) -> AsyncIterator[str]:
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout()) as client,
                client.stream(
                    "POST", f"{self.base_url}/api/generate", json=self._payload(prompt, seed, True)
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    payload_item = json.loads(line)
                    token = payload_item.get("response")
                    if isinstance(token, str) and token:
                        yield token
                    if payload_item.get("done"):
                        break
        except Exception as error:
            raise _classify(error, "The local Ollama model service") from error


class OpenAICompatibleGenerator:
    provider = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise GenerationError(
                "AI answer generation is not configured. Set GENERATOR_API_KEY in the API service.",
                503,
                "not_configured",
            )
        return {"Authorization": f"Bearer {self.api_key}"}

    def _payload(self, prompt: str, seed: int, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "seed": seed,
        }
        if stream:
            payload["stream"] = True
        return payload

    async def generate(self, prompt: str, seed: int = 42) -> str:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=self._payload(prompt, seed, False),
                    headers=headers,
                )
                response.raise_for_status()
                choices = response.json().get("choices")
        except Exception as error:
            raise _classify(error, "The configured AI provider") from error
        content = (
            choices[0].get("message", {}).get("content")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )
        if not isinstance(content, str) or not content.strip():
            raise GenerationError(
                "The configured AI provider returned an empty answer.", 502, "empty"
            )
        return content.strip()

    async def stream(self, prompt: str, seed: int = 42) -> AsyncIterator[str]:
        headers = self._headers()
        try:
            async with (
                httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=self._payload(prompt, seed, True),
                    headers=headers,
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    token = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(token, str) and token:
                        yield token
        except Exception as error:
            raise _classify(error, "The configured AI provider") from error


def build_generator(
    provider: str,
    api_key: str,
    api_base_url: str,
    ollama_base_url: str,
    model: str,
    timeout: float = 120.0,
) -> OllamaGenerator | OpenAICompatibleGenerator:
    if provider == "openai":
        return OpenAICompatibleGenerator(api_key, model, api_base_url, timeout=timeout)
    if provider == "ollama":
        return OllamaGenerator(ollama_base_url, model, timeout=timeout)
    raise ValueError(f"Unsupported generation provider {provider!r}; choose openai or ollama")
