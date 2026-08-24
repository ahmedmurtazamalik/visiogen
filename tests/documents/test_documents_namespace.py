"""Smoke test for the deterministic document package boundary."""


def test_documents_namespace_is_importable() -> None:
    import visiogen.documents  # noqa: F401
