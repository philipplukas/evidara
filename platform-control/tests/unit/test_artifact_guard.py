"""The capture guard must reject bytes that are not the document they claim to be.

These pin the two live defects that motivated it — #631's application shell served
as a statute, and #716's 142-byte JavaScript redirect stub served as a PDF. Both
returned HTTP 200, so only an assertion on the payload itself holds the line.
"""

from __future__ import annotations

from acquisition_core.artifact_guard import (
    check_capture,
    has_format_magic,
    looks_like_html,
)

# A minimal but structurally honest PDF: correct signature, plausible size.
_PDF = b"%PDF-1.7\n" + b"1 0 obj\n<< /Type /Catalog >>\nendobj\n" * 40 + b"%%EOF\n"

# #716, reproduced: the OpenAttachment endpoint returned 200 with this shape where
# a PDF was expected. 142 bytes of HTML that a status-code check calls success.
_REDIRECT_STUB = (
    b"<html><head><script>window.location.href="
    b"'/OpenAttachment?id=1&v=2';</script></head>"
    b"<body>Redirecting...</body></html>"
)


def test_html_stub_is_detected():
    assert looks_like_html(_REDIRECT_STUB)


def test_pdf_is_not_html():
    assert not looks_like_html(_PDF)


def test_leading_whitespace_does_not_hide_html():
    assert looks_like_html(b"\n\n   <!DOCTYPE html><html></html>")


def test_pdf_magic_is_recognised():
    assert has_format_magic(_PDF, "application/pdf")


def test_missing_pdf_magic_is_rejected():
    assert not has_format_magic(b"not a pdf at all", "application/pdf")


def test_format_without_a_signature_is_not_contradicted():
    """Text formats have no magic number, so the guard must not invent one."""
    assert has_format_magic(b"<html>anything</html>", "text/html")


# A UTF-8 BOM is real: servers and CMSes prepend one when they concatenate a
# response, and `bytes.lstrip()` does not strip it. Before this was handled, a
# BOM-prefixed statute PDF was refused as `format_signature_missing` — a refusal
# that names a stub the capture does not contain.
_BOM = b"\xef\xbb\xbf"


def test_leading_bom_does_not_hide_pdf_magic():
    assert has_format_magic(_BOM + _PDF, "application/pdf")


def test_bom_and_whitespace_together_do_not_hide_pdf_magic():
    assert has_format_magic(b"\n  " + _BOM + _PDF, "application/pdf")
    assert has_format_magic(_BOM + b"\n  " + _PDF, "application/pdf")


def test_bom_prefixed_pdf_is_captured():
    verdict = check_capture(
        body=_BOM + _PDF,
        expected_content_type="application/pdf",
        declared_content_type="application/pdf",
        min_bytes=500,
    )
    assert verdict.ok, verdict.detail


def test_bom_does_not_smuggle_a_716_stub_past_the_guard():
    """Skipping a BOM must not weaken the #716 defence.

    `looks_like_html` runs *before* the magic-number check and matches by
    substring, so it never depended on the payload's first byte. A BOM-prefixed
    stub is still refused, and still refused for the right reason.
    """
    verdict = check_capture(
        body=_BOM + _REDIRECT_STUB,
        expected_content_type="application/pdf",
    )
    assert not verdict
    assert verdict.reason == "html_where_binary_expected"


def test_bom_alone_is_not_a_pdf():
    assert not has_format_magic(_BOM + b"just some text", "application/pdf")


def test_716_redirect_stub_is_refused_as_pdf():
    """The named regression: 142 bytes of HTML must never be captured as a statute."""
    result = check_capture(
        body=_REDIRECT_STUB,
        expected_content_type="application/pdf",
    )
    assert not result
    assert result.reason == "html_where_binary_expected"


def test_stub_reason_names_the_actual_defect_not_a_symptom():
    """A 142-byte HTML stub is an HTML problem, not a size problem.

    Ordering matters: an operator reading `below_size_floor` looks for a truncated
    download, which is the wrong investigation.
    """
    result = check_capture(
        body=_REDIRECT_STUB,
        expected_content_type="application/pdf",
        min_bytes=10_000,
    )
    assert result.reason == "html_where_binary_expected"


def test_real_pdf_passes():
    assert check_capture(body=_PDF, expected_content_type="application/pdf")


def test_empty_body_is_refused():
    result = check_capture(body=b"", expected_content_type="application/pdf")
    assert not result
    assert result.reason == "empty_body"


def test_declared_content_type_mismatch_is_refused():
    result = check_capture(
        body=_PDF,
        expected_content_type="application/pdf",
        declared_content_type="text/html; charset=utf-8",
    )
    assert not result
    assert result.reason == "content_type_mismatch"


def test_charset_parameter_does_not_break_a_matching_content_type():
    assert check_capture(
        body=b"<html>a statute in html</html>" * 20,
        expected_content_type="text/html",
        declared_content_type="text/html; charset=utf-8",
    )


def test_size_floor_catches_a_valid_but_empty_pdf():
    """A structurally valid PDF can still be a cover page."""
    result = check_capture(
        body=b"%PDF-1.7\n%%EOF\n",
        expected_content_type="application/pdf",
        min_bytes=1_000,
    )
    assert not result
    assert result.reason == "below_size_floor"


def test_no_floor_configured_means_no_size_opinion():
    assert check_capture(
        body=b"%PDF-1.7\n%%EOF\n",
        expected_content_type="application/pdf",
    )


def test_guard_result_is_falsy_when_it_refuses():
    """Callers branch on the result directly; truthiness must track ok."""
    assert not check_capture(body=b"", expected_content_type="application/pdf")
    assert check_capture(body=_PDF, expected_content_type="application/pdf")
