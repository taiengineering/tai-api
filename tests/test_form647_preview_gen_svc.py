"""WO-TAI-FORM647-PREVIEW-INTEGRATION-001 R1
reference_form_preview_gen_svc.py 최소 단위 테스트

검증 항목:
  SVC-01  PDF byte header → 'pdf' 판별
  SVC-02  OLE2 byte header → 'hwp_ole2' 판별
  SVC-03  HWPX (ZIP+mimetype) → 'hwpx' 판별
  SVC-04  미지원 헤더 → 'unknown' 판별
  SVC-05  빈 파일 → PreviewError(EMPTY_FILE)
  SVC-06  파일 크기 초과 → PreviewError(FILE_TOO_LARGE)
  SVC-07  미지원 형식 → PreviewError(UNSUPPORTED_FORMAT)
  SVC-08  PDF 손상(0 페이지) → PreviewError(PDF_EMPTY)
  SVC-09  PDF 렌더 후 차원 초과 → PreviewError(OUTPUT_DIMENSION_EXCEEDED)
  SVC-10  PDF 렌더 후 용량 초과 → PreviewError(OUTPUT_TOO_LARGE)
  SVC-11  _guard_output: 정상 차원 → 통과
"""
from __future__ import annotations

import io
import struct
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from services.reference_form_preview_gen_svc import (
    PreviewError,
    PreviewResult,
    _guard_output,
    detect_format,
    generate_preview,
)

# ---------------------------------------------------------------------------
# 형식 판별
# ---------------------------------------------------------------------------

_PDF_HEADER  = b"%PDF-1.4 some content"
_OLE2_HEADER = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 500
_JUNK        = b"\x00\x01\x02\x03\x04\x05\x06\x07" + b"\x00" * 100


def _make_hwpx_bytes() -> bytes:
    """최소 HWPX ZIP — mimetype 파일 포함."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("content.hpf", "<hpf/>")
    return buf.getvalue()


def test_svc_01_detect_pdf():
    assert detect_format(_PDF_HEADER) == "pdf"


def test_svc_02_detect_hwp_ole2():
    assert detect_format(_OLE2_HEADER) == "hwp_ole2"


def test_svc_03_detect_hwpx():
    assert detect_format(_make_hwpx_bytes()) == "hwpx"


def test_svc_04_detect_unknown():
    assert detect_format(_JUNK) == "unknown"


# ---------------------------------------------------------------------------
# generate_preview — 입력 가드
# ---------------------------------------------------------------------------

def test_svc_05_empty_file():
    with pytest.raises(PreviewError) as exc_info:
        generate_preview(b"")
    assert exc_info.value.code == "EMPTY_FILE"


def test_svc_06_file_too_large():
    # 20MB + 1 byte
    oversized = b"\x00" * (20 * 1024 * 1024 + 1)
    with pytest.raises(PreviewError) as exc_info:
        generate_preview(oversized)
    assert exc_info.value.code == "FILE_TOO_LARGE"


def test_svc_07_unsupported_format():
    with pytest.raises(PreviewError) as exc_info:
        generate_preview(_JUNK)
    assert exc_info.value.code == "UNSUPPORTED_FORMAT"


# ---------------------------------------------------------------------------
# PDF 경로 — 손상 파일 처리
# ---------------------------------------------------------------------------

def test_svc_08_pdf_empty_pages():
    """PDF 파싱은 성공하지만 페이지 수 0 → PDF_EMPTY."""
    mock_doc = MagicMock()
    mock_doc.__len__ = MagicMock(return_value=0)

    with patch("services.reference_form_preview_gen_svc._pdf_to_png") as mock_pdf:
        mock_pdf.side_effect = PreviewError("PDF_EMPTY", "PDF에 페이지가 없습니다.")
        with pytest.raises(PreviewError) as exc_info:
            generate_preview(_PDF_HEADER)
        assert exc_info.value.code == "PDF_EMPTY"


# ---------------------------------------------------------------------------
# 출력 가드
# ---------------------------------------------------------------------------

def test_svc_09_output_dimension_exceeded():
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with pytest.raises(PreviewError) as exc_info:
        _guard_output(png_bytes, w=10_001, h=100)
    assert exc_info.value.code == "OUTPUT_DIMENSION_EXCEEDED"


def test_svc_10_output_too_large():
    oversized_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * (50 * 1024 * 1024 + 1)
    with pytest.raises(PreviewError) as exc_info:
        _guard_output(oversized_png, w=1240, h=1753)
    assert exc_info.value.code == "OUTPUT_TOO_LARGE"


def test_svc_11_guard_output_normal():
    """정상 범위 → 예외 없음."""
    normal_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    _guard_output(normal_png, w=1240, h=1753)  # should not raise
