#!/usr/bin/env python3
"""Run the reviewed A3 corpus through production observation and reconstruction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image

from visiogen.analysis.evaluation import aggregate_semantic_scores, score_semantic_case
from visiogen.analysis.models import CandidatePreparation
from visiogen.analysis.observation import StructuredObservationWorkflow
from visiogen.analysis.preparation import prepare_diagram_candidates
from visiogen.analysis.reconstruction import (
    ReconstructionWorkflowError,
    StructuredReconstructionWorkflow,
)
from visiogen.analysis.semantic_pipeline import SemanticAnalysisWorkflow
from visiogen.analysis.semantics import AnalyzedDiagram, RawObservationBatch
from visiogen.analysis.selection import CandidateSelection, discover_diagram_candidates
from visiogen.config import Settings
from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.documents.models import CoverageReport, DocumentSnapshot, SourceLocation, VisualAsset
from visiogen.providers.codex_cli import CodexStructuredCaller

_REPOSITORY = Path(__file__).resolve().parents[1]
_CORPUS = _REPOSITORY / "tests/fixtures/analysis/semantic_corpus.json"
_BUILDERS = _REPOSITORY / "tests/analysis"
_THRESHOLDS = {
    "object_precision": 0.90,
    "object_recall": 0.90,
    "reference_recall": 1.00,
    "edge_precision": 0.85,
    "edge_recall": 0.85,
    "direction_accuracy": 0.90,
    "family_accuracy": 0.80,
}


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=_REPOSITORY,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _snapshot(image_path: Path, corpus_sha: str) -> DocumentSnapshot:
    data = image_path.read_bytes()
    image_sha = hashlib.sha256(data).hexdigest()
    with Image.open(image_path) as image:
        width, height = image.size
    asset = VisualAsset(
        id="asset-0001",
        media_type="image/png",
        origin="embedded",
        sha256=image_sha,
        byte_size=len(data),
        artifact_path=f"assets/{image_path.name}",
        width_px=width,
        height_px=height,
        location=SourceLocation(),
    )
    return DocumentSnapshot(
        source_id=f"semantic-corpus:{corpus_sha}:{image_path.stem}:{image_sha}",
        source_sha256=image_sha,
        source_name=image_path.name,
        document_kind="docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        byte_size=len(data),
        visual_assets=[asset],
        coverage=CoverageReport(
            native_text="not_available",
            embedded_media="complete",
            rendered_pages="not_available",
        ),
    )


def _passed(metrics, failures: list[dict[str, object]], complete: bool) -> bool:
    return (
        complete
        and not failures
        and all(getattr(metrics, name) >= threshold for name, threshold in _THRESHOLDS.items())
        and metrics.ambiguous_direction_safe == metrics.ambiguous_direction_total
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("Acceptance output must be outside the source checkout")
    if _git("status", "--porcelain"):
        parser.error("Acceptance requires a clean immutable source checkout")
    source_revision = _git("rev-parse", "HEAD")
    provider_version = subprocess.run(
        ["codex", "--version"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    corpus_bytes = _CORPUS.read_bytes()
    corpus_sha = hashlib.sha256(corpus_bytes).hexdigest()
    corpus = json.loads(corpus_bytes)
    all_cases = corpus["cases"]
    requested = set(args.case_ids or [])
    cases = [case for case in all_cases if not requested or case["id"] in requested]
    if requested - {case["id"] for case in cases}:
        parser.error("One or more requested corpus cases do not exist")
    complete = len(cases) == len(all_cases)
    sys.path.insert(0, str(_BUILDERS))
    from semantic_fixture_builders import write_semantic_fixture

    settings = Settings(
        provider="codex",
        codex_model=args.model,
        timeout_seconds=args.timeout,
    )

    def build(stage: Path) -> dict[str, object]:
        scores = []
        failures: list[dict[str, object]] = []
        case_records: list[dict[str, object]] = []
        for case in cases:
            case_dir = stage / case["id"]
            ingestion = case_dir / "ingestion"
            assets_dir = ingestion / "assets"
            assets_dir.mkdir(parents=True)
            image_path = write_semantic_fixture(
                assets_dir / f"{case['id']}.png",
                case["generation_kind"],
            )
            snapshot = _snapshot(image_path, corpus_sha)
            discovery = discover_diagram_candidates(
                snapshot,
                selection=CandidateSelection(candidate_id="candidate-0001"),
            )
            preparation: CandidatePreparation = prepare_diagram_candidates(
                snapshot,
                discovery,
                ingestion,
                case_dir / "prepared",
            )
            prepared = preparation.prepared_candidates[0]
            observation_caller = CodexStructuredCaller(settings, RawObservationBatch)
            reconstruction_caller = CodexStructuredCaller(settings, AnalyzedDiagram)
            workflow = SemanticAnalysisWorkflow(
                StructuredObservationWorkflow(observation_caller),
                StructuredReconstructionWorkflow(reconstruction_caller),
            )
            try:
                result = workflow.analyze(prepared, case_dir / "prepared")
                score = score_semantic_case(case, result.reconstruction.diagram)
                scores.append(score)
                record = {
                    "id": case["id"],
                    "status": "completed",
                    "score": score.model_dump(mode="json"),
                    "result": result.model_dump(mode="json"),
                }
            except Exception as error:
                failure: dict[str, object] = {
                    "id": case["id"],
                    "error": f"{type(error).__name__}: {error}",
                }
                if isinstance(error, ReconstructionWorkflowError):
                    failure["attempts"] = len(error.traces)
                    failure["validation_error"] = error.validation_error
                    failure["traces"] = [
                        trace.model_dump(mode="json") for trace in error.traces
                    ]
                failures.append(failure)
                record = {"id": case["id"], "status": "failed", "failure": failure}
            (case_dir / "semantic-result.json").write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n"
            )
            case_records.append(record)
        metrics = aggregate_semantic_scores(scores)
        passed = _passed(metrics, failures, complete)
        report: dict[str, object] = {
            "status": "passed" if passed else ("exploratory" if not complete else "failed"),
            "source_revision": source_revision,
            "source_clean": True,
            "provider": "codex-cli",
            "provider_version": provider_version,
            "model": args.model,
            "corpus_version": corpus["version"],
            "corpus_sha256": corpus_sha,
            "complete_corpus": complete,
            "thresholds": _THRESHOLDS,
            "metrics": metrics.model_dump(mode="json"),
            "failures": failures,
            "cases": case_records,
        }
        (stage / "acceptance-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    print(f"A3 semantic acceptance: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] in {"passed", "exploratory"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
