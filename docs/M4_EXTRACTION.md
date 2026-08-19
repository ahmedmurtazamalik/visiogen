# M4 Acceptance — Fixture Corpus and Provider-Neutral Extraction

**Status:** ACCEPTED — CODEX CLI IS THE PREFERRED PROVIDER
**Platform:** Ubuntu, Python 3.11
**Authoritative contract:** `visiogen.models.DiagramGraph`
**Live evaluation date:** 2026-08-19

## Accepted provider decision

Visiogen retains a provider-neutral extraction boundary and requires explicit provider selection. The accepted roles are:

1. **Codex CLI (`gpt-5.6-sol`) — preferred provider.** This is the accepted high-quality path for the current trusted, local-user application.
2. **Gemini — optional hosted API provider.** Real transport and structured-output interoperability are proven, but the last complete corpus showed semantic drift and a later corrected run was quota-blocked.
3. **Local Qwen — optional experimental/offline provider.** Real llama.cpp interoperability is proven, but Qwen3.5-9B is too slow and semantically unreliable on the current CPU host to be preferred.

There is no automatic fallback or provider substitution. A Codex failure is surfaced as a typed provider error unless the caller explicitly selects another provider.

Codex CLI uses the locally authenticated ChatGPT/Codex account. It does not require a Visiogen API key, but it does require the `codex` executable, a valid local Codex login, network access, and available plan capacity. This path is intended for trusted local execution; it is not a shared personal-subscription backend for an untrusted public service.

## Scope implemented

- Ten reviewed text fixtures under `tests/fixtures/text/`.
- Nine immutable reviewed canonical graphs under `tests/fixtures/graphs/expected/`.
- One explicit ambiguous-input baseline: `NoDiagramContentError`; Visiogen does not manufacture a node when no definite diagram is present.
- Provider-neutral extraction, a shared geometry-free prompt, canonical validation, deterministic normalization, and exactly one schema-repair attempt.
- Explicit `VISIOGEN_` configuration with selected-provider-only requirements and no import-time environment reads.
- Codex CLI, OpenAI-compatible local Qwen, and Google Gemini adapters using the same extraction workflow, DTO schema, normalization, and errors.
- An explicit provider factory; no silent provider fallback.
- Typed process/transport, malformed-output, schema-validation, timeout, and no-diagram failures.
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

## Automated evidence

The controlled provider contracts remain deterministic unit evidence, not live-provider evidence. They prove request/process construction, parsing, shared canonical validation, exactly one repair attempt, explicit provider selection, and typed failures.

Current complete-suite evidence:

```text
167 tests passed
96% total coverage
Codex CLI adapter: 94% coverage
Codex provider factory: 100% coverage
```

Every Codex source change was introduced through RED → GREEN tests before implementation.

## Explicit live-evaluation method

Codex is the preferred command:

```bash
VISIOGEN_PROVIDER=codex \
VISIOGEN_CODEX_MODEL=gpt-5.6-sol \
VISIOGEN_TIMEOUT_SECONDS=120 \
uv run python scripts/evaluate_providers.py \
  --provider codex \
  --artifact-root artifacts/provider-evaluation/live-acceptance-codex
```

Optional providers remain independently selectable:

```bash
uv run python scripts/evaluate_providers.py --provider local
uv run python scripts/evaluate_providers.py --provider gemini
```

The evaluator never substitutes one provider for another. Actual canonical graphs and field-level mismatch reports are written only beneath the selected artifact root.

## Real Codex CLI evidence

Runtime identity:

```text
Codex CLI: 0.146.0
provider: openai
model: gpt-5.6-sol
sandbox: read-only
session mode: ephemeral
```

The production `CodexCLIExtractor` completed the immutable ten-prompt corpus through ten real authenticated Codex processes:

```text
cases: 10
valid diagram graphs: 9
expected no-diagram outcomes: 1
transport/process/schema failures: 0
strict fixture matches: 1
strict fixture mismatches: 9
source-faithful semantic review: 10/10 accepted
```

Evidence:

```text
artifacts/provider-evaluation/live-acceptance-codex/codex/*.actual.json
artifacts/provider-evaluation/live-acceptance-codex/codex/semantic-mismatch-report.json
```

The field-level strict report is deliberately retained. Its nine mismatches are not being relabeled or hidden. Review showed that they consist of generated titles, equivalent concise labels and IDs, corresponding endpoint-ID changes, and equivalent branch wording. One login output node is classified as `input_output`, which follows the current extraction instruction more directly than the older fixture's `process` classification. No Codex output omitted or invented a component, containment relation, connection, flow branch, loop, reference numeral, or expected no-diagram outcome.

The immutable expected graphs were not edited to force a pass. M4 acceptance is based on both machine validation and explicit source-to-graph semantic review, not a false claim that provider-generated identity strings are byte-equivalent.

### Codex isolation and schema controls

Each extraction:

- runs in a fresh temporary directory;
- uses `--ephemeral` and `--ignore-rules`;
- uses a read-only sandbox and no repository dependency;
- receives the user description through standard input rather than shell interpolation;
- writes only a final response file in the temporary directory;
- enforces the extraction DTO with `--output-schema`;
- transforms optional fields into Codex-compatible required-but-nullable properties;
- captures CLI output rather than forwarding it into application logs;
- applies an explicit timeout; and
- passes the result through the unchanged shared normalization workflow.

## Real Gemini evidence

A complete authenticated `gemini-3.6-flash` run produced valid canonical output for all nine diagram prompts and the expected no-diagram outcome:

```text
cases: 10
strict matches: 1
strict mismatches: 9
transport/schema failures: 0
```

A corrected-prompt `gemini-3.7-flash` probe fixed the previously observed difficult taxonomy/topology failures, but the subsequent full corpus run reached the account's daily quota. Gemini remains an explicit optional provider; this incomplete run is not represented as full acceptance.

Evidence:

```text
artifacts/provider-evaluation/gemini/
artifacts/provider-evaluation/live-acceptance/gemini/
```

## Real local Qwen evidence

Provider endpoint and served model:

```text
OpenAI-compatible llama.cpp: http://127.0.0.1:8080/v1
served model ID: qwen3.5-9b
model artifact: unsloth/Qwen3.5-9B-GGUF:Q5_K_M
```

The final corpus produced nine canonical graphs plus the expected no-diagram outcome. `eco_headphone` exceeded the initial 300-second timeout, then succeeded on a 600-second retry in 424.74 seconds.

```text
cases: 10
saved canonical graphs: 9
strict matches: 1
strict mismatches: 9
remaining transport/schema failures after retry: 0
manual source-faithful outcomes: 4/10
```

Substantive drift remained in six cases: incorrect service/gateway taxonomy, incorrect housing containment, an invented login process, a missing loop continuation, an omitted subsystem container, and missing canonical patent reference-number fields. This is why Qwen3.5-9B remains experimental rather than silently backing Codex.

Evidence:

```text
artifacts/provider-evaluation/prompt-v2/local/*.actual.json
artifacts/provider-evaluation/prompt-v2/local/semantic-mismatch-report.json
```

## Live interoperability corrections retained

Real inference produced regression-tested corrections:

1. Gemini now uses raw `response_json_schema` rather than an incompatible Pydantic `response_schema` path.
2. Qwen uses JSON Schema output, bounded generation, and disabled thinking behavior.
3. Equivalent reciprocal forward relationships normalize to one bidirectional edge.
4. Reports include provider/model identity, UTC evaluation time, and field-level differences while ignoring generated edge IDs.
5. The shared prompt requires minimal source-faithful semantics and explicit flow/taxonomy handling.
6. Codex strict-output schemas require all object properties while preserving optionality through nullable field types.

## M4 gate decision

**M4 is accepted with Codex CLI as the preferred provider.** This decision is supported by:

- a real production-adapter corpus run;
- ten valid structured outcomes;
- zero process, schema, or canonical-validation failures;
- explicit review of every actual graph against its source prompt; and
- 10/10 source-faithful semantic acceptance.

Qwen and Gemini remain supported only through explicit selection. Their residual evidence remains documented rather than being treated as a silent fallback or erased.

Deterministic layout remains independently owned by M5; no extraction provider emits coordinates or visual placement. M5 closure may resume after this recorded provider decision.

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
2014335 Record live provider acceptance evidence
06e8a92 Add preferred Codex CLI extraction provider
```
