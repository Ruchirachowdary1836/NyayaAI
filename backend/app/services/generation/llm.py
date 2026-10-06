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
