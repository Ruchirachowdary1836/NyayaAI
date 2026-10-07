from __future__ import annotations

import json

import httpx

from backend.app.services.generation.prompts import SYSTEM_PROMPT


class OllamaGenerator:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b-instruct",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def generate(self, prompt: str, seed: int = 42) -> str:
        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "seed": seed},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Local model service is unavailable: {error}") from error
        result = response.json().get("response")
        if not isinstance(result, str) or not result.strip():
            raise RuntimeError("Local model service returned an empty answer")
        return result.strip()

    async def stream(self, prompt: str, seed: int = 42):
        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": 0, "seed": seed},
        }
        try:
            async with (
                httpx.AsyncClient(timeout=None) as client,
                client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response,
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
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError(f"Local model stream failed: {error}") from error


class OpenAICompatibleGenerator:
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
            raise RuntimeError(
                "AI answer generation is not configured. Set GENERATOR_API_KEY in the API service."
            )
        return {"Authorization": f"Bearer {self.api_key}"}

    async def generate(self, prompt: str, seed: int = 42) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "seed": seed,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Configured AI provider request failed: {error}") from error
        choices = response.json().get("choices")
        content = (
            choices[0].get("message", {}).get("content")
            if isinstance(choices, list) and choices
            else None
        )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Configured AI provider returned an empty answer")
        return content.strip()

    async def stream(self, prompt: str, seed: int = 42):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "seed": seed,
            "stream": True,
        }
        try:
            async with (
                httpx.AsyncClient(timeout=None) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError as error:
                        raise RuntimeError(
                            "Configured AI provider sent malformed stream data"
                        ) from error
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    token = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(token, str) and token:
                        yield token
        except httpx.HTTPError as error:
            raise RuntimeError(f"Configured AI provider stream failed: {error}") from error


def build_generator(
    provider: str,
    api_key: str,
    api_base_url: str,
    ollama_base_url: str,
    model: str,
) -> OllamaGenerator | OpenAICompatibleGenerator:
    if provider == "openai":
        return OpenAICompatibleGenerator(api_key, model, api_base_url)
    if provider == "ollama":
        return OllamaGenerator(ollama_base_url, model)
    raise ValueError(f"Unsupported generation provider {provider!r}; choose openai or ollama")
