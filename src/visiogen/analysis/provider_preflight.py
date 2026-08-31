"""Decision logic for the authenticated analysis-provider preflight."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from visiogen.analysis.models import AnalysisModel


class ProviderProbe(AnalysisModel):
    """One timed provider or production-case probe."""

    kind: Literal["text", "analysis_case"]
    status: Literal["passed", "failed"]
    elapsed_seconds: float = Field(ge=0)
    case_status: str | None = None
    model_calls: int | None = Field(default=None, ge=0)
    maximum_model_call_seconds: float | None = Field(default=None, ge=0)
    error: str | None = None


class ProviderPreflightDecision(AnalysisModel):
    """Machine-readable readiness decision for starting an A8 release run."""

    status: Literal["ready", "not_ready"]
    reasons: list[str]


def maximum_trace_elapsed_ms(value: object) -> float | None:
    """Return the slowest individual model trace, excluding aggregate stage timing."""

    found: list[float] = []

    def visit(item: object, *, inside_traces: bool = False) -> None:
        if isinstance(item, dict):
            elapsed = item.get("elapsed_ms")
            if inside_traces and isinstance(elapsed, (int, float)):
                found.append(float(elapsed))
            for key, child in item.items():
                visit(child, inside_traces=inside_traces or key == "traces")
        elif isinstance(item, list):
            for child in item:
                visit(child, inside_traces=inside_traces)

    visit(value)
    return max(found, default=None)


def evaluate_provider_preflight(
    probes: list[ProviderProbe],
    *,
    required_case_passes: int,
    maximum_text_seconds: float,
    maximum_model_call_seconds: float,
) -> ProviderPreflightDecision:
    """Require a quick text probe and consecutive healthy production-case probes."""

    reasons: list[str] = []
    text_probes = [probe for probe in probes if probe.kind == "text"]
    case_probes = [probe for probe in probes if probe.kind == "analysis_case"]
    if len(text_probes) != 1:
        reasons.append("Exactly one text probe is required.")
    elif text_probes[0].status != "passed":
        reasons.append("The text probe failed.")
    elif text_probes[0].elapsed_seconds > maximum_text_seconds:
        reasons.append(
            "The text probe exceeded the latency threshold "
            f"({text_probes[0].elapsed_seconds:.1f}s > {maximum_text_seconds:.1f}s)."
        )
    if len(case_probes) != required_case_passes:
        reasons.append(
            f"Expected {required_case_passes} production-case probes; got {len(case_probes)}."
        )
    for index, probe in enumerate(case_probes, start=1):
        if probe.status != "passed" or probe.case_status != "complete":
            reasons.append(f"Production-case probe {index} did not complete successfully.")
        if probe.maximum_model_call_seconds is None:
            reasons.append(f"Production-case probe {index} has no model-call timing.")
        elif probe.maximum_model_call_seconds > maximum_model_call_seconds:
            reasons.append(
                f"Production-case probe {index} exceeded the model-call latency threshold "
                f"({probe.maximum_model_call_seconds:.1f}s > "
                f"{maximum_model_call_seconds:.1f}s)."
            )
    return ProviderPreflightDecision(
        status="not_ready" if reasons else "ready",
        reasons=reasons,
    )
