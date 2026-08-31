"""Provider-preflight readiness decisions."""

from visiogen.analysis.provider_preflight import (
    ProviderProbe,
    evaluate_provider_preflight,
    maximum_trace_elapsed_ms,
)


def test_maximum_trace_elapsed_excludes_aggregate_candidate_timing() -> None:
    analysis = {
        "candidates": [
            {
                "elapsed_ms": 1_000_000,
                "semantic": {
                    "observation": {
                        "traces": [
                            {"elapsed_ms": 300_100},
                            {"elapsed_ms": 85_000},
                        ]
                    }
                },
            }
        ]
    }

    assert maximum_trace_elapsed_ms(analysis) == 300_100


def test_preflight_is_ready_after_quick_text_and_two_complete_cases() -> None:
    decision = evaluate_provider_preflight(
        [
            ProviderProbe(kind="text", status="passed", elapsed_seconds=12),
            ProviderProbe(
                kind="analysis_case", status="passed", elapsed_seconds=300,
                case_status="complete", model_calls=5, maximum_model_call_seconds=75,
            ),
            ProviderProbe(
                kind="analysis_case", status="passed", elapsed_seconds=280,
                case_status="complete", model_calls=4, maximum_model_call_seconds=68,
            ),
        ],
        required_case_passes=2,
        maximum_text_seconds=30,
        maximum_model_call_seconds=240,
    )

    assert decision.status == "ready"
    assert decision.reasons == []


def test_preflight_rejects_slow_or_incomplete_probes() -> None:
    decision = evaluate_provider_preflight(
        [
            ProviderProbe(kind="text", status="passed", elapsed_seconds=31),
            ProviderProbe(
                kind="analysis_case", status="failed", elapsed_seconds=600,
                case_status="partial", model_calls=3, maximum_model_call_seconds=300,
            ),
        ],
        required_case_passes=2,
        maximum_text_seconds=30,
        maximum_model_call_seconds=240,
    )

    assert decision.status == "not_ready"
    assert any("text probe exceeded" in reason for reason in decision.reasons)
    assert any("Expected 2" in reason for reason in decision.reasons)
    assert any("did not complete" in reason for reason in decision.reasons)
    assert any("model-call latency" in reason for reason in decision.reasons)
