from visiogen.config import Settings
from visiogen.provider_factory import create_extractor, selected_model
from visiogen.providers.codex_cli import CodexCLIExtractor
from visiogen.providers.gemini import GeminiExtractor
from visiogen.providers.local_qwen import LocalQwenExtractor


def test_factory_builds_explicit_codex_provider_and_model_identity() -> None:
    settings = Settings(provider="codex", codex_model="gpt-5.6-sol-test")

    extractor = create_extractor(settings)

    assert isinstance(extractor, CodexCLIExtractor)
    assert selected_model(settings) == "gpt-5.6-sol-test"


def test_factory_retains_explicit_optional_providers() -> None:
    local = Settings(provider="local", local_model="qwen-test")
    gemini = Settings(
        provider="gemini",
        gemini_model="gemini-test",
        gemini_api_key="test-key",
    )

    assert isinstance(create_extractor(local), LocalQwenExtractor)
    assert selected_model(local) == "qwen-test"
    assert isinstance(create_extractor(gemini), GeminiExtractor)
    assert selected_model(gemini) == "gemini-test"
