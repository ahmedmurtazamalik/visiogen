"""Architecture checks that keep the two product workstreams independent."""

from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path(__file__).parents[1] / "src" / "visiogen"
ANALYSIS_ROOTS = (PACKAGE / "analysis", PACKAGE / "documents")
GENERATION_MODULES = {
    "critic",
    "design",
    "designer",
    "extractor",
    "generation",
    "layout",
    "layouts",
    "models",
    "normalization",
    "pipeline",
    "preview",
    "provider_evaluation",
    "provider_factory",
    "renderer",
    "shape_mapper",
    "validation",
}
GENERATION_PATHS = tuple(
    PACKAGE / f"{module}.py"
    for module in GENERATION_MODULES
    if (PACKAGE / f"{module}.py").is_file()
) + tuple(sorted((PACKAGE / "generation").rglob("*.py")))


def _visiogen_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return {name for name in imports if name == "visiogen" or name.startswith("visiogen.")}


def _workstream_files() -> list[Path]:
    return sorted(path for root in ANALYSIS_ROOTS for path in root.rglob("*.py"))


def test_analysis_workstream_does_not_import_generation_modules() -> None:
    violations: list[str] = []
    for path in _workstream_files():
        for imported in _visiogen_imports(path):
            parts = imported.split(".")
            if len(parts) > 1 and parts[1] in GENERATION_MODULES:
                violations.append(f"{path.relative_to(PACKAGE)} imports {imported}")

    assert violations == []


def test_documents_package_remains_provider_independent() -> None:
    violations: list[str] = []
    for path in sorted((PACKAGE / "documents").rglob("*.py")):
        for imported in _visiogen_imports(path):
            if imported == "visiogen.providers" or imported.startswith("visiogen.providers."):
                violations.append(f"{path.relative_to(PACKAGE)} imports {imported}")

    assert violations == []


def test_generation_workstream_does_not_import_analysis_modules() -> None:
    violations: list[str] = []
    for path in GENERATION_PATHS:
        for imported in _visiogen_imports(path):
            if imported in {"visiogen.analysis", "visiogen.documents"} or imported.startswith(
                ("visiogen.analysis.", "visiogen.documents.")
            ):
                violations.append(f"{path.relative_to(PACKAGE)} imports {imported}")

    assert violations == []
