"""AI provider abstraction.

The rest of the application talks to `AIProvider`, never to a vendor SDK, so
swapping or adding a provider is a new subclass rather than a refactor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    finish_reason: str = "stop"

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class ProviderError(Exception):
    """The provider failed. Callers must degrade, never propagate a 500."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class AIProvider(ABC):
    name = "base"

    @property
    @abstractmethod
    def configured(self) -> bool:
        """False when no API key is present — AI features then hide cleanly."""

    @abstractmethod
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
        """One completion round trip."""

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1600,
    ):
        """Yield content chunks as they arrive."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """Live model catalog, so the UI never offers a decommissioned model."""
