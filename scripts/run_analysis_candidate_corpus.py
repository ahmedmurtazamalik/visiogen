#!/usr/bin/env python3
"""Run the immutable A2 candidate corpus through the production Codex adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image

from visiogen.analysis.classification import (
    StructuredCandidateClassifier,
    VisualCandidateBatch,
)
from visiogen.analysis.selection import discover_diagram_candidates
from visiogen.config import Settings
from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    SourceLocation,
    VisualAsset,
)
from visiogen.providers.codex_cli import CodexStructuredCaller

_REPOSITORY = Path(__file__).resolve().parents[1]
_CORPUS = _REPOSITORY / "tests/fixtures/analysis/candidate_corpus.json"
_TEST_BUILDERS = _REPOSITORY / "tests/analysis"
_DIAGRAM_PRECISION = 0.90
_DIAGRAM_RECALL = 0.90
_NON_DIAGRAM_PRECISION = 0.90
_NON_DIAGRAM_RECALL = 0.90


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=_REPOSITORY,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _label_metrics(expected: list[str], predicted: list[str], label: str) -> dict[str, float | int]:
    true_positive = sum(
        expected_label == label and predicted_label == label
        for expected_label, predicted_label in zip(expected, predicted, strict=True)
    )
    false_positive = sum(
        expected_label != label and predicted_label == label
        for expected_label, predicted_label in zip(expected, predicted, strict=True)
    )
    false_negative = sum(
        expected_label == label and predicted_label != label
        for expected_label, predicted_label in zip(expected, predicted, strict=True)
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": _ratio(true_positive, true_positive + false_positive),
        "recall": _ratio(true_positive, true_positive + false_negative),
    }


def _snapshot_for_images(cases: list[dict[str, str]], images_dir: Path) -> DocumentSnapshot:
    assets: list[VisualAsset] = []
    for index, case in enumerate(cases, start=1):
        path = images_dir / f"{case['id']}.png"
        data = path.read_bytes()
        with Image.open(path) as image:
            width, height = image.size
        assets.append(
            VisualAsset(
                id=f"asset-{index:04d}",
                media_type="image/png",
                origin="embedded",
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
                artifact_path=f"inputs/{path.name}",
                width_px=width,
                height_px=height,
                location=SourceLocation(),
            )
        )
    corpus_sha = hashlib.sha256(_CORPUS.read_bytes()).hexdigest()
    return DocumentSnapshot(
        source_id=f"candidate-corpus:{corpus_sha}",
        source_sha256=corpus_sha,
        source_name=_CORPUS.name,
        document_kind="docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        byte_size=_CORPUS.stat().st_size,
        visual_assets=assets,
        coverage=CoverageReport(
            native_text="not_available",
            embedded_media="complete",
            rendered_pages="not_available",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("Acceptance output must be outside the source checkout")
    if _git("status", "--porcelain"):
        parser.error("Acceptance requires a clean immutable source checkout")
    source_revision = _git("rev-parse", "HEAD")
    corpus = json.loads(_CORPUS.read_text())
    cases = corpus["cases"]
    sys.path.insert(0, str(_TEST_BUILDERS))
    from candidate_fixture_builders import write_candidate_fixture

    settings = Settings(
        provider="codex",
        codex_model=args.model,
        timeout_seconds=args.timeout,
    )

    def build(stage: Path) -> dict[str, object]:
        images_dir = stage / "inputs"
        images_dir.mkdir()
        for case in cases:
            write_candidate_fixture(
                images_dir / f"{case['id']}.png",
                case["generation_kind"],
            )
        snapshot = _snapshot_for_images(cases, images_dir)
        provisional = discover_diagram_candidates(snapshot)
        image_by_id = {
            candidate.id: images_dir / f"{case['id']}.png"
            for candidate, case in zip(provisional.candidates, cases, strict=True)
        }
        caller = CodexStructuredCaller(settings, VisualCandidateBatch)
        classifier = StructuredCandidateClassifier(
            caller,
            image_by_id,
            classifier_identity=f"codex-cli:{args.model}",
        )
        discovery = discover_diagram_candidates(snapshot, classifier=classifier)
        trace = classifier.last_trace
        if trace is None:
            raise RuntimeError("Classifier did not retain its successful call trace")
        expected = [case["expected_label"] for case in cases]
        predicted = [candidate.decision.label for candidate in discovery.candidates]
        diagram = _label_metrics(expected, predicted, "diagram")
        non_diagram = _label_metrics(expected, predicted, "non_diagram")
        unknown_correct = sum(
            expected_label == "unknown" and predicted_label == "unknown"
            for expected_label, predicted_label in zip(expected, predicted, strict=True)
        )
        unknown_total = expected.count("unknown")
        passed = (
            diagram["precision"] >= _DIAGRAM_PRECISION
            and diagram["recall"] >= _DIAGRAM_RECALL
            and non_diagram["precision"] >= _NON_DIAGRAM_PRECISION
            and non_diagram["recall"] >= _NON_DIAGRAM_RECALL
            and unknown_correct == unknown_total
        )
        report: dict[str, object] = {
            "status": "passed" if passed else "failed",
            "source_revision": source_revision,
            "source_clean": True,
            "provider": "codex-cli",
            "model": args.model,
            "corpus_version": corpus["version"],
            "corpus_sha256": snapshot.source_sha256,
            "thresholds": {
                "diagram_precision": _DIAGRAM_PRECISION,
                "diagram_recall": _DIAGRAM_RECALL,
                "non_diagram_precision": _NON_DIAGRAM_PRECISION,
                "non_diagram_recall": _NON_DIAGRAM_RECALL,
                "unknown_controls_must_match": True,
            },
            "metrics": {
                "diagram": diagram,
                "non_diagram": non_diagram,
                "unknown_correct": unknown_correct,
                "unknown_total": unknown_total,
            },
            "cases": [
                {
                    "id": case["id"],
                    "candidate_id": candidate.id,
                    "expected": case["expected_label"],
                    "predicted": candidate.decision.label,
                    "confidence": candidate.decision.confidence,
                    "reason": candidate.decision.reason,
                    "image_sha256": trace.image_sha256[candidate.id],
                }
                for case, candidate in zip(cases, discovery.candidates, strict=True)
            ],
            "classification_trace": trace.model_dump(mode="json"),
            "discovery": discovery.model_dump(mode="json"),
        }
        (stage / "acceptance-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    print(f"A2 candidate acceptance: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
