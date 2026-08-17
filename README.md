# Visiogen

Visiogen converts supported text descriptions into structured, editable Microsoft Visio diagrams.

The baseline targets flowcharts, system block diagrams, and abstract patent-oriented component schematics. Development is currently in the foundation phase.

## Development

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run pytest -q
uv run visiogen --help
```

The renderer will use a known-good Visio template. Real `.vsdx` compatibility and connector glue must be accepted in Microsoft Visio on Windows before renderer development proceeds.
