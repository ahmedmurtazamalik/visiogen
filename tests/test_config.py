import pytest

from visiogen.config import ConfigError, Settings


def test_settings_accepts_explicit_local_configuration() -> None:
    settings = Settings(
        provider="local",
        local_base_url="http://127.0.0.1:8080/v1",
        local_model="qwen-test",
        timeout_seconds=45.0,
        debug=False,
    )

    assert settings.provider == "local"
    assert settings.local_model == "qwen-test"
    assert settings.gemini_api_key is None


def test_from_env_parses_only_required_local_configuration() -> None:
    settings = Settings.from_env(
        {
            "VISIOGEN_PROVIDER": "local",
            "VISIOGEN_LOCAL_BASE_URL": "http://localhost:9000/v1/",
            "VISIOGEN_LOCAL_MODEL": "qwen-local",
            "VISIOGEN_TIMEOUT_SECONDS": "30",
            "VISIOGEN_DEBUG": "true",
        }
    )

    assert settings.local_base_url == "http://localhost:9000/v1"
    assert settings.local_model == "qwen-local"
    assert settings.timeout_seconds == 30.0
    assert settings.debug is True


def test_gemini_requires_only_its_selected_credentials() -> None:
    with pytest.raises(ConfigError, match="Gemini API key is required"):
        Settings(provider="gemini")
    with pytest.raises(ConfigError, match="Gemini model is required"):
        Settings(provider="gemini", gemini_model="", gemini_api_key="test-key")

    settings = Settings(
        provider="gemini",
        gemini_model="gemini-test",
        gemini_api_key="test-key",
    )

    assert settings.gemini_model == "gemini-test"
    assert settings.gemini_api_key == "test-key"


def test_settings_rejects_unknown_provider() -> None:
    with pytest.raises(ConfigError, match="Unsupported provider 'other'"):
        Settings(provider="other")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"local_base_url": ""}, "Local base URL is required"),
        ({"local_model": ""}, "Local model is required"),
        ({"timeout_seconds": 0}, "Timeout must be positive"),
    ],
)
def test_settings_rejects_invalid_selected_local_values(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {"provider": "local", **overrides}
    with pytest.raises(ConfigError, match=message):
        Settings(**values)  # type: ignore[arg-type]


def test_from_env_rejects_invalid_debug_policy() -> None:
    with pytest.raises(ConfigError, match="VISIOGEN_DEBUG must be a boolean"):
        Settings.from_env(
            {
                "VISIOGEN_PROVIDER": "local",
                "VISIOGEN_DEBUG": "sometimes",
            }
        )
