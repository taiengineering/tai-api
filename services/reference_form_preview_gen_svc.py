"""Reference Form Preview Generation Service — WO-TAI-FORM647-PREVIEW-INTEGRATION-001

입력 파일 bytes → 첫 페이지 PNG bytes.

지원 형식:
  PDF           : pypdfium2 직접 렌더링
  OLE2 HWP      : Gotenberg LibreOffice → PDF → pypdfium2
  HWPX          : rhwp-python 직접 렌더링

형식 판별: 파일 헤더 시그니처 (확장자 무관).
  PDF  : b'%PDF-'
  HWPX : ZIP 헤더 (504b0304) + mimetype = 'application/hwp+zip'
  OLE2 : D0CF11E0A1B11AE1

GOTENBERG_URL 은 환경변수에서만 읽는다.
"""
from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass
from typing import Literal

_PDF_MAGIC    = b"%PDF-"
_OLE2_MAGIC   = bytes.fromhex("D0CF11E0A1B11AE1")
_ZIP_MAGIC    = bytes.fromhex("504b0304")
_HWPX_MIME    = b"application/hwp+zip"

_DEFAULT_DPI  = 150
_MAX_INPUT_MB = 20
_MAX_OUTPUT_MB = 50
_MAX_DIMENSION = 10_000  # px — 이를 초과하는 단일 차원은 비정상 렌더 판정

FileFormat = Literal["pdf", "hwp_ole2", "hwpx", "unknown"]


class PreviewError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreviewResult:
    png_bytes: bytes
    source_format: FileFormat
    page_count: int
    width_px: int
    height_px: int
    dpi: int


# ---------------------------------------------------------------------------
# 형식 판별
# ---------------------------------------------------------------------------

def detect_format(raw: bytes) -> FileFormat:
    if raw[:5] == _PDF_MAGIC:
        return "pdf"
    if raw[:4] == _ZIP_MAGIC:
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            if "mimetype" in z.namelist():
                mime = z.read("mimetype").strip()
                if _HWPX_MIME in mime:
                    return "hwpx"
        except Exception:
            pass
        return "unknown"
    if raw[:8] == _OLE2_MAGIC:
        return "hwp_ole2"
    return "unknown"


# ---------------------------------------------------------------------------
# 출력 크기 가드
# ---------------------------------------------------------------------------

def _guard_output(png_bytes: bytes, w: int, h: int) -> None:
    """출력 PNG가 크기·차원 한도를 초과하면 PreviewError를 발생시킨다."""
    if len(png_bytes) > _MAX_OUTPUT_MB * 1024 * 1024:
        raise PreviewError(
            "OUTPUT_TOO_LARGE",
            f"PNG 출력 크기가 {_MAX_OUTPUT_MB}MB를 초과합니다: {len(png_bytes):,} bytes",
        )
    if w > _MAX_DIMENSION or h > _MAX_DIMENSION:
        raise PreviewError(
            "OUTPUT_DIMENSION_EXCEEDED",
            f"PNG 출력 차원이 {_MAX_DIMENSION}px를 초과합니다: {w}×{h}",
        )


# ---------------------------------------------------------------------------
# PDF → PNG (pypdfium2)
# ---------------------------------------------------------------------------

def _pdf_to_png(pdf_bytes: bytes, dpi: int) -> tuple[bytes, int, int, int]:
    """PDF bytes → (png_bytes, page_count, width_px, height_px)."""
    try:
        import pypdfium2
    except ImportError as exc:
        raise PreviewError("DEP_MISSING", "pypdfium2 not installed") from exc

    try:
        from PIL import Image
    except ImportError as exc:
        raise PreviewError("DEP_MISSING", "Pillow not installed") from exc

    try:
        doc = pypdfium2.PdfDocument(pdf_bytes)
    except Exception as exc:
        raise PreviewError("PDF_PARSE_FAILED", f"PDF 파싱 실패: {exc}") from exc

    page_count = len(doc)
    if page_count == 0:
        raise PreviewError("PDF_EMPTY", "PDF에 페이지가 없습니다.")

    page = doc[0]
    w_pt, h_pt = page.get_width(), page.get_height()
    if w_pt <= 0 or h_pt <= 0:
        raise PreviewError("PDF_ZERO_PAGE", f"첫 페이지 치수가 0입니다: {w_pt}×{h_pt} pt")

    scale = dpi / 72
    try:
        bitmap = page.render(scale=scale, rotation=0)
        pil_img = bitmap.to_pil()
    except Exception as exc:
        raise PreviewError("PDF_RENDER_FAILED", f"PDF 렌더링 실패: {exc}") from exc

    if pil_img.mode == "RGBA":
        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
        bg.paste(pil_img, mask=pil_img.split()[3])
        pil_img = bg
    elif pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    _guard_output(png_bytes, pil_img.width, pil_img.height)
    return png_bytes, page_count, pil_img.width, pil_img.height


# ---------------------------------------------------------------------------
# HWP OLE2 → PDF via Gotenberg → PNG
# ---------------------------------------------------------------------------

def _hwp_ole2_to_png(raw: bytes, dpi: int) -> tuple[bytes, int, int, int]:
    """OLE2 HWP bytes → PNG. Gotenberg LibreOffice 경유."""
    try:
        import httpx
    except ImportError as exc:
        raise PreviewError("DEP_MISSING", "httpx not installed") from exc

    gotenberg_url = (os.getenv("GOTENBERG_URL") or "").strip().rstrip("/")
    if not gotenberg_url:
        raise PreviewError(
            "CONFIG_MISSING",
            "GOTENBERG_URL 환경변수가 설정되지 않았습니다.",
        )

    url = gotenberg_url + "/forms/libreoffice/convert"
    files = {"files": ("document.hwp", raw, "application/octet-stream")}
    try:
        resp = httpx.post(url, files=files, timeout=60.0)
    except Exception as exc:
        raise PreviewError("GOTENBERG_UNAVAILABLE", f"Gotenberg 연결 실패: {exc}") from exc

    if resp.status_code != 200:
        raise PreviewError(
            "GOTENBERG_CONVERT_FAILED",
            f"LibreOffice 변환 실패 HTTP {resp.status_code}: {resp.text[:200]}",
        )

    pdf_bytes = resp.content
    if not pdf_bytes.startswith(_PDF_MAGIC):
        raise PreviewError("GOTENBERG_INVALID_PDF", "Gotenberg 응답이 PDF 아님")

    return _pdf_to_png(pdf_bytes, dpi)


# ---------------------------------------------------------------------------
# HWPX → PNG (rhwp-python)
# ---------------------------------------------------------------------------

def _hwpx_to_png(raw: bytes, dpi: float) -> tuple[bytes, int, int, int]:
    """HWPX bytes → PNG. rhwp-python 직접 렌더링."""
    try:
        import rhwp
    except ImportError as exc:
        raise PreviewError("DEP_MISSING", "rhwp-python not installed") from exc

    try:
        from PIL import Image
    except ImportError as exc:
        raise PreviewError("DEP_MISSING", "Pillow not installed") from exc

    try:
        doc = rhwp.Document.from_bytes(raw)
    except Exception as exc:
        raise PreviewError("HWPX_PARSE_FAILED", f"HWPX 파싱 실패: {exc}") from exc

    page_count = doc.page_count
    try:
        png_bytes = doc.render_png(0, dpi=dpi)
    except Exception as exc:
        raise PreviewError("HWPX_RENDER_FAILED", f"HWPX 렌더링 실패: {exc}") from exc

    img = Image.open(io.BytesIO(png_bytes))
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

    _guard_output(png_bytes, img.width, img.height)
    return png_bytes, page_count, img.width, img.height


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------

def generate_preview(raw: bytes, *, dpi: int = _DEFAULT_DPI) -> PreviewResult:
    """파일 bytes → 첫 페이지 PNG PreviewResult.

    Args:
        raw: 원본 파일 bytes (PDF / OLE2 HWP / HWPX).
        dpi: 렌더링 해상도 (기본 150).

    Raises:
        PreviewError: 형식 미지원, 렌더링 실패, 의존성 누락.
    """
    if len(raw) == 0:
        raise PreviewError("EMPTY_FILE", "빈 파일")
    if len(raw) > _MAX_INPUT_MB * 1024 * 1024:
        raise PreviewError("FILE_TOO_LARGE", f"파일 크기 {_MAX_INPUT_MB}MB 초과")

    fmt = detect_format(raw)

    if fmt == "pdf":
        png, pages, w, h = _pdf_to_png(raw, dpi)
    elif fmt == "hwp_ole2":
        png, pages, w, h = _hwp_ole2_to_png(raw, dpi)
    elif fmt == "hwpx":
        png, pages, w, h = _hwpx_to_png(raw, dpi)
    else:
        raise PreviewError(
            "UNSUPPORTED_FORMAT",
            f"지원되지 않는 파일 형식 (헤더: {raw[:8].hex()})"
        )

    return PreviewResult(
        png_bytes=png,
        source_format=fmt,
        page_count=pages,
        width_px=w,
        height_px=h,
        dpi=dpi,
    )
