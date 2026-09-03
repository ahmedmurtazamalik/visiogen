# Generation v2 Diagram Specification

**Status:** G1 implemented contract

`DiagramSpecification` is the versioned boundary between a user's requested
meaning and later visual construction. It records what the diagram must
communicate without choosing coordinates, connector routes, Visio masters, or
package details.

## Inputs

The `generate` command accepts exactly one source:

```bash
uv run visiogen generate --text "Create a left-to-right sensor system" ...
uv run visiogen generate --input-file request.txt ...
uv run visiogen generate --spec-file reviewed-spec.yaml ...
```

JSON files must use `.json`; YAML files must use `.yaml` or `.yml`. YAML is read
with the safe loader, so executable constructors and template syntax are not
supported. Unknown fields are rejected.

Text input is converted by one structured model call. A schema or deterministic
constraint failure permits one repair call, after which generation fails clearly.
Specification files are validated locally and do not incur that model call.

## Contract

Version 1 records:

- purpose, audience, diagram type, notation, orientation, and primary flow;
- required and optional objects and relationships;
- exact labels, reference numerals, containment, and visual importance;
- ordering, adjacency, alignment, and separation constraints;
- shape-family, color, typography, and connector-style preferences;
- permitted ambiguities and explicit unknowns;
- measurable visual requirements and forbidden conditions.

Deterministic validation rejects duplicate IDs, unknown references, self or cyclic
containment, malformed kind-specific constraints, incomplete measurements, and
cycles among hard ordering constraints. The model never decides whether those
conditions are structurally valid.

## Evidence

Every production generation run persists `03-validated-specification.json`.
Text-derived runs additionally retain the specification system/user prompts, raw
responses, exact provider transport prompts, request IDs, attempt count, and
elapsed time. The manifest binds the validated specification and its JSON Schema
with SHA-256 hashes.

The validated specification is serialized as the authoritative input to the
existing visual designer. Rendering remains on the Generation v1 implementation
until the later construction-plan and renderer phases replace it.
