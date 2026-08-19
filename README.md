# Visiogen

Visiogen converts supported text descriptions into structured, editable Microsoft Visio diagrams.

The baseline targets flowcharts, system block diagrams, and abstract patent-oriented component schematics. The canonical graph contract, deterministic semantic-to-template mapping, Windows-accepted Visio palette, reviewed extraction fixtures, and local Qwen/Gemini extraction adapters are implemented.

## Development

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run pytest -q
uv run visiogen --help
```

The known-good Visio template and its connector, callout, container, save/reopen behavior have passed Microsoft Visio acceptance. See [`docs/M4_EXTRACTION.md`](docs/M4_EXTRACTION.md) for provider-contract evidence and the optional live-model evaluation workflow.
