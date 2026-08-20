# Text-to-Visio Patent Diagram Assistant — Implementation Plan

> **Historical baseline plan.** The geometry-free, deterministic-output architecture in this document was superseded on 2026-08-20 by `docs/HYBRID_AI_ARCHITECTURE.md` and `hybrid_ai_implementation_plan.md`. Keep this file for milestone history; do not use its former AI/layout restrictions for new work.

> **For the implementing agent:** Work milestone by milestone and do not advance until the current acceptance criteria pass. This is a single-developer project targeting a useful baseline in roughly one focused week. Prefer the smallest reliable implementation over speculative generality.

## 1. Goal

Build a Python pipeline that converts a text description into a valid, editable Microsoft Visio `.vsdx` diagram.

The first release supports three related diagram families:

1. Flowcharts and method/process diagrams.
2. System and architecture block diagrams.
3. Simple patent-oriented component schematics with containers, reference numerals, and callouts.

The output is a professional first draft, not a filing-ready patent drawing or a universal Visio generator. A Visio user should normally be able to refine a well-scoped 5–25 element result in approximately 10–30 minutes.

## 2. Delivery Constraints and Development Environment

- Primary development machine: Ubuntu 24.04, Intel i7-9700, 32 GB RAM, no useful modern GPU.
- Local inference target: Qwen 3.5 9B GGUF through `llama.cpp`, starting with `Q6_K` or `UD-Q6_K_XL`.
- Optional hosted inference: Google Gemini API, including its available free tier.
- Microsoft Visio validation machine: a separate Windows laptop.
- Source of truth: one Git repository shared by Ubuntu and Windows.
- Ubuntu performs implementation, local inference, rendering, automated tests, and package validation.
- Windows performs template authoring and real Visio acceptance checks.

Do not move the whole implementation to Windows. Do not automate the Visio GUI through SSH in the baseline. Use Git for code and the canonical template; use Git, SCP, or a shared folder for generated acceptance artifacts.

## 3. Product Scope

### 3.1 Supported in the first release

- Natural-language descriptions mixed with diagramming or patent terminology.
- Top-to-bottom and left-to-right flowcharts.
- System/component block diagrams.
- One-level subsystem or housing containers.
- Directed, undirected, and bidirectional relationships.
- Flow, data, control, power, communication, mechanical, and association edges.
- Solid, dashed, and dotted lines.
- Edge labels.
- Notes and callouts.
- Optional patent-style reference numerals.
- Simple component schematics represented with abstract Visio shapes.
- One generated diagram page per request.
- Editable native Visio shapes and glued connectors.
- Explicit selection between local Qwen and Gemini extraction.

### 3.2 Explicit non-goals for the first release

- Filing-ready design-patent drawings.
- Accurate physical geometry inferred from prose.
- Consistent front/rear/top/bottom/side/perspective product views.
- CAD, mechanical cross-sections, or detailed exploded views.
- Detailed circuit schematics.
- UML, BPMN, network stencils, org charts, floor plans, and every Visio category.
- Arbitrary user-provided stencils.
- Multi-page diagrams generated from one request.
- Perfect orthogonal connector routing.
- Automatic legal or patent-office compliance claims.
- Silent failover from local inference to a cloud provider.

## 4. Architectural Principles

1. **The LLM extracts meaning, not geometry.** It identifies elements, relationships, containers, and labels. It never emits coordinates.
2. **The intermediate representation is authoritative.** Every later stage consumes the same validated `DiagramGraph` contract.
3. **Semantic type and visual shape are separate.** Several semantic types may share one template shape or styling rule.
4. **Layout is deterministic.** Graphviz or a deterministic fallback computes positions.
5. **Rendering copies known-good Visio objects.** Do not generate the complete Visio XML package from scratch.
6. **Providers are interchangeable.** Qwen and Gemini implement one extractor interface.
7. **Cloud use is explicit.** The CLI or configuration selects the provider; the application does not unexpectedly send input elsewhere.
8. **Validate at every boundary.** Preserve intermediate JSON so extraction, layout, and rendering can be debugged independently.

## 5. Runtime Pipeline

```text
raw text
   │
   ▼
[1] extractor provider
    local Qwen OR Gemini
    text → semantic DiagramGraph
   │
   ▼
[2] graph validation and normalization
    IDs, references, containers, edge semantics
   │
   ▼
[3] layout strategy
    flowchart / system block / component schematic
    graph → positioned graph
   │
   ▼
[4] visual mapping
    semantic node/edge types → template shapes and styles
   │
   ▼
[5] VSDX renderer
    positioned graph + template → output.vsdx
   │
   ▼
[6] validation
    ZIP/XML structural checks + Windows Microsoft Visio
```

Keep these stages separate. Provider code must not import renderer code, and renderer code must not contain extraction prompts.

## 6. Repository Layout

```text
project/
  pyproject.toml
  README.md
  src/
    visiogen/
      __init__.py
      models.py
      config.py
      extractor.py
      normalization.py
      layout.py
      shape_mapper.py
      renderer.py
      validation.py
      pipeline.py
      cli.py
      providers/
        __init__.py
        base.py
        local_qwen.py
        gemini.py
      layouts/
        __init__.py
        graphviz_layout.py
        fallback_layered.py
  templates/
    template.vsdx
    TEMPLATE.md
  scripts/
    validate_in_visio.ps1
  tests/
    fixtures/
      text/
      graphs/
    test_models.py
    test_normalization.py
    test_extractors.py
    test_layout.py
    test_shape_mapper.py
    test_renderer.py
    test_validation.py
    test_pipeline.py
  artifacts/                 # generated; ignored except approved fixtures
  implementation_plan.md
  system_overview.md
```

Use `python3`, not `python`, on Ubuntu. Use a project virtual environment or `uv` because the host uses PEP 668.

## 7. Dependencies

Pin tested versions in `pyproject.toml`:

- `pydantic`
- `vsdx`
- `networkx`
- `google-genai` for Gemini
- an OpenAI-compatible client or direct HTTP client for `llama.cpp`
- `pytest`
- `pytest-cov`

System dependencies:

- Graphviz `dot` on Ubuntu and Windows where automated layout tests run.
- `llama.cpp` server on Ubuntu for local Qwen inference.
- Microsoft Visio on Windows is required for preview export and final acceptance.

Do not require Ollama in the baseline. The local provider should target an OpenAI-compatible endpoint so `llama.cpp`, Ollama, or another compatible server can be substituted later.

## 8. Core Data Contract

Define the contract in `src/visiogen/models.py` with Pydantic.

```python
from typing import Literal
from pydantic import BaseModel, Field

DiagramType = Literal[
    "flowchart",
    "system_block",
    "component_schematic",
]

Orientation = Literal["top_to_bottom", "left_to_right"]

NodeType = Literal[
    # Flow and method semantics
    "terminator",
    "process",
    "decision",
    "input_output",
    "data_store",
    "document",
    "predefined_process",
    "delay",
    "note",
    "connector_hub",
    # System and component semantics
    "component",
    "subsystem",
    "controller",
    "processor",
    "memory",
    "database",
    "sensor",
    "actuator",
    "transducer",
    "power_source",
    "communication_module",
    "interface",
    "external_system",
    "service",
    "housing",
]

RelationType = Literal[
    "flow",
    "data",
    "control",
    "power",
    "communication",
    "mechanical",
    "association",
]

DirectionType = Literal[
    "forward",
    "reverse",
    "bidirectional",
    "none",
]

LineStyle = Literal["solid", "dashed", "dotted"]

class DiagramNode(BaseModel):
    id: str
    type: NodeType
    label: str
    parent_id: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None

class DiagramEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: RelationType = "flow"
    direction: DirectionType = "forward"
    label: str | None = None
    style: LineStyle = "solid"

class DiagramGraph(BaseModel):
    title: str
    diagram_type: DiagramType
    orientation: Orientation
    nodes: list[DiagramNode] = Field(default_factory=list)
    edges: list[DiagramEdge] = Field(default_factory=list)
```

Contract rules:

- Extractors leave all geometry fields as `None`.
- IDs are stable within one graph.
- Every edge endpoint references an existing node.
- Every `parent_id` references a container-capable node.
- Baseline containers may be nested only one level deep.
- Reference numerals are optional strings because patent numbering can contain suffixes.
- Reference numerals must be unique when present.
- `notes` are retained in JSON but are not rendered unless explicitly mapped to a note.
- All persisted stage boundaries use JSON.

## 9. Visual Template Vocabulary

The semantic vocabulary does not require 25 unique Visio masters. Start with approximately 15–20 reliable visual templates:

### Flow templates

- terminator
- process
- decision
- input_output
- data_store
- document
- predefined_process
- delay
- note
- connector_hub

### System/component templates

- component_rectangle
- subsystem_container
- controller
- memory
- database
- sensor
- transducer
- power_source
- interface
- external_system
- service
- housing_container
- reference_callout

If two templates prove visually redundant, reuse one through `shape_mapper.py`. Semantic identity remains in the graph even when visual geometry is shared.

Every palette shape in `template.vsdx` must contain a stable lookup key such as `__template_controller__`, not ordinary visible labels that could collide with generated content.

## 10. Milestones

### M0 — Repository scaffold and test harness

Create the repository layout, virtual environment configuration, package metadata, and empty tests.

Acceptance:

- `python3 -m pytest` runs successfully.
- All package imports resolve.
- `python3 -m visiogen.cli --help` runs.
- Generated artifacts and local model files are ignored by Git.

### M1 — Data contract and normalization

Implement Pydantic models and `normalize_graph()`.

Normalization must:

- Reject duplicate node or edge IDs.
- Reject dangling edge endpoints.
- Reject invalid container references and cycles in containment.
- Enforce one-level containment for the baseline.
- Reject duplicate reference numerals.
- Assign deterministic missing edge IDs if the provider omits them only when the provider DTO allows omission.
- Default ambiguous diagram types to `system_block` only when system/component language is present; otherwise use `flowchart`.
- Never manufacture missing domain components.

Acceptance:

- Unit tests cover valid flowcharts, valid system diagrams, containers, duplicate IDs, dangling edges, duplicate reference numerals, and containment cycles.
- Round-trip JSON serialization preserves semantics.
- Geometry is absent before layout.

### M2 — Early VSDX feasibility spike

Front-load the highest-risk dependency before building the full extractor.

On Windows:

1. Create a minimal Visio template with a process shape, component rectangle, container, callout, and connector.
2. Commit the template.

On Ubuntu:

1. Open it with the pinned `vsdx` version.
2. Copy and relabel shapes.
3. Position and resize copies.
4. Create and glue at least one connector.
5. Save a new `.vsdx`.

Back on Windows:

1. Open the output without a repair prompt.
2. Move both endpoint shapes.
3. Confirm the connector remains attached.

Stop and reassess the renderer library if this spike fails. Do not build later milestones on an unverified connector assumption.

Acceptance:

- One generated file passes structural ZIP/XML checks.
- Visio opens it without repair.
- Copied shapes remain editable.
- The connector is genuinely glued.
- The exact working `vsdx` APIs are captured in renderer tests and comments.

### M3 — Complete template and visual mapper

Expand `template.vsdx` to the agreed palette. Document each lookup key in `templates/TEMPLATE.md`.

Implement mappings such as:

```text
processor             → controller
communication_module  → component_rectangle
actuator               → component_rectangle
housing                → housing_container
subsystem              → subsystem_container
```

Map relation types to connector styling:

```text
flow          → solid, forward arrow
control       → solid, forward arrow
power         → solid, forward arrow, distinct line weight
communication → solid, bidirectional when requested
data          → solid, direction from graph
mechanical    → solid or dashed, no forced arrow
association   → dotted, no forced arrow
```

Acceptance:

- Every `NodeType` resolves to a valid template key.
- Every relation/direction/style combination resolves deterministically.
- Unknown semantic or template keys produce clear errors.
- The complete template opens correctly in Visio.

### M4 — Provider-neutral extraction

Define an extractor protocol:

```python
class DiagramExtractor(Protocol):
    def extract(self, text: str) -> DiagramGraph: ...
```

Use provider-specific DTOs that exclude `x`, `y`, `width`, and `height` entirely. Do not merely ask the model to leave them null.

Shared system-prompt requirements:

- Determine the diagram family.
- Extract only elements supported by the schema.
- Preserve explicit labels and technical terms.
- Infer relationship direction from the text.
- Use `parent_id` only for explicit or strongly implied containment.
- Preserve provided patent reference numerals.
- Do not invent reference numerals unless the request asks for automatic numbering.
- Do not invent physical geometry.
- Use `component` when no more specific system type is justified.
- Use `process` when no more specific flow type is justified.
- Return schema-conforming structured output only.

#### M4A — Local Qwen provider

Target an OpenAI-compatible local endpoint, defaulting to `http://127.0.0.1:8080/v1`.

Recommended initial model:

- Qwen 3.5 9B GGUF
- Start with `Q6_K` or `UD-Q6_K_XL`
- Keep context conservative for CPU inference; start at 8K unless fixtures demonstrate a need for more.
- Use deterministic or low-variance generation settings appropriate to the model.

The provider must expose endpoint and model configuration rather than hardcoding a runtime.

#### M4B — Gemini provider

Use the official Google SDK and structured output support. Select the Gemini model through configuration because free-tier model availability can change.

Environment variables:

```text
VISIOGEN_LLM_PROVIDER=local|gemini
VISIOGEN_LOCAL_BASE_URL=http://127.0.0.1:8080/v1
VISIOGEN_LOCAL_MODEL=<configured model name>
GEMINI_API_KEY=<secret>
VISIOGEN_GEMINI_MODEL=<configured model name>
```

Do not commit keys. Do not silently switch providers after an error.

Extraction resilience:

- Validate every response with Pydantic.
- Allow one schema-repair retry with explicit validation errors.
- Fail with a clear provider/extraction error after the retry.
- Log request IDs and timing, but not credentials.
- Save accepted stage JSON when debug output is enabled.

Acceptance:

- Both providers pass the same fixture contract tests.
- Tests use mocked provider responses; normal CI does not require API access or a running model.
- An opt-in integration marker tests live Qwen and Gemini.
- Extracted graphs contain no geometry fields.
- Five flowchart and five system/component prompts produce valid references.

### M5 — Layout strategies

Use Graphviz as the primary layout engine. Generate DOT, invoke `dot -Tplain`, and parse coordinates. Keep a small deterministic layered fallback for environments without Graphviz.

Coordinate contract:

- `layout.py` returns final center-based coordinates in inches using Visio’s bottom-left origin.
- `renderer.py` must not invert the y-axis again.
- Width and height are explicit positive floats.
- Page dimensions are returned or calculated alongside the graph.

Strategies:

#### Flowchart

- Default rank direction: top-to-bottom.
- Respect requested left-to-right orientation.
- Keep decisions and their branches near one another.
- Use fixed minimum rank and node spacing.

#### System block

- Default rank direction: left-to-right.
- Weight data/control/power direction for ordering.
- Avoid treating undirected associations as process flow.
- Use Graphviz clusters for one-level subsystems.

#### Component schematic

- Place the main housing/container first.
- Arrange contained components in a readable grid or Graphviz cluster.
- Keep callout space around the outside of the container.
- Treat placement as abstract, not physically accurate.

Shape sizing:

- Define minimum sizes by visual template.
- Expand width within a bounded range for longer labels.
- Wrap labels deterministically rather than creating extremely wide nodes.
- Reserve space for reference numerals.

Acceptance:

- Every node has positive geometry.
- No ordinary node bounding boxes overlap in representative fixtures.
- Children remain inside their container bounds.
- Layout is deterministic for the same JSON input.
- A 25-element system fixture remains readable on a grown page.
- Fallback layout produces valid, if less polished, output.

### M6 — Renderer

Use the pinned `vsdx` APIs proven in M2.

Rendering order:

1. Open `templates/template.vsdx`.
2. Create or clear the output page according to the proven template strategy.
3. Render outer containers.
4. Copy and position ordinary nodes.
5. Set dimensions and visible labels.
6. Add reference numerals and callouts.
7. Create connectors using the node ID → Visio shape map.
8. Set arrow direction, line style, line weight, and edge labels.
9. Verify connector glue using the library/package relationships available in the pinned version.
10. Remove or isolate palette shapes.
11. Set page size and save to a new path.

Renderer rules:

- Never mutate the canonical template in place.
- Fail clearly if any node lacks geometry.
- Fail clearly if a template key is missing.
- Preserve editable text.
- Use black-and-white, restrained defaults suitable for technical diagrams.
- Do not claim that the styling satisfies a patent office’s rules.

Acceptance:

- Flowchart fixture: all nodes and edges appear.
- System fixture: containers and typed relationships appear.
- Headphone fixture: housing, components, power/data/control links, and reference numerals appear.
- Output opens without repair in Visio.
- Shapes can be moved and edited.
- Connectors remain attached after movement.

### M7 — Pipeline, CLI, and intermediate artifacts

Public API:

```python
def generate_vsdx(
    text: str,
    output_path: str,
    provider: str,
    *,
    debug_dir: str | None = None,
) -> None:
    ...
```

CLI examples:

```bash
python3 -m visiogen.cli generate \
  --provider local \
  --text "Start with login, then validate credentials..." \
  --output artifacts/login.vsdx

python3 -m visiogen.cli generate \
  --provider gemini \
  --input-file tests/fixtures/text/headphone.txt \
  --output artifacts/headphone.vsdx \
  --debug-dir artifacts/headphone-debug

python3 -m visiogen.cli render-graph \
  --graph tests/fixtures/graphs/headphone.json \
  --output artifacts/headphone-no-llm.vsdx
```

Debug directory contents:

```text
01-extracted.json
02-normalized.json
03-laid-out.json
layout.dot
pipeline.log
```

Acceptance:

- Rendering from saved JSON does not require an LLM.
- Provider selection is explicit and visible in logs.
- A provider failure does not delete prior debug artifacts.
- Empty or non-diagram text produces one clear error or a deliberately simple single-node result; it never crashes obscurely.

### M8 — Cross-platform validation harness

#### Ubuntu validation

For every generated `.vsdx`:

- Confirm it is a readable ZIP.
- Confirm required package files and relationships exist.
- Parse all XML files.
- Confirm at least one page exists.
- Compare expected node/edge labels and counts where practical.
- Do not substitute a third-party VSDX renderer for Microsoft Visio.

Clearly document that package validation does not guarantee Visio acceptance.

#### Windows validation

Create `scripts/validate_in_visio.ps1` to assist a logged-in user with:

- Opening every acceptance file through Visio COM where supported.
- Recording document/page/shape counts.
- Optionally exporting a preview.
- Closing without modifying the fixture.
- Writing a machine-readable validation report.

Manual checklist:

- No repair prompt.
- Correct page count.
- All labels visible.
- Containers contain intended children.
- Arrow directions are correct.
- Connector labels are readable.
- Moving endpoint shapes keeps connectors attached.
- Diagram can be edited and saved.

Do not rely on noninteractive SSH sessions to validate the Visio GUI.

Acceptance:

- All acceptance artifacts pass Ubuntu structural validation.
- All acceptance artifacts pass Windows Visio open/edit/save checks.
- The Git commit and fixture names are recorded with the Windows result.

### M9 — End-to-end acceptance set

Maintain at least these text fixtures:

1. Three-step linear flow.
2. Branching login decision with yes/no labels.
3. Method flow with a loop and failure path.
4. Single isolated process.
5. Ambiguous text with no obvious diagram.
6. Basic processor-memory-sensor system.
7. Bidirectional communication architecture.
8. System with one nested subsystem.
9. Eco-friendly headphone component diagram with housing, battery, controller, sensor, driver, charging interface, and energy-harvesting module.
10. Patent-style numbered schematic request.

Release acceptance:

- Every successful fixture generates valid stage JSON and `.vsdx`.
- No output triggers a Visio repair prompt.
- All references and parent relationships are valid.
- Expected node and edge semantics match reviewed fixtures.
- Typical 5–25 element diagrams are useful first drafts.
- Known limitations are documented rather than hidden.

## 11. Suggested Seven-Day Sequence

### Day 1

- Scaffold repository.
- Implement models and normalization with tests.
- Establish Git workflow between Ubuntu and Windows.

### Day 2

- Author the minimal Windows template.
- Complete the VSDX feasibility spike.
- Lock the working `vsdx` version and APIs.

### Day 3

- Expand the template and shape mapper.
- Implement renderer primitives for shapes, containers, callouts, and connectors.

### Day 4

- Implement Graphviz and fallback layouts.
- Render saved graph fixtures without an LLM.

### Day 5

- Implement local Qwen and Gemini providers.
- Add shared extraction prompts, validation, and retry behavior.

### Day 6

- Complete pipeline and CLI.
- Add structural validation and acceptance artifacts.

### Day 7

- Run Windows Visio acceptance.
- Fix package/connector issues.
- Document limitations and usage.

If the M2 connector spike exposes library limitations, revise the schedule immediately. Reliable `.vsdx` output is more important than completing every semantic type in the first week.

## 12. Testing Strategy

- Unit tests for models, normalization, mapping, and coordinate conversion.
- Golden JSON fixtures for extraction semantics.
- Snapshot tests for DOT generation.
- Geometry tests for positive dimensions, overlap, and containment.
- Renderer smoke tests on saved graphs without LLM calls.
- Mocked provider contract tests.
- Opt-in live provider tests.
- ZIP/XML package validation for every output.
- Manual and assisted Visio acceptance on Windows.

Tests must distinguish:

1. Semantic correctness.
2. Layout quality.
3. Package integrity.
4. Actual Visio compatibility.

Passing one category does not imply the others pass.

## 13. Risks and Mitigations

### `vsdx` connector or cross-page APIs differ from documentation

Mitigation: M2 spike before full implementation; pin the proven version; test connector glue in real Visio.

### Template binary is difficult to merge

Mitigation: designate one template editor at a time; keep lookup keys documented; commit intentional template revisions separately.

### Local Qwen is too slow or inaccurate

Mitigation: benchmark representative fixtures; lower context; compare quantizations; retain Gemini as an explicit provider option.

### The LLM invents components or relations

Mitigation: narrow structured schema, conservative prompt, one repair retry, reviewed golden fixtures, and visible intermediate JSON.

### System diagrams become visually crowded

Mitigation: Graphviz primary layout, page growth, bounded label wrapping, clusters, and an explicit 5–25 element quality target.

### Patent expectations drift toward physical design drawings

Mitigation: keep the product boundary explicit. This release creates abstract flow, system, and simple component diagrams—not precise product geometry or filing-ready design-patent views.

## 14. Post-Baseline Extensions

Only pursue these after the acceptance set passes:

- Multi-page figure sets.
- A `PatentDocument` model coordinating figures and reference numerals.
- More sophisticated callout placement.
- Orthogonal connector routing.
- User-editable style themes.
- Additional Visio stencil packs.
- Input sketches or images.
- SVG/vector renderer for technical line art.
- FreeCAD/Blender/CAD integration for consistent physical views.
- Model quality benchmark reports and provider auto-selection, with user consent.

## 15. Definition of Done

The baseline is done when a user can describe a supported flow, system, or abstract component diagram; explicitly select local Qwen or Gemini; receive an editable `.vsdx`; inspect saved intermediate JSON; and open, move, relabel, connect, and save the result in Microsoft Visio without a repair prompt.
