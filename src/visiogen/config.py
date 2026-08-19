"""Explicit runtime configuration with no import-time environment reads."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Literal, Mapping, cast

ProviderName = Literal["local", "gemini"]


class ConfigError(ValueError):
    """Raised when selected-provider configuration is invalid."""


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError("VISIOGEN_DEBUG must be a boolean")


def _parse_timeout(value: str) -> float:
    try:
        return float(value)
    except ValueError as error:
        raise ConfigError("VISIOGEN_TIMEOUT_SECONDS must be numeric") from error


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings constructible directly or explicitly from the environment."""

    provider: ProviderName
    local_base_url: str = "http://127.0.0.1:8080/v1"
    local_model: str = "qwen3.5-9b"
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str | None = None
    timeout_seconds: float = 60.0
    debug: bool = False

    def __post_init__(self) -> None:
        if self.provider not in {"local", "gemini"}:
            raise ConfigError(f"Unsupported provider '{self.provider}'")
        if self.timeout_seconds <= 0:
            raise ConfigError("Timeout must be positive")
        if self.provider == "local" and not self.local_base_url.strip():
            raise ConfigError("Local base URL is required for provider 'local'")
        if self.provider == "local" and not self.local_model.strip():
            raise ConfigError("Local model is required for provider 'local'")
        if self.provider == "gemini" and not self.gemini_model.strip():
            raise ConfigError("Gemini model is required for provider 'gemini'")
        if self.provider == "gemini" and not self.gemini_api_key:
            raise ConfigError("Gemini API key is required for provider 'gemini'")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read VISIOGEN_ settings only when explicitly requested."""

        values = os.environ if environ is None else environ
        provider = values.get("VISIOGEN_PROVIDER")
        if provider is None:
            raise ConfigError("VISIOGEN_PROVIDER is required")
        return cls(
            provider=cast(ProviderName, provider),
            local_base_url=values.get(
                "VISIOGEN_LOCAL_BASE_URL", "http://127.0.0.1:8080/v1"
            ).rstrip("/"),
            local_model=values.get("VISIOGEN_LOCAL_MODEL", "qwen3.5-9b"),
            gemini_model=values.get("VISIOGEN_GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_api_key=values.get("VISIOGEN_GEMINI_API_KEY"),
            timeout_seconds=_parse_timeout(
                values.get("VISIOGEN_TIMEOUT_SECONDS", "60")
            ),
            debug=_parse_bool(values.get("VISIOGEN_DEBUG", "false")),
        )
