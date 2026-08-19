"""Provider protocol, model-call seam, and shared errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from visiogen.models import DiagramGraph


class ProviderError(RuntimeError):
    """Raised when a model provider cannot return a usable response."""


class ExtractionValidationError(ValueError):
    """Raised when provider output remains invalid after schema repair."""


class NoDiagramContentError(ExtractionValidationError):
    """Raised when input or provider output contains no diagram semantics."""


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Provider text plus safe transport metadata."""

    content: str
    request_id: str | None = None
    elapsed_ms: float | None = None


@runtime_checkable
class DiagramExtractor(Protocol):
    """Provider-neutral semantic extraction interface."""

    def extract(self, text: str) -> DiagramGraph: ...


class StructuredModelCall(Protocol):
    """Injected structured-model transport used by the shared workflow."""

    def __call__(self, system_prompt: str, user_prompt: str) -> ProviderResponse: ...
