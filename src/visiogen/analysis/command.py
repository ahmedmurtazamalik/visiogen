"""CLI registration boundary for the document-analysis workstream."""

from __future__ import annotations

import argparse


def register_analysis_command(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register analysis commands when their first vertical slice is available.

    This analysis-owned hook allows `visiogen analyze` to be added without
    editing the stable top-level dispatcher.
    """

    del commands
