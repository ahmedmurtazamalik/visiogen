# M4 Acceptance — Fixture Corpus and Provider-Neutral Extraction

**Status:** LIVE GATE OPEN — NOT YET ACCEPTED
**Platform:** Ubuntu, Python 3.11
**Authoritative contract:** `visiogen.models.DiagramGraph`
**Live evaluation date:** 2026-08-19

## Scope implemented

- Ten reviewed text fixtures under `tests/fixtures/text/`.
- Nine immutable reviewed canonical graphs under `tests/fixtures/graphs/expected/`.
- One explicit ambiguous-input baseline: `NoDiagramContentError`; Visiogen does not manufacture a node when no diagram is present.
- Provider-neutral extraction, a shared geometry-free prompt, canonical validation, deterministic normalization, and exactly one schema-repair attempt.
- Explicit `VISIOGEN_` configuration with selected-provider-only credential requirements and no import-time environment reads.
- An OpenAI-compatible local Qwen adapter and a Google Gemini adapter using the same extraction workflow, DTO schema, normalization, and errors.
- Typed transport, malformed-envelope, schema-validation, and no-diagram failures.
- Artifact containment checks that prohibit evaluation output from entering the immutable expected-fixture directory.

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

## Offline contract evidence

The controlled provider contract remains deterministic unit evidence, not live-provider evidence. It uses injected transports to prove request construction, parsing, shared canonical validation, exactly one repair attempt, and typed failures.

Historical M4 evidence before layout work:

```text
96 tests passed
96% total coverage
20/20 controlled provider/fixture combinations passed
```

Current complete-suite evidence after the live interoperability fixes and M5 implementation:

```text
156 tests passed
```

## Mandatory live-evaluation method

Qwen and Gemini are run separately; there is no fallback or provider substitution:

```bash
set -a
source .env.live
set +a

uv run python scripts/evaluate_providers.py --provider local
uv run python scripts/evaluate_providers.py --provider gemini
```

Actual canonical graphs and field-level strict mismatch reports are written beneath an artifact-only directory:

```text
artifacts/provider-evaluation/<run>/<provider>/*.actual.json
artifacts/provider-evaluation/<run>/<provider>/semantic-mismatch-report.json
```

Generated edge IDs are excluded from strict semantic comparison. Other field differences are recorded with their expected and actual JSON paths. A strict mismatch is evidence of drift from a reviewed graph; it is not automatically a transport or schema interoperability failure.

## Live interoperability failures found and corrected

Real inference exposed defects that controlled transports did not:

1. Gemini rejected the Pydantic class passed through `response_schema` because its generated schema contained unsupported fields. The adapter now passes `ExtractedDiagramGraph.model_json_schema()` through `response_json_schema`.
2. The previously configured Gemini model was unavailable to the account. Configuration now selects an explicitly available model rather than silently falling back.
3. The local Qwen request allowed unbounded output and thinking-mode behavior, causing corpus evaluation to stall. The adapter now disables thinking explicitly, uses llama.cpp JSON Schema constrained output, and caps completion output.
4. Local Qwen expressed a bidirectional relation as two reciprocal forward edges. Extraction normalization now deterministically collapses equivalent reciprocal edges into one bidirectional canonical edge without mutating the provider graph.
5. The live evaluator previously reported only a binary mismatch. Reports now include model identity, UTC evaluation time, and field-level differences while ignoring generated edge IDs.
6. The shared prompt now requires minimal source-faithful graphs, deterministic label/ID conventions, explicit flow handling, and concrete node-taxonomy guidance discovered from real provider output.

Every source correction above was introduced with a failing regression test before implementation.

## Real Gemini evidence

### `gemini-3.6-flash`

A complete ten-case authenticated run produced valid canonical output for all nine diagram-bearing prompts and the expected no-diagram outcome for the ambiguous prompt. The run completed through the real `google-genai` SDK and saved all nine actual graphs.

```text
cases: 10
strict matches: 1
strict mismatches: 9
transport/schema failures: 0
```

The sole strict match was `ambiguous_no_diagram`. Most graph-bearing differences were generated titles, internal node IDs, wording/case, or edge annotations; substantive taxonomy/topology drift remained in several cases. Therefore this run proves real SDK/schema/canonical-pipeline interoperability, but it does not satisfy a zero-drift semantic acceptance gate.

Evidence:

```text
artifacts/provider-evaluation/gemini/*.actual.json
artifacts/provider-evaluation/gemini/semantic-mismatch-report.json
```

### Prompt-correction verification and quota blocker

Targeted authenticated calls using `gemini-3.7-flash` and the corrected prompt returned valid canonical graphs for the four previously difficult cases (`eco_headphone`, `login_decision`, `method_loop`, and `nested_subsystem`) and corrected the observed taxonomy/topology failures. A subsequent full-corpus attempt reached the account's request-per-day quota, so it could not provide a complete current-prompt acceptance run.

The incomplete full-run report is retained rather than relabeled as success:

```text
artifacts/provider-evaluation/live-acceptance/gemini/semantic-mismatch-report.json
```

No automatic model fallback was used. The final Gemini zero-drift/current-prompt gate remains blocked until quota resets or billing provides sufficient quota for one complete run.

## Real local Qwen evidence

Provider endpoint and served model:

```text
OpenAI-compatible llama.cpp: http://127.0.0.1:8080/v1
served model ID: qwen3.5-9b
model artifact: unsloth/Qwen3.5-9B-GGUF:Q5_K_M
```

A complete ten-case run executed through the real llama.cpp server. Eight diagram-bearing prompts completed within the configured 300-second request timeout. `eco_headphone` exceeded that limit, then succeeded on an explicit 600-second retry in 424.74 seconds. The preserved corpus therefore contains nine actual canonical graphs plus the expected no-diagram outcome.

```text
cases: 10
saved canonical graphs: 9
strict matches: 1
strict mismatches: 9
remaining transport/schema failures after retry: 0
```

The strict match was `ambiguous_no_diagram`. Manual semantic review classified `basic_system`, `isolated_process`, and `linear_flow` as source-faithful apart from generated presentation/identity fields. Substantive drift remained in six diagram cases:

- `bidirectional_architecture`: incorrect node taxonomy for the communication gateway and external analytics service.
- `eco_headphone`: represented housing containment as association edges instead of canonical `parent_id` values.
- `login_decision`: invented a `Return to entry` process node.
- `method_loop`: omitted the normal post-processing continuation edge.
- `nested_subsystem`: omitted the control-subsystem container and child containment.
- `patent_schematic`: embedded reference numerals in labels/IDs instead of populating canonical `reference_number` fields.

The reciprocal processor/memory edges in `basic_system` were normalized into one canonical bidirectional edge by the regression-tested interoperability correction.

Evidence:

```text
artifacts/provider-evaluation/prompt-v2/local/*.actual.json
artifacts/provider-evaluation/prompt-v2/local/semantic-mismatch-report.json
```

## Current gate decision

M4 implementation and offline contracts are complete. Real provider interoperability has been demonstrated, and real failures have produced regression-tested corrections. **M4 live semantic acceptance remains open** because:

- the final current-prompt Gemini corpus rerun is blocked by the daily request quota; and
- the current CPU-served Qwen3.5-9B model still has substantive canonical semantic drift in six diagram cases despite successful schema/pipeline interoperability.

M5 closure and push remain paused until this section is replaced by complete evidence or the residual model-quality mismatches are explicitly accepted as the baseline.

## Dependency-ordered commits

```text
581b3f2 Add reviewed extraction fixtures
5dd5507 Add provider-neutral extraction workflow
a035f95 Add explicit provider configuration
71bab06 Add local Qwen extraction provider
eb7a946 Add Gemini extraction provider
8362856 Add provider evaluation tooling
f94289f Document extraction milestone
d68ae68 Fix live provider interoperability
793813a Normalize reciprocal provider relationships
```

Deterministic layout remains independently owned by M5; neither provider emits coordinates or visual placement.
