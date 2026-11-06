"""WO-TAI-FORM647-PREVIEW-SPIKE-001 — 파일럿 3종 프리뷰 기술검증

대상:
  Pilot A PDF  (17649099_licbyl.pdf)   → pypdfium2 첫 페이지 → PNG
  Pilot A HWP  (17649099_licbyl.hwp)   → Gotenberg LibreOffice → PDF → pypdfium2 → PNG
  Pilot B HWPX (3033503_admbyl.hwp)    → Gotenberg LibreOffice (.hwp 및 .hwpx 각각) → PDF → pypdfium2 → PNG

금지: 운영 DB 변경, Storage 쓰기, 프리뷰 승인, 운영 Gotenberg 호출.

사용법:
  python3 scripts/spike_form647_preview.py
  GOTENBERG_URL=http://localhost:3500 python3 scripts/spike_form647_preview.py
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

try:
    import pypdfium2
except ImportError:
    log.error("pypdfium2 not installed. Run: pip install pypdfium2")
    sys.exit(1)

try:
    import httpx
except ImportError:
    log.error("httpx not installed")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    log.error("Pillow not installed")
    sys.exit(1)

from db.supabase_client import get_supabase

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

_GOTENBERG_URL = (os.getenv("GOTENBERG_URL") or "http://localhost:3500").rstrip("/")
_DST_BUCKET    = "reference-forms"
_RUN_ID        = "form647-remediation-002-714df47a637e3e73"
_OUT_DIR       = Path(__file__).resolve().parent / "output" / "preview_spike"
_DPI           = 150  # 첫 페이지 렌더 DPI

_PILOT_FILES = [
    {
        "label":      "Pilot A PDF",
        "storage_path": f"form647/{_RUN_ID}/pdf/17649099_licbyl.pdf",
        "file_type":  "pdf",
        "registered_sha256": "62d6e4f7981ebd122f5233d42d7283a1b517c7429b034a3bb030a3fc6c136c74",
        "out_name":   "pilot_a_pdf",
    },
    {
        "label":      "Pilot A HWP (OLE2)",
        "storage_path": f"form647/{_RUN_ID}/hwp/17649099_licbyl.hwp",
        "file_type":  "hwp",
        "registered_sha256": "d6771324ae18d35302eacfc97fd5e300ff3d4f1a29c876150035b9ecbdd94906",
        "out_name":   "pilot_a_hwp",
    },
    {
        "label":      "Pilot B HWPX (stored as .hwp)",
        "storage_path": f"form647/{_RUN_ID}/hwp/3033503_admbyl.hwp",
        "file_type":  "hwpx",
        "registered_sha256": "9c39355c0cebe4df1d50985c81835e01d70953e1a1f784496bf061c18811fc06",
        "out_name":   "pilot_b_hwpx",
    },
]


# ---------------------------------------------------------------------------
# PDF → PNG via pypdfium2
# ---------------------------------------------------------------------------

def pdf_to_png(pdf_bytes: bytes, dpi: int = _DPI) -> tuple[bytes, int, int]:
    """PDF 첫 페이지를 PNG bytes로 반환한다. (png_bytes, width_px, height_px)"""
    doc = pypdfium2.PdfDocument(pdf_bytes)
    page = doc[0]
    scale = dpi / 72  # PDFium 기본 단위: pt at 72 dpi
    bitmap = page.render(scale=scale, rotation=0)
    pil_img = bitmap.to_pil()
    # RGB 보장
    if pil_img.mode not in ("RGB", "RGBA"):
        pil_img = pil_img.convert("RGB")
    if pil_img.mode == "RGBA":
        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
        bg.paste(pil_img, mask=pil_img.split()[3])
        pil_img = bg
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return buf.getvalue(), pil_img.width, pil_img.height


# ---------------------------------------------------------------------------
# HWP/HWPX → PDF via Gotenberg LibreOffice
# ---------------------------------------------------------------------------

def hwp_to_pdf_via_gotenberg(raw: bytes, filename: str, timeout: float = 60.0) -> bytes:
    """LibreOffice 경유 HWP/HWPX → PDF. PDF bytes 반환."""
    url = _GOTENBERG_URL + "/forms/libreoffice/convert"
    files = {"files": (filename, raw, "application/octet-stream")}
    resp = httpx.post(url, files=files, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"Gotenberg {resp.status_code}: {resp.text[:300]}")
    ctype = resp.headers.get("content-type", "")
    if "application/pdf" not in ctype and not resp.content.startswith(b"%PDF-"):
        raise RuntimeError(f"응답이 PDF 아님: content-type={ctype!r}, head={resp.content[:20]!r}")
    return resp.content


# ---------------------------------------------------------------------------
# 단일 파일 처리
# ---------------------------------------------------------------------------

def process_file(sb, pf: dict) -> dict:
    result = {
        "label":           pf["label"],
        "file_type":       pf["file_type"],
        "storage_path":    pf["storage_path"],
        "sha256_match":    None,
        "pdf_step":        None,   # None | "direct" | "gotenberg_hwp" | "gotenberg_hwpx"
        "pdf_size_bytes":  None,
        "png_size_bytes":  None,
        "png_width":       None,
        "png_height":      None,
        "out_png":         None,
        "verdict":         "FAIL",
        "error":           None,
    }

    # 1. 버킷에서 다운로드
    try:
        raw = sb.storage.from_(_DST_BUCKET).download(pf["storage_path"])
    except Exception as exc:
        result["error"] = f"download_failed: {exc}"
        return result

    # 2. SHA256 확인
    actual_sha = hashlib.sha256(raw).hexdigest()
    result["sha256_match"] = (actual_sha == pf["registered_sha256"])
    if not result["sha256_match"]:
        result["error"] = f"sha256_mismatch: actual={actual_sha[:16]}"
        return result

    file_type = pf["file_type"]

    # 3. PDF 획득
    pdf_bytes: bytes | None = None

    if file_type == "pdf":
        pdf_bytes = raw
        result["pdf_step"] = "direct"
        result["pdf_size_bytes"] = len(raw)

    elif file_type in ("hwp", "hwpx"):
        # OLE2 HWP — .hwp 확장자로 전송
        fname_hwp = pf["storage_path"].split("/")[-1]   # e.g. 17649099_licbyl.hwp
        try:
            log.info("  → Gotenberg LibreOffice (.hwp)  %s", fname_hwp)
            pdf_bytes = hwp_to_pdf_via_gotenberg(raw, fname_hwp)
            result["pdf_step"] = "gotenberg_hwp"
            result["pdf_size_bytes"] = len(pdf_bytes)
        except Exception as exc:
            log.warning("  .hwp 변환 실패: %s", exc)
            result["error"] = f"gotenberg_hwp_failed: {exc}"

        # HWPX: .hwp로 실패한 경우 또는 항상 .hwpx 확장자로도 시도
        if file_type == "hwpx":
            fname_hwpx = fname_hwp.replace(".hwp", ".hwpx")
            try:
                log.info("  → Gotenberg LibreOffice (.hwpx) %s", fname_hwpx)
                pdf_bytes_x = hwp_to_pdf_via_gotenberg(raw, fname_hwpx)
                # .hwpx 성공 여부를 별도 필드에 기록
                result["gotenberg_hwpx_pdf_size"] = len(pdf_bytes_x)
                result["gotenberg_hwpx_verdict"] = "OK"
                # 이미 .hwp로 성공했으면 .hwpx 결과는 비교용으로만 사용
                if pdf_bytes is None:
                    pdf_bytes = pdf_bytes_x
                    result["pdf_step"] = "gotenberg_hwpx"
                    result["pdf_size_bytes"] = len(pdf_bytes_x)
                    result["error"] = None
            except Exception as exc2:
                log.warning("  .hwpx 변환 실패: %s", exc2)
                result["gotenberg_hwpx_verdict"] = f"FAIL: {exc2}"

        if pdf_bytes is None:
            return result

    # 4. PDF → PNG (첫 페이지)
    try:
        png_bytes, w, h = pdf_to_png(pdf_bytes, dpi=_DPI)
        result["png_size_bytes"] = len(png_bytes)
        result["png_width"]  = w
        result["png_height"] = h
    except Exception as exc:
        result["error"] = f"pdf_to_png_failed: {exc}"
        return result

    # 5. PNG 저장
    out_path = _OUT_DIR / f"{pf['out_name']}.png"
    out_path.write_bytes(png_bytes)
    result["out_png"]  = str(out_path)
    result["verdict"]  = "PASS"
    result["error"]    = None
    log.info("  [PASS] %s  →  %dx%d px, %d bytes  →  %s",
             pf["label"], w, h, len(png_bytes), out_path.name)
    return result


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def run() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Gotenberg 헬스 확인
    try:
        hresp = httpx.get(_GOTENBERG_URL + "/health", timeout=5)
        log.info("Gotenberg health: %s", hresp.text[:120])
    except Exception as exc:
        log.error("Gotenberg 접근 불가 (%s): %s", _GOTENBERG_URL, exc)
        sys.exit(1)

    sb = get_supabase()

    results = []
    for pf in _PILOT_FILES:
        log.info("\n[%s]", pf["label"])
        r = process_file(sb, pf)
        results.append(r)

    # 요약
    print("\n" + "=" * 60)
    print("PREVIEW SPIKE 결과 요약")
    print("=" * 60)
    for r in results:
        status = "✓ PASS" if r["verdict"] == "PASS" else "✗ FAIL"
        print(f"\n{status}  {r['label']}")
        print(f"  sha256_match  : {r['sha256_match']}")
        print(f"  pdf_step      : {r['pdf_step']}")
        print(f"  pdf_size      : {r['pdf_size_bytes']:,} bytes" if r['pdf_size_bytes'] else "  pdf_size      : -")
        if r.get("gotenberg_hwpx_verdict"):
            print(f"  hwpx_verdict  : {r['gotenberg_hwpx_verdict']}")
        if r["verdict"] == "PASS":
            print(f"  png           : {r['png_width']}×{r['png_height']} px, {r['png_size_bytes']:,} bytes")
            print(f"  saved         : {Path(r['out_png']).name}")
        else:
            print(f"  error         : {r['error']}")

    # JSON 저장
    out_json = _OUT_DIR / "spike_results.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n결과 JSON: {out_json}")
    print(f"PNG 저장 위치: {_OUT_DIR}/")

    pass_count = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\nPASS {pass_count}/3")


if __name__ == "__main__":
    run()
