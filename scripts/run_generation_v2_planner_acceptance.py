#!/usr/bin/env python3
"""Run the three core G3 specifications through the real Codex planner."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from visiogen.config import Settings
from visiogen.generation.construction import VisioConstructionPlan
from visiogen.generation.planner import (
    APPROVED_EXAMPLES_VERSION,
    CONSTRUCTION_PROMPT_VERSION,
    ConstructionPlanningError,
    StructuredConstructionPlanner,
    build_construction_prompt,
)
from visiogen.generation.specification import load_specification
from visiogen.providers.codex_cli import CodexStructuredCaller

REPOSITORY = Path(__file__).resolve().parents[1]
CASES = {
    "flowchart": REPOSITORY / "tests/fixtures/generation_v2/specifications/expert-flow.json",
    "system_block": REPOSITORY / "tests/fixtures/generation_v2/specifications/expert-system.yaml",
    "component_schematic": REPOSITORY / "tests/fixtures/generation_v2/specifications/expert-component.json",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output must not already exist")
    if output == REPOSITORY or REPOSITORY in output.parents:
        parser.error("Acceptance output must be outside the source checkout")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPOSITORY, text=True,
        capture_output=True, check=True,
    ).stdout
    if status.strip():
        parser.error("G3 real-model acceptance requires a clean source checkout")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True,
        capture_output=True, check=True,
    ).stdout.strip()

    stage = Path(tempfile.mkdtemp(prefix="visiogen-g3-", dir=output.parent))
    try:
        settings = Settings(provider="codex", codex_model=args.model)
        planner = StructuredConstructionPlanner(
            CodexStructuredCaller(settings, VisioConstructionPlan)
        )
        outcomes = []
        for family, source in CASES.items():
            case_dir = stage / family
            case_dir.mkdir()
            specification = load_specification(source)
            _write_json(case_dir / "specification.json", specification.model_dump(mode="json"))
            (case_dir / "system-prompt.txt").write_text(build_construction_prompt())
            try:
                result = planner.plan(specification)
            except ConstructionPlanningError as error:
                for index, value in enumerate(error.user_prompts, 1):
                    (case_dir / f"user-prompt-{index}.txt").write_text(value)
                for index, response in enumerate(error.responses, 1):
                    (case_dir / f"raw-response-{index}.json").write_text(response.content)
                    if response.transport_prompt is not None:
                        (case_dir / f"transport-prompt-{index}.txt").write_text(
                            response.transport_prompt
                        )
                outcomes.append({
                    "family": family, "status": "failed",
                    "error_type": type(error).__name__, "error": str(error),
                })
                continue
            for index, value in enumerate(result.user_prompts, 1):
                (case_dir / f"user-prompt-{index}.txt").write_text(value)
            for index, value in enumerate(result.raw_responses, 1):
                (case_dir / f"raw-response-{index}.json").write_text(value)
            for index, value in enumerate(result.transport_prompts, 1):
                if value is not None:
                    (case_dir / f"transport-prompt-{index}.txt").write_text(value)
            _write_json(case_dir / "validated-plan.json", result.plan.model_dump(mode="json"))
            outcomes.append({
                "family": family,
                "status": "passed",
                "attempts": result.attempts,
                "request_ids": list(result.request_ids),
                "elapsed_ms": result.elapsed_ms,
                "specification_sha256": _sha(case_dir / "specification.json"),
                "plan_sha256": _sha(case_dir / "validated-plan.json"),
            })
        schema = json.dumps(VisioConstructionPlan.model_json_schema(), sort_keys=True).encode()
        passed = all(item["status"] == "passed" for item in outcomes)
        report = {
            "status": "passed" if passed else "failed",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "source_revision": revision,
            "source_worktree_clean": True,
            "provider": "codex",
            "model": args.model,
            "prompt_version": CONSTRUCTION_PROMPT_VERSION,
            "approved_examples_version": APPROVED_EXAMPLES_VERSION,
            "construction_plan_schema_sha256": hashlib.sha256(schema).hexdigest(),
            "cases": outcomes,
        }
        _write_json(stage / "acceptance-report.json", report)
        stage.replace(output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print(f"G3 planner acceptance: {'passed' if passed else 'failed'} ({len(CASES)} core families)")
    print(f"Evidence: {output}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
