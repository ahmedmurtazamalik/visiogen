#!/usr/bin/env python3
"""Measure Codex latency and gate expensive A8 release-corpus execution."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from time import monotonic

from pydantic import BaseModel, ConfigDict

from visiogen.analysis.provider_preflight import (
    ProviderProbe,
    evaluate_provider_preflight,
    maximum_trace_elapsed_ms,
)
from visiogen.analysis.release_evaluation import ReleaseCase, validate_release_corpus
from visiogen.analysis.release_execution import verify_analysis_bundle
from visiogen.analysis.production import build_codex_analysis_pipeline
from visiogen.config import Settings
from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.providers.codex_cli import CodexStructuredCaller

_REPOSITORY = Path(__file__).resolve().parents[1]


class _TextProbeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_REPOSITORY, text=True, capture_output=True, check=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", default="held-clean-native-pdf")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--consecutive", type=int, default=2)
    parser.add_argument("--maximum-text-seconds", type=float, default=30)
    parser.add_argument("--maximum-model-call-seconds", type=float, default=240)
    args = parser.parse_args()
    if args.consecutive < 1:
        parser.error("--consecutive must be positive")
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("Preflight output must be outside the source checkout")
    if _git("status", "--porcelain"):
        parser.error("Provider preflight requires a clean immutable source checkout")

    corpus_path = args.corpus.resolve()
    corpus_raw = json.loads(corpus_path.read_text())
    cases = [ReleaseCase.model_validate(item) for item in corpus_raw["cases"]]
    validation = validate_release_corpus(cases, corpus_path.parent)
    if not validation.valid:
        parser.error("Invalid A8 corpus: " + "; ".join(validation.failures))
    matching = [case for case in cases if case.id == args.case]
    if len(matching) != 1:
        parser.error(f"Unknown or duplicate corpus case: {args.case}")
    case = matching[0]
    settings = Settings(
        provider="codex", codex_model=args.model, timeout_seconds=args.timeout
    )
    source_revision = _git("rev-parse", "HEAD")

    def build(stage: Path) -> dict[str, object]:
        probes: list[ProviderProbe] = []
        started = monotonic()
        try:
            caller = CodexStructuredCaller(settings, _TextProbeResponse)
            response = caller(
                "Return a provider health response as strict JSON.",
                'Return {"status":"ok"}.',
            )
            parsed = _TextProbeResponse.model_validate_json(response.content)
            if parsed.status != "ok":
                raise ValueError(f"Unexpected text-probe status: {parsed.status}")
            probes.append(
                ProviderProbe(
                    kind="text", status="passed", elapsed_seconds=monotonic() - started
                )
            )
        except Exception as error:
            probes.append(
                ProviderProbe(
                    kind="text",
                    status="failed",
                    elapsed_seconds=monotonic() - started,
                    error=f"{type(error).__name__}: {error}",
                )
            )

        if (
            probes[0].status == "passed"
            and probes[0].elapsed_seconds <= args.maximum_text_seconds
        ):
            for index in range(1, args.consecutive + 1):
                bundle = stage / f"case-probe-{index:02d}" / "bundle"
                started = monotonic()
                try:
                    pipeline = build_codex_analysis_pipeline(settings)
                    pipeline.analyze(corpus_path.parent / case.source_path, bundle)
                    outcome = verify_analysis_bundle(case, bundle)
                    analysis = json.loads((bundle / "analysis.json").read_text())
                    maximum_ms = maximum_trace_elapsed_ms(analysis)
                    within_latency_limit = (
                        maximum_ms is not None
                        and maximum_ms / 1000 <= args.maximum_model_call_seconds
                    )
                    passed = outcome.status == "complete" and within_latency_limit
                    probes.append(
                        ProviderProbe(
                            kind="analysis_case",
                            status="passed" if passed else "failed",
                            elapsed_seconds=monotonic() - started,
                            case_status=outcome.status,
                            model_calls=outcome.model_calls,
                            maximum_model_call_seconds=(
                                maximum_ms / 1000 if maximum_ms is not None else None
                            ),
                            error=None if passed else "; ".join(outcome.failures),
                        )
                    )
                except Exception as error:
                    probes.append(
                        ProviderProbe(
                            kind="analysis_case",
                            status="failed",
                            elapsed_seconds=monotonic() - started,
                            error=f"{type(error).__name__}: {error}",
                        )
                    )
                if probes[-1].status == "failed":
                    break

        decision = evaluate_provider_preflight(
            probes,
            required_case_passes=args.consecutive,
            maximum_text_seconds=args.maximum_text_seconds,
            maximum_model_call_seconds=args.maximum_model_call_seconds,
        )
        report: dict[str, object] = {
            "status": decision.status,
            "reasons": decision.reasons,
            "source_revision": source_revision,
            "source_clean": True,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider": "codex-cli",
            "model": args.model,
            "case_id": case.id,
            "required_consecutive_case_passes": args.consecutive,
            "thresholds": {
                "maximum_text_seconds": args.maximum_text_seconds,
                "maximum_model_call_seconds": args.maximum_model_call_seconds,
            },
            "probes": [probe.model_dump(mode="json") for probe in probes],
        }
        (stage / "preflight-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    print(f"A8 provider preflight: {str(report['status']).upper()}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    print(f"Evidence: {output}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
