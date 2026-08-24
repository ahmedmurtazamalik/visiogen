# Parallel Workstream Boundaries

Visiogen has two independent product workstreams:

```text
Generation                         Analysis
text -> structured design          PDF/DOCX -> document snapshot
     -> native VSDX                     -> diagram understanding
     -> Visio critique                  -> textual description
                                        -> consistency findings
```

The repository is organized so one contributor can continue the generation
pipeline while another builds document analysis. The paths below are ownership
boundaries for coordination, not access restrictions.

## Generation-owned paths

The generation contributor owns the existing mature modules at the root of the
package. They intentionally remain in place so ongoing generation work does not
have to absorb a large import migration:

```text
src/visiogen/critic.py
src/visiogen/design.py
src/visiogen/designer.py
src/visiogen/extractor.py
src/visiogen/layout.py
src/visiogen/layouts/
src/visiogen/models.py
src/visiogen/normalization.py
src/visiogen/pipeline.py
src/visiogen/preview.py
src/visiogen/provider_evaluation.py
src/visiogen/provider_factory.py
src/visiogen/renderer.py
src/visiogen/shape_mapper.py
src/visiogen/validation.py
src/visiogen/generation/
templates/
scripts/*visio*
tests/test_critic.py
tests/test_design.py
tests/test_designer.py
tests/test_extractors.py
tests/test_layout.py
tests/layouts/
tests/test_pipeline.py
tests/test_preview.py
tests/test_renderer.py
tests/test_renderer_fixtures.py
tests/test_shape_mapper.py
tests/test_validation.py
```

New generation integration code should go under `src/visiogen/generation/` when
it does not belong to an established public module.

## Analysis-owned paths

The analysis contributor owns:

```text
src/visiogen/analysis/
src/visiogen/documents/
tests/analysis/
tests/documents/
tests/fixtures/analysis/
tests/fixtures/documents/
docs/plans/active/DOCUMENT_ANALYSIS.md
docs/analysis/
scripts/*analysis*
```

`documents` is deterministic input infrastructure. It must not import model
providers or generation modules. `analysis` may use shared provider transports
through narrow protocols but must not import the VSDX pipeline, renderer, layout,
template, preview exporter, or native Visio automation.

## Deliberately shared paths

These files are integration surfaces and should be changed in small dedicated
commits after coordinating with the other contributor:

```text
src/visiogen/cli.py
src/visiogen/config.py
src/visiogen/providers/
src/visiogen/__init__.py
pyproject.toml
README.md
docs/architecture/SYSTEM_OVERVIEW.md
.github/workflows/
tests/conftest.py
```

The root CLI is now a stable dispatcher. Generation command implementation lives
in `generation/command.py`; analysis command registration belongs in
`analysis/command.py`. Adding or changing arguments in either workstream should
not require editing `cli.py`.

Provider subprocess mechanics may be shared, but provider output schemas and
workflows belong to the consuming workstream. Avoid putting analysis models in
`providers/base.py` merely because a provider returns them.

## Import direction

Allowed dependency direction:

```text
analysis -> documents
analysis -> narrow shared provider/config infrastructure
generation -> existing generation modules
cli -> generation.command + analysis.command
```

Forbidden dependency direction:

```text
documents -> analysis
documents -> providers
documents -> generation/VSDX modules
analysis -> generation/VSDX modules
generation -> analysis or documents
```

If both workstreams discover a genuinely identical primitive, do not immediately
move it into a shared module. Let each implementation stabilize first, then extract
the smallest proven common contract in a separate integration commit. Premature
sharing creates more merge conflicts than small temporary duplication.

## Git workflow for two contributors

Use one branch and one worktree per workstream:

```bash
git worktree add ../Visiogen-generation -b work/generation main
git worktree add ../Visiogen-analysis -b work/analysis main
```

Recommended commit behavior:

1. Keep commits scoped to one workstream.
2. Do not mix formatting or renames with feature work.
3. Rebase or merge `main` frequently before changing a shared path.
4. Put shared-path changes in their own commit so they can be reviewed or
   cherry-picked independently.
5. Run the complete suite before merging, not only the workstream-local tests.
6. Do not rewrite reviewed fixtures from provider output.

The repository does not assign GitHub usernames in `CODEOWNERS` because ownership
identities are not yet known. Add actual identities later rather than committing
placeholder owners that give a false review guarantee.

## Test commands

Generation contributor:

```bash
uv run pytest -q tests --ignore=tests/analysis --ignore=tests/documents
```

Analysis contributor:

```bash
uv run pytest -q tests/analysis tests/documents
```

Integration gate for both:

```bash
uv run pytest -q
uv build
uv run visiogen --help
```

Real model and desktop-application acceptance remain separate from unit tests and
must retain their own provenance artifacts.
