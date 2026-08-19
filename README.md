# Visiogen

Visiogen converts supported text descriptions into structured, editable Microsoft Visio diagrams.

The baseline targets flowcharts, system block diagrams, and abstract patent-oriented component schematics. The canonical graph contract, deterministic semantic-to-template mapping, Windows-accepted Visio palette, provider-neutral extraction with preferred Codex CLI plus optional Qwen and Gemini adapters, and deterministic Graphviz/fallback layout strategies are implemented.

## Development

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Graphviz `dot` for the primary layout strategy and full acceptance suite. The deterministic fallback layout does not require Graphviz. Preferred live extraction also requires the Codex CLI authenticated locally with an eligible ChatGPT/Codex account.

```bash
uv sync --extra dev
uv run pytest -q
uv run visiogen --help
```

## Extraction providers

Provider selection is always explicit. Codex is preferred for the current trusted local-user application:

```bash
VISIOGEN_PROVIDER=codex \
VISIOGEN_CODEX_MODEL=gpt-5.6-sol \
VISIOGEN_TIMEOUT_SECONDS=120 \
uv run python scripts/evaluate_providers.py --provider codex
```

The Codex adapter runs each request in an ephemeral temporary directory with a read-only sandbox and schema-constrained output. It uses the local Codex login rather than a Visiogen API key. It is not intended to expose one user's personal subscription as a public multi-user backend.

Local Qwen and Gemini remain available only through explicit `local` or `gemini` selection; neither is a silent fallback for Codex.

The known-good Visio template and its connector, callout, container, and save/reopen behavior have passed Microsoft Visio acceptance. See [`docs/M4_EXTRACTION.md`](docs/M4_EXTRACTION.md) for provider contracts, real-provider evidence, and the accepted provider decision. See [`docs/M5_LAYOUT.md`](docs/M5_LAYOUT.md) for deterministic geometry architecture and acceptance evidence.
