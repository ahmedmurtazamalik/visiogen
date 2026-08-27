"""Provider protocol, model-call seam, and shared errors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from visiogen.models import DiagramGraph


class ProviderError(RuntimeError):
    """Raised when a model provider cannot return a usable response."""


class ProviderTimeoutError(ProviderError):
    """Transient provider timeout with safe attempt metadata for bounded retry."""

    def __init__(
        self,
        message: str,
        *,
        elapsed_ms: float,
        transport_prompt: str | None = None,
    ) -> None:
        self.elapsed_ms = elapsed_ms
        self.transport_prompt = transport_prompt
        super().__init__(message)


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
    transport_prompt: str | None = None


@runtime_checkable
class DiagramExtractor(Protocol):
    """Provider-neutral semantic extraction interface."""

    def extract(self, text: str) -> DiagramGraph: ...


class StructuredModelCall(Protocol):
    """Injected structured-model transport used by the shared workflow."""

    def __call__(self, system_prompt: str, user_prompt: str) -> ProviderResponse: ...


class ImageStructuredCall(Protocol):
    """Structured provider capability that accepts real image files."""

    def call_with_images(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Sequence[str | Path],
    ) -> ProviderResponse: ...
