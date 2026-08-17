# Text-to-Visio Patent Diagram Assistant — System Overview

## What this project is

This project turns a text description into an editable Microsoft Visio `.vsdx` diagram.

It is intended to create useful first drafts in three related categories:

1. Flowcharts and method/process diagrams.
2. System and architecture block diagrams.
3. Simple patent-oriented component schematics with containers, reference numerals, and callouts.

The goal is not a magical text-to-anything drawing system. The goal is a dependable assistant that produces a structured, editable starting point which a Visio user can refine.

For an appropriately scoped 5–25 element description, the target is a diagram that normally requires about 10–30 minutes of human refinement rather than being redrawn from scratch.

## Why the scope is broader than eight flowchart shapes

The original concept used eight flowchart shapes only as a low-risk proof of concept. That was never an architectural limit.

Once the renderer can safely copy shapes, place them, label them, and glue connectors, expanding the template is comparatively inexpensive. The revised system therefore supports a curated visual palette for both flow and system diagrams.

Examples include:

- Start/end, process, decision, input/output, document, data store, note, and delay.
- Generic components, subsystems, controllers, processors, memory, databases, sensors, transducers, power sources, communication modules, interfaces, services, external systems, and housings.
- Containers, patent-style reference callouts, and several connector styles.

The system deliberately does not attempt to support every Visio stencil. A focused vocabulary of approximately 15–20 reliable visual templates can represent a larger semantic vocabulary because multiple semantic types may reuse the same geometry.

For example, an actuator and a communication module may both use a technical rectangle in the first release while retaining different semantic types in the graph. This keeps the model expressive without forcing every concept to have a novel shape.

## What a useful result looks like

Given this description:

> Create a diagram of an eco-friendly wireless headphone containing a recycled-material housing, replaceable battery, acoustic driver, Bluetooth controller, energy-harvesting module, charging interface, and sensor. The energy-harvesting module charges the battery, which powers the controller and driver. The controller receives data from the sensor and sends audio signals to the driver.

The system should create an editable abstraction containing:

```text
Headphone housing
  ├── Recycled-material structure
  ├── Replaceable battery
  ├── Energy-harvesting module
  ├── Bluetooth controller
  ├── Acoustic driver
  ├── Charging interface
  └── Sensor
```

With relationships such as:

```text
Energy-harvesting module → Battery       [power]
Charging interface → Battery             [power]
Battery → Bluetooth controller           [power]
Battery → Acoustic driver                [power]
Sensor → Bluetooth controller            [data]
Bluetooth controller → Acoustic driver   [control/audio]
```

The output would not look like a precise three-dimensional headphone. It would be a clean component or system diagram that communicates the invention’s parts and relationships. A patent professional could move components, adjust callouts, change labels, or restyle connectors directly in Visio.

## Why not ask an LLM to generate a `.vsdx` directly?

Two problems make that unreliable.

First, `.vsdx` is a ZIP package containing many related XML files. Pages, shapes, masters, relationships, and connectors must agree with one another. Small mistakes can cause Visio to reject or repair the file.

Second, language models are much better at interpreting meaning than positioning diagram elements. Asking an LLM for exact coordinates commonly produces overlaps, bad spacing, and inconsistent geometry.

The system therefore separates understanding from layout and rendering.

## The pipeline

```text
Text description
      │
      ▼
1. Extract meaning
   Local Qwen or Gemini
      │
      ▼
2. Validate and normalize the graph
      │
      ▼
3. Choose and run a deterministic layout
      │
      ▼
4. Map semantic types to visual templates
      │
      ▼
5. Copy known-good Visio shapes and connect them
      │
      ▼
6. Validate the generated package and open it in Visio
      │
      ▼
Editable output.vsdx
```

Each stage has a narrow contract and can be improved independently.

## Stage 1 — Understand the text

The LLM converts the description into a semantic graph.

It identifies:

- The diagram family.
- Elements or components.
- Labels.
- Directed or undirected relationships.
- Relationship meanings such as flow, data, control, power, or communication.
- Explicit subsystem or housing containment.
- Optional reference numerals.

It does not choose coordinates, dimensions, connector routes, or Visio master IDs.

A simplified result might look like:

```json
{
  "title": "Eco-friendly headphone system",
  "diagram_type": "component_schematic",
  "orientation": "left_to_right",
  "nodes": [
    {
      "id": "n1",
      "type": "housing",
      "label": "Headphone housing",
      "reference_number": "100"
    },
    {
      "id": "n2",
      "type": "power_source",
      "label": "Replaceable battery",
      "parent_id": "n1",
      "reference_number": "110"
    }
  ],
  "edges": []
}
```

The graph is saved as JSON so later stages can be tested without calling an LLM again.

## LLM options

### Local Qwen

The default local option is Qwen 3.5 9B in GGUF format, served through a local OpenAI-compatible `llama.cpp` endpoint.

The Ubuntu machine has an Intel i7-9700 and 32 GB RAM but no useful modern GPU, so inference will run primarily on the CPU. Qwen 3.5 9B is small enough to fit comfortably while remaining capable of structured extraction.

The initial quantization candidates are:

- `Q6_K`, approximately 6.95 GiB.
- `UD-Q6_K_XL`, approximately 8.16 GiB.

Advantages:

- No per-request API cost.
- Works offline.
- Full control over the runtime.
- Stable option even if hosted free tiers change.

Tradeoffs:

- Slower than hosted inference.
- May make more semantic mistakes on ambiguous or long descriptions.
- Requires the local model server to be running.

### Gemini API

Gemini is the optional hosted provider. It offers strong structured-output support and may be available through a free tier, depending on Google’s current models, quotas, and terms.

Advantages:

- Faster than CPU inference.
- Stronger handling of difficult or ambiguous descriptions.
- No local model installation.

Tradeoffs:

- Requires internet access and an API key.
- Free-tier limits and model availability can change.
- Production use may eventually require billing.

The application makes provider selection explicit. It does not silently fall back from local Qwen to Gemini.

Because both providers implement the same extractor interface, they can be compared on the same fixtures and replaced without changing layout or rendering.

## Stage 2 — Validate and normalize

LLM output is not trusted merely because it is valid JSON.

The normalization stage checks:

- Node and edge IDs are unique.
- Every edge references existing nodes.
- Every container reference points to a valid container.
- Containers do not form cycles.
- Reference numerals are unique when supplied.
- The graph uses supported semantic types and relationships.
- Geometry is still absent.

Invalid output receives at most one schema-repair attempt. If it remains invalid, the application reports a clear extraction error rather than allowing a broken graph into the renderer.

## Stage 3 — Lay out the diagram

Layout is deterministic and primarily uses Graphviz.

The strategy depends on the diagram family.

### Flowcharts

- Usually top-to-bottom.
- Can run left-to-right when requested.
- Decisions and branches are layered according to graph structure.

### System block diagrams

- Usually left-to-right.
- Data, power, and control relationships influence ordering.
- Subsystems can be rendered as Graphviz clusters.

### Component schematics

- A housing or main container is placed first.
- Contained components are arranged inside it.
- Space is reserved for callouts around the outside.
- Placement is communicative, not physically exact.

Graphviz produces positions that are converted into inches and normalized to Visio’s bottom-left coordinate system. A simpler deterministic layered layout remains available as a fallback when Graphviz is unavailable.

The layout stage also:

- Chooses minimum dimensions by shape family.
- Wraps long labels.
- Grows the page for larger diagrams.
- Prevents ordinary node overlap.
- Keeps child components inside their container.

## Stage 4 — Map meaning to appearance

Semantic meaning and visual appearance are intentionally separate.

For example:

```text
Semantic type             Visual template
-------------             ---------------
processor                 controller
communication_module      component_rectangle
actuator                   component_rectangle
housing                    housing_container
subsystem                  subsystem_container
power_source               power_source
```

This separation has two benefits:

1. New semantic types do not always require new Visio shapes.
2. Visual styling can change without changing LLM extraction.

Edges are mapped similarly:

- Flow and control usually use forward arrows.
- Communication may be bidirectional.
- Power can use a distinct line weight.
- Mechanical relations may have no arrow.
- Associations may use dotted lines.
- Optional elements or connections may use dashed styling.

## Stage 5 — Build the Visio file

The renderer does not generate the whole Visio package from scratch.

A hand-authored `template.vsdx` contains known-good examples of the required shapes. Each template shape has a stable internal text key such as:

```text
__template_process__
__template_controller__
__template_sensor__
__template_power_source__
__template_reference_callout__
```

At generation time, the renderer:

1. Opens the template.
2. Copies the correct shape for each graph element.
3. Sets its size and position.
4. Replaces the template key with the real label.
5. Adds a reference numeral when requested.
6. Creates connectors for graph relationships.
7. Glues connector endpoints to their shapes.
8. Applies arrow and line styles.
9. Removes or isolates the original palette shapes.
10. Saves a new `.vsdx` without modifying the template.

Starting from valid Visio objects greatly reduces the chance of corrupt output and preserves editability.

## Stage 6 — Validate the result

Validation has two levels.

### Automated Ubuntu checks

The validator confirms that the `.vsdx`:

- Is a readable ZIP archive.
- Contains required Visio package files.
- Contains parseable XML.
- Has at least one page.
- Contains expected labels and approximate shape/connector counts where practical.

LibreOffice may optionally perform a stronger headless smoke test.

These checks detect corruption but cannot prove that Microsoft Visio will accept every relationship without repair.

### Real Windows Visio checks

The Windows laptop is the final compatibility environment.

At milestone checkpoints, it will:

- Pull the tested Git commit.
- Open generated acceptance artifacts in Visio.
- Confirm there is no repair prompt.
- Verify labels, containers, arrows, and callouts.
- Move shapes to confirm connectors remain glued.
- Edit and save the document.

A PowerShell script may use Visio’s COM interface to open a test set, count objects, and export previews. Final visual review remains interactive.

## Cross-machine development approach

Development remains on Ubuntu. The Windows laptop is a specialized acceptance machine, not the primary development environment.

Recommended exchange:

```text
Git repository
  ├── Python code
  ├── tests and synthetic fixtures
  ├── canonical template.vsdx
  └── Windows validation scripts

Generated artifacts
  └── transferred through Git when approved, SCP, or a shared folder
```

SSH is useful for file transfer or commands but not for inspecting Visio’s GUI. If remote visual operation is ever needed, an interactive desktop method such as RDP is more suitable. For the baseline, manually opening the Windows laptop at renderer checkpoints is simpler.

## What the baseline should do well

### Very suitable

- Linear methods.
- Branching workflows.
- Approval and rejection processes.
- Data-processing pipelines.
- Processor/memory/sensor block diagrams.
- Power and control relationships.
- Systems with one level of subsystem grouping.
- Abstract product component diagrams.
- Simple numbered patent schematics.

### Expected quality by size

#### 1–10 elements

Usually close to immediately usable, with minor label or spacing adjustments.

#### 10–25 elements

The main target. Expected to be a useful first draft requiring approximately 10–30 minutes of Visio refinement.

#### 25–40 elements

Structurally useful, but likely to require more work because of connector crossings, long labels, and page growth.

#### More than 40 dense elements

May preserve useful structure but is outside the baseline quality target for a single generated page.

## Patent-related capability boundaries

### Method patent figures

A strong fit. The pipeline can represent ordered steps, decisions, loops, alternatives, and failure paths.

### System and architecture patent figures

Also a good fit after expanding the template vocabulary. Controllers, sensors, memories, transducers, power sources, and external systems can be represented as abstract blocks with typed connections.

### Simple component schematics

Feasible as abstract diagrams. The system can generate housings, contained components, callouts, reference numerals, and approximate relationships. It does not claim physically exact placement.

### Complex physical and design-patent drawings

Not a baseline target. Text alone cannot reliably define exact product geometry or maintain consistent ornamental details across perspective and orthographic views. Those tasks would require sketches, CAD, vector illustration, or a human designer.

The system can still assist those workflows later by extracting component inventories, assigning reference numerals, proposing figure sets, and assembling labels and callouts.

## Why this architecture can grow

Each capability has a clear extension point:

- Better reasoning: replace or add an extractor provider.
- More concepts: extend semantic types.
- More visual shapes: add template entries and mappings.
- Better placement: replace the layout strategy.
- Better connectors: improve routing without changing extraction.
- Multiple patent figures: introduce a higher-level `PatentDocument` model.
- Physical drawings: add SVG or CAD renderers while retaining semantic extraction.

The baseline is therefore useful on its own without pretending to solve every diagram category, and it provides a foundation for more ambitious patent-figure assistance later.

## Practical first-release definition

The first release is successful when a user can:

1. Describe a supported flow, system, or abstract component diagram.
2. Choose local Qwen or Gemini.
3. Receive a validated semantic graph.
4. Receive an editable `.vsdx`.
5. Open it in Microsoft Visio without a repair prompt.
6. Move, relabel, reconnect, and save its shapes.
7. Use it as a meaningful first draft rather than starting from a blank page.
