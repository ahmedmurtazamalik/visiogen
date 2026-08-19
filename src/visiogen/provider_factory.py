"""Explicit construction and model identity for extraction providers."""

from __future__ import annotations

from visiogen.config import Settings
from visiogen.providers.base import DiagramExtractor
from visiogen.providers.codex_cli import CodexCLIExtractor
from visiogen.providers.gemini import GeminiExtractor
from visiogen.providers.local_qwen import LocalQwenExtractor


def create_extractor(settings: Settings) -> DiagramExtractor:
    """Construct only the provider explicitly selected in runtime settings."""

    if settings.provider == "codex":
        return CodexCLIExtractor(settings)
    if settings.provider == "local":
        return LocalQwenExtractor(settings)
    return GeminiExtractor(settings)


def selected_model(settings: Settings) -> str:
    """Return the explicit model identity for evaluation evidence."""

    if settings.provider == "codex":
        return settings.codex_model
    if settings.provider == "local":
        return settings.local_model
    return settings.gemini_model
