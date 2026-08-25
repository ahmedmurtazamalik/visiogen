#!/usr/bin/env python3
"""Run deterministic A4 descriptions over the exact accepted A3 semantic corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from visiogen.analysis.description import (
    compose_diagram_description,
    render_description_markdown,
    write_description_bundle,
)
from visiogen.analysis.description_evaluation import score_description_coverage
from visiogen.analysis.semantics import AnalyzedDiagram
from visiogen.documents.artifacts import publish_artifact_directory

_REPOSITORY = Path(__file__).resolve().parents[1]
_A3_REPORT = _REPOSITORY / "docs/acceptance/evidence/a3-semantic-reconstruction.json"
_METRICS = (
    "object_coverage",
    "relationship_coverage",
    "group_coverage",
    "annotation_coverage",
    "legend_coverage",
    "limitation_coverage",
    "visible_label_coverage",
    "reference_number_coverage",
    "ambiguity_coverage",
)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=_REPOSITORY,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("Acceptance output must be outside the source checkout")
    if _git("status", "--porcelain"):
        parser.error("Acceptance requires a clean immutable source checkout")
    source_revision = _git("rev-parse", "HEAD")
    report_bytes = _A3_REPORT.read_bytes()
    a3_report_sha = _sha256(report_bytes)
    a3_report = json.loads(report_bytes)
    if a3_report["status"] != "passed" or not a3_report["complete_corpus"]:
        parser.error("A4 acceptance requires the complete accepted A3 corpus")

    def build(stage: Path) -> dict[str, object]:
        case_records = []
        aggregate = {name: [] for name in _METRICS}
        stable_outputs = True
        for case in a3_report["cases"]:
            diagram = AnalyzedDiagram.model_validate(
                case["result"]["reconstruction"]["diagram"]
            )
            description = compose_diagram_description(diagram)
            repeated = compose_diagram_description(diagram)
            stable = description == repeated and render_description_markdown(
                description
            ) == render_description_markdown(repeated)
            stable_outputs = stable_outputs and stable
            score = score_description_coverage(description, diagram)
            for name in _METRICS:
                aggregate[name].append(getattr(score, name))
            manifest = write_description_bundle(diagram, stage / case["id"])
            case_records.append(
                {
                    "id": case["id"],
                    "candidate_id": diagram.candidate_id,
                    "stable": stable,
                    "score": score.model_dump(mode="json"),
                    "artifacts": manifest.model_dump(mode="json"),
                }
            )
        metrics = {
            name: min(values, default=1.0) for name, values in aggregate.items()
        }
        passed = (
            len(case_records) == len(a3_report["cases"])
            and stable_outputs
            and all(value == 1 for value in metrics.values())
        )
        report: dict[str, object] = {
            "status": "passed" if passed else "failed",
            "source_revision": source_revision,
            "source_clean": True,
            "generator": "deterministic-a4-description-v1",
            "a3_source_revision": a3_report["source_revision"],
            "a3_report_sha256": a3_report_sha,
            "case_count": len(case_records),
            "stable_outputs": stable_outputs,
            "thresholds": {name: 1.0 for name in _METRICS},
            "metrics": metrics,
            "cases": case_records,
        }
        (stage / "acceptance-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    if not isinstance(report, dict):
        raise TypeError("A4 artifact publisher returned an unexpected result")
    print(f"A4 description acceptance: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
