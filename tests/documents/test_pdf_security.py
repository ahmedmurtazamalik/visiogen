"""Provider-independent PDF security preflight."""

import pytest

from visiogen.documents.pdf import _contains_javascript_action


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"<< /S /JavaScript /JS (app.alert(1)) >>", True),
        (b"<< /S /Java#53cript /JS (app.alert(1)) >>", True),
        (b"<< /S /Java#53#63ript /JS (app.alert(1)) >>", True),
        (b"BT (The word JavaScript is ordinary text.) Tj ET", False),
        (b"<< /Type /Page /Resources << /Font << /JS 4 0 R >> >> >>", False),
    ],
)
def test_javascript_action_detection_decodes_pdf_name_escapes(
    content: bytes,
    expected: bool,
) -> None:
    assert _contains_javascript_action(content) is expected
