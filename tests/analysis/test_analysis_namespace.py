"""Smoke test for the analysis workstream package boundary."""


def test_analysis_namespace_is_importable() -> None:
    import visiogen.analysis  # noqa: F401
