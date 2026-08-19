"""Opt-in provider evaluation against reviewed semantic fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from visiogen.models import DiagramGraph
from visiogen.providers.base import (
    DiagramExtractor,
    ExtractionValidationError,
    NoDiagramContentError,
    ProviderError,
)

ProviderName = Literal["local", "gemini"]


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def evaluate_fixture_corpus(
    extractor: DiagramExtractor,
    *,
    provider: ProviderName,
    fixtures_root: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    """Evaluate one live provider without modifying reviewed expectations."""

    text_dir = fixtures_root / "text"
    expected_dir = fixtures_root / "graphs" / "expected"
    resolved_expected = expected_dir.resolve()
    resolved_artifacts = artifact_root.resolve()
    if (
        resolved_artifacts == resolved_expected
        or resolved_expected in resolved_artifacts.parents
    ):
        raise ValueError("Artifact output cannot be inside reviewed expected fixtures")
    output_dir = artifact_root / provider
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []

    for prompt_path in sorted(text_dir.glob("*.txt")):
        case = prompt_path.stem
        error_path = expected_dir / f"{case}.error.json"
        try:
            actual = extractor.extract(prompt_path.read_text())
        except NoDiagramContentError:
            status = "match" if error_path.is_file() else "mismatch"
            results.append({"case": case, "status": status, "actual": "no_diagram"})
            continue
        except (ProviderError, ExtractionValidationError) as error:
            results.append(
                {
                    "case": case,
                    "status": "error",
                    "actual": type(error).__name__,
                }
            )
            continue

        actual_value = actual.model_dump(mode="json", exclude_none=True)
        _write_json_atomic(output_dir / f"{case}.actual.json", actual_value)
        if error_path.is_file():
            results.append({"case": case, "status": "mismatch", "actual": "graph"})
            continue

        expected = DiagramGraph.model_validate_json(
            (expected_dir / f"{case}.json").read_text()
        )
        results.append(
            {
                "case": case,
                "status": "match" if actual == expected else "mismatch",
                "actual": "graph",
            }
        )

    mismatch_count = sum(item["status"] != "match" for item in results)
    report: dict[str, Any] = {
        "provider": provider,
        "case_count": len(results),
        "mismatch_count": mismatch_count,
        "cases": results,
    }
    _write_json_atomic(output_dir / "semantic-mismatch-report.json", report)
    return report
