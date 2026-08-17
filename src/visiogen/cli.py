"""Visiogen command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    return argparse.ArgumentParser(
        prog="visiogen",
        description="Generate editable Visio diagrams from text descriptions.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Visiogen command-line interface."""
    parser = build_parser()
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
