"""Groq provider.

Groq exposes an OpenAI-compatible surface, so this speaks plain HTTP rather
than pulling in an SDK whose version drift would be a maintenance liability.

The API key lives only here, server-side. It is never sent to the browser.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx

from app.ai.providers.base import AIProvider, ProviderError, ProviderResponse, ToolCall
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.model = model or settings.groq_model
        self.base_url = (base_url or settings.groq_base_url).rstrip("/")
        self.timeout = settings.ai_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        temperature: float,
        max_tokens: int,
        json_schema: dict[str, Any] | None,
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema.get("name", "response"),
                    "schema": json_schema["schema"],
                    "strict": True,
                },
            }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1600,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        if not self.configured:
            raise ProviderError("No Groq API key configured")

        payload = self._payload(
            messages, model, temperature, max_tokens, json_schema, tools
        )
        started = time.monotonic()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("Groq timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach Groq: {exc}", retryable=True) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        self._raise_for_status(response)

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError("Groq returned a non-JSON response") from exc

        choices = body.get("choices") or []
        if not choices:
            raise ProviderError("Groq returned no choices")

        message = choices[0].get("message") or {}
        usage = body.get("usage") or {}

        return ProviderResponse(
            content=message.get("content") or "",
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            model=body.get("model", payload["model"]),
            finish_reason=choices[0].get("finish_reason", "stop"),
        )

    def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1600,
    ) -> Iterator[str]:
        if not self.configured:
            raise ProviderError("No Groq API key configured")

        payload = self._payload(messages, model, temperature, max_tokens, None, None)
        payload["stream"] = True

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        response.read()
                        self._raise_for_status(response)
                    for line in response.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content")
                        if delta:
                            yield delta
        except httpx.TimeoutException as exc:
            raise ProviderError("Groq timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach Groq: {exc}", retryable=True) from exc

    def list_models(self) -> list[str]:
        if not self.configured:
            return []
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.base_url}/models", headers=self._headers())
            response.raise_for_status()
            return sorted(
                item["id"] for item in response.json().get("data", []) if item.get("id")
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.info("could not list Groq models", error=str(exc))
            return []

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        detail = ""
        try:
            detail = (response.json().get("error") or {}).get("message", "")
        except ValueError:
            detail = response.text[:200]

        if response.status_code == 401:
            raise ProviderError("Groq rejected the API key")
        if response.status_code == 404:
            # Almost always a decommissioned or misspelled model id.
            raise ProviderError(
                f"Groq does not recognise that model: {detail or 'not found'}. "
                "Check GROQ_MODEL against the current catalog."
            )
        if response.status_code == 429:
            raise ProviderError("Groq rate limit reached", retryable=True)
        if response.status_code >= 500:
            raise ProviderError(f"Groq is unavailable ({response.status_code})", retryable=True)
        raise ProviderError(detail or f"Groq error {response.status_code}")


def _parse_tool_calls(raw: list[dict[str, Any]] | None) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in raw or []:
        function = item.get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        calls.append(
            ToolCall(
                id=item.get("id", ""),
                name=function.get("name", ""),
                arguments=arguments or {},
            )
        )
    return calls
