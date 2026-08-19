# M4 Acceptance — Fixture Corpus and Provider-Neutral Extraction

**Status:** PASS  
**Platform:** Ubuntu, Python 3.11  
**Authoritative contract:** `visiogen.models.DiagramGraph`

## Scope completed

- Ten reviewed text fixtures under `tests/fixtures/text/`.
- Nine reviewed expected canonical graphs under `tests/fixtures/graphs/expected/`.
- One explicit ambiguous-input baseline: `NoDiagramContentError`; Visiogen does not manufacture a node when no diagram is present.
- Provider-neutral extraction protocol, shared geometry-free prompt, canonical validation, deterministic normalization, and exactly one schema-repair attempt.
- Explicit `VISIOGEN_` configuration with selected-provider-only credential requirements and no import-time environment reads.
- OpenAI-compatible local Qwen adapter with deterministic JSON-only requests.
- Gemini adapter using `google-genai` structured JSON output with `ExtractedDiagramGraph` as the response schema.
- Typed transport, malformed-envelope, schema-validation, and no-diagram failures.
- Request IDs and elapsed time are retained in safe metadata; prompts and API keys are excluded.

## Reviewed acceptance corpus

Flow-oriented cases:

1. `linear_flow`
2. `login_decision`
3. `method_loop`
4. `isolated_process`
5. `ambiguous_no_diagram` — expected typed error

System/component cases:

1. `basic_system`
2. `bidirectional_architecture`
3. `nested_subsystem`
4. `eco_headphone`
5. `patent_schematic`

The mocked provider contract runs every case through both adapters: 20 adapter/case combinations. Successful outputs validate as the same canonical `DiagramGraph`, contain no geometry, and match the reviewed semantic graph. The ambiguous case produces the same typed no-diagram outcome from both adapters.

## Offline acceptance evidence

```text
96 tests passed
96% total coverage
20/20 provider-contract combinations passed
100% coverage: extractor.py
100% coverage: providers/base.py
100% coverage: providers/gemini.py
97% coverage: providers/local_qwen.py
```

Normal automated tests use injected fake transports and require neither a running local model nor a Gemini API key.

## Optional live evaluation

Live evaluation is opt-in and never replaces reviewed expectations. Actual model outputs and a semantic mismatch report are written beneath an artifact-only directory:

```bash
# Local OpenAI-compatible Qwen server
VISIOGEN_LOCAL_BASE_URL=http://127.0.0.1:8080/v1 \
VISIOGEN_LOCAL_MODEL=qwen3.5-9b \
uv run python scripts/evaluate_providers.py --provider local

# Gemini
VISIOGEN_GEMINI_API_KEY='<key>' \
VISIOGEN_GEMINI_MODEL=gemini-2.5-flash \
uv run python scripts/evaluate_providers.py --provider gemini
```

Default outputs:

```text
artifacts/provider-evaluation/<provider>/*.actual.json
artifacts/provider-evaluation/<provider>/semantic-mismatch-report.json
```

The evaluator rejects output paths inside `tests/fixtures/graphs/expected/`, so a live run cannot overwrite reviewed expected graphs.

## Dependency-ordered commits

```text
581b3f2 Add reviewed extraction fixtures
5dd5507 Add provider-neutral extraction workflow
a035f95 Add explicit provider configuration
71bab06 Add local Qwen extraction provider
eb7a946 Add Gemini extraction provider
```

M4 may feed M7 pipeline/CLI integration. Deterministic layout remains independently owned by M5; neither provider emits coordinates or visual placement.
