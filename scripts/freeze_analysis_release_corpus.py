#!/usr/bin/env python3
"""Freeze an A8 corpus draft by hashing and validating exact PDF/DOCX sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from visiogen.analysis.release_evaluation import ReleaseCase, validate_release_corpus


def freeze_corpus(draft_path: Path) -> dict[str, object]:
    """Resolve draft paths safely, add hashes, and return a validated frozen corpus."""

    raw = json.loads(draft_path.read_text())
    allowed_top = {"version", "thresholds", "cases"}
    extra_top = set(raw) - allowed_top
    if extra_top:
        raise ValueError("Unknown draft corpus fields: " + ", ".join(sorted(extra_top)))
    root = draft_path.resolve().parent
    frozen_cases: list[ReleaseCase] = []
    for raw_case in raw["cases"]:
        if "source_sha256" in raw_case:
            raise ValueError("Draft cases must not contain source_sha256")
        source_path = raw_case.get("source_path")
        if not isinstance(source_path, str):
            raise ValueError("Every draft case requires source_path")
        pure = PurePosixPath(source_path)
        if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != source_path:
            raise ValueError("Draft source paths must be normalized relative POSIX paths")
        path = root.joinpath(*pure.parts)
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError as error:
            raise ValueError(f"Missing draft corpus source: {source_path}") from error
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"Draft corpus source escapes root: {source_path}")
        if path.is_symlink() or not resolved.is_file():
            raise ValueError(f"Draft corpus source must be a regular non-symlink file: {source_path}")
        payload = {**raw_case, "source_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()}
        frozen_cases.append(ReleaseCase.model_validate(payload))
    validation = validate_release_corpus(frozen_cases, root)
    if not validation.valid:
        raise ValueError("Invalid frozen corpus: " + "; ".join(validation.failures))
    return {
        "version": raw.get("version", 1),
        "thresholds": raw.get("thresholds", {}),
        "cases": [case.model_dump(mode="json") for case in frozen_cases],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Frozen corpus output already exists")
    frozen = freeze_corpus(args.draft.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    print(f"Frozen A8 corpus: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
