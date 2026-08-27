#!/usr/bin/env python3
"""Create blinded A8 review forms from a completed corpus execution report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from visiogen.analysis.release_evaluation import ReleaseCase
from visiogen.analysis.review_packet import build_review_packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Review output already exists; refusing to overwrite human work")
    corpus = json.loads(args.corpus.read_text())
    execution = json.loads(args.execution.read_text())
    cases = [ReleaseCase.model_validate(item) for item in corpus["cases"]]
    packet = build_review_packet(cases, execution)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    print(f"A8 held-out review packet: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
