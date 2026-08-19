"""Opt-in provider evaluation against reviewed semantic fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
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

ProviderName = Literal["codex", "local", "gemini"]


def _semantic_value(graph: DiagramGraph) -> dict[str, Any]:
    value = graph.model_dump(mode="json", exclude_none=True)
    for edge in value["edges"]:
        edge.pop("id", None)
    return value


def _field_differences(
    expected: Any,
    actual: Any,
    path: str = "",
) -> list[dict[str, Any]]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences: list[dict[str, Any]] = []
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}.{key}" if path else key
            if key not in expected or key not in actual:
                differences.append(
                    {
                        "path": child_path,
                        "expected": expected.get(key, "<missing>"),
                        "actual": actual.get(key, "<missing>"),
                    }
                )
            else:
                differences.extend(
                    _field_differences(expected[key], actual[key], child_path)
                )
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        for index in range(max(len(expected), len(actual))):
            child_path = f"{path}[{index}]"
            if index >= len(expected) or index >= len(actual):
                differences.append(
                    {
                        "path": child_path,
                        "expected": expected[index] if index < len(expected) else "<missing>",
                        "actual": actual[index] if index < len(actual) else "<missing>",
                    }
                )
            else:
                differences.extend(
                    _field_differences(expected[index], actual[index], child_path)
                )
        return differences
    if expected != actual:
        return [{"path": path, "expected": expected, "actual": actual}]
    return []


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def evaluate_fixture_corpus(
    extractor: DiagramExtractor,
    *,
    provider: ProviderName,
    model: str,
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
    results: list[dict[str, Any]] = []

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
        differences = _field_differences(
            _semantic_value(expected),
            _semantic_value(actual),
        )
        result: dict[str, Any] = {
            "case": case,
            "status": "match" if not differences else "mismatch",
            "actual": "graph",
        }
        if differences:
            result["differences"] = differences
        results.append(result)

    mismatch_count = sum(item["status"] != "match" for item in results)
    report: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "case_count": len(results),
        "mismatch_count": mismatch_count,
        "cases": results,
    }
    _write_json_atomic(output_dir / "semantic-mismatch-report.json", report)
    return report
