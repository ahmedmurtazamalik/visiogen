# Generation v2 Construction Plan

**Status:** G3 implementation verified; real-model gate pending clean checkpoint

`VisioConstructionPlan` is the strict boundary between a validated professional
specification and later deterministic compilation. The AI chooses the complete
visual construction; Python verifies schema, references, semantic coverage, and
coarse invariants. G4 will add detailed compilation and geometric diagnostics.

Version 1 records page size/orientation/margins/grid, regions and guides, exact
native template masters, rectangles and text boxes, typography, fills, lines,
z-order, containers, named ports, connector routes/bends/jumps/arrowheads/labels,
reference callouts, visual rationale, and constraint traceability.

The validator requires exactly one shape per specification object and one
connector per relationship. It checks endpoint shapes and ports, semantic arrow
direction, exact relationship labels, page bounds, containment membership,
reference-number callouts, and traceability for every hard constraint and visual
requirement. Invalid initial output receives at most one model repair.

The prompt and approved-example set are independently versioned. Its three
few-shot patterns come only from the checked-in expert flowchart, system, and
contained-component specification fixtures. Fake callers test schema, validation,
repair, and provenance plumbing but are not quality evidence.

After committing the implementation, run the exit gate from a clean checkout to
an external new directory:

```bash
uv run python scripts/run_generation_v2_planner_acceptance.py \
  --output ../acceptance/g3-$(git rev-parse --short HEAD) \
  --model gpt-5.6-sol
```

The runner rejects dirty source and output inside the checkout. It preserves each
specification, logical and transport prompts, raw response, validated plan,
request IDs, timings, hashes, schema version, prompt/example versions, model, and
source revision.
