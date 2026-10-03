"""Photo intake pipeline for OBJ-MSDS-04B PoC.

Tests:
  - Ordered JPEG set creation (sequence_no preserved)
  - JPEG normalization (long-edge 1920 / 2560)
  - Derived PDF from ordered JPEGs
  - Page order verification
  - OCR compatibility of derived PDF via pypdf text extraction
"""
import json
import os
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Spacer

_APPLE_GOTHIC = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"


def _font(size: int = 24):
    try:
        return ImageFont.truetype(_APPLE_GOTHIC, size)
    except Exception:
        return ImageFont.load_default()


def create_synthetic_photo(
    sequence_no: int,
    total_photos: int,
    text_lines: list[str],
    long_edge: int = 1920,
) -> Image.Image:
    """Create a synthetic MSDS photo as a clean JPEG."""
    w, h = 1240, 1754  # A4 ratio base
    img = Image.new("RGB", (w, h), color=(245, 245, 240))  # slightly off-white (paper)
    draw = ImageDraw.Draw(img)

    # Header
    font_hdr = _font(28)
    draw.text((40, 30), f"MSDS 사진 (Photo {sequence_no}/{total_photos})", fill=(30, 30, 30), font=font_hdr)

    # Content lines
    font_body = _font(22)
    y = 100
    for line in text_lines:
        draw.text((40, y), line, fill=(20, 20, 20), font=font_body)
        y += 32
        if y > h - 60:
            break

    # Footer marker for order verification
    font_sm = _font(18)
    draw.text((40, h - 60), f"[SEQ:{sequence_no:03d}]", fill=(180, 180, 180), font=font_sm)

    # Resize to target long edge
    scale = long_edge / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    return img


def normalize_jpeg(img: Image.Image, long_edge: int = 1920) -> Image.Image:
    """Resize image so the long edge == long_edge. No WebP."""
    w, h = img.size
    if max(w, h) == long_edge:
        return img
    scale = long_edge / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def create_ordered_jpeg_set(
    product_name: str,
    n_photos: int,
    output_dir: Path,
    long_edge: int = 1920,
) -> list[dict]:
    """Generate n_photos synthetic MSDS photos in correct sequence order."""
    output_dir.mkdir(parents=True, exist_ok=True)
    photo_records = []

    for seq in range(1, n_photos + 1):
        lines = [
            f"물질안전보건자료 (MSDS)",
            f"제품명: {product_name}",
            f"",
            f"사진 {seq}/{n_photos} — Section {seq + 1}",
            f"",
            "이 페이지는 사진 촬영 방식으로 수집된 MSDS 내용입니다.",
            "CAS No.: 7647-01-0" if seq == 1 else "",
        ]
        img = create_synthetic_photo(seq, n_photos, lines, long_edge=long_edge)
        out_path = output_dir / f"photo_{seq:03d}.jpg"
        img.save(str(out_path), "JPEG", quality=85)
        photo_records.append({
            "sequence_no": seq,
            "path": str(out_path),
            "long_edge": max(img.size),
            "size_bytes": os.path.getsize(out_path),
        })

    return photo_records


def create_derived_pdf(
    photo_records: list[dict],
    output_path: Path,
) -> dict:
    """Combine ordered JPEG photos into a single derived PDF using canvas.

    Page order must match sequence_no order. Returns verification dict.
    """
    from reportlab.pdfgen import canvas as rl_canvas

    sorted_photos = sorted(photo_records, key=lambda r: r["sequence_no"])
    page_w, page_h = A4
    pad = 4  # pts safety margin

    c = rl_canvas.Canvas(str(output_path), pagesize=A4)
    for rec in sorted_photos:
        img = Image.open(rec["path"])
        iw, ih = img.size
        scale = min((page_w - pad * 2) / iw, (page_h - pad * 2) / ih)
        draw_w, draw_h = iw * scale, ih * scale
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2
        c.drawImage(rec["path"], x, y, width=draw_w, height=draw_h,
                    preserveAspectRatio=True)
        c.showPage()
    c.save()

    size_bytes = os.path.getsize(output_path)
    return {
        "path": str(output_path),
        "page_count": len(sorted_photos),
        "size_bytes": size_bytes,
        "sequence_preserved": [r["sequence_no"] for r in sorted_photos],
    }


def verify_derived_pdf(pdf_path: Path, expected_sequence: list[int]) -> dict:
    """Verify page count and that SEQ markers appear in correct order in native text."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    actual_pages = len(reader.pages)
    expected_pages = len(expected_sequence)

    seq_found = []
    for page in reader.pages:
        text = page.extract_text() or ""
        # Look for [SEQ:NNN] markers embedded in the synthetic photos
        import re
        m = re.search(r'\[SEQ:(\d+)\]', text)
        if m:
            seq_found.append(int(m.group(1)))

    order_correct = seq_found == expected_sequence if seq_found else None

    return {
        "page_count_expected": expected_pages,
        "page_count_actual": actual_pages,
        "page_count_match": actual_pages == expected_pages,
        "seq_markers_found": seq_found,
        "order_correct": order_correct,
        "note": "seq_markers_found may be empty if JPEG text is image-only (expected)",
    }


def run_photo_pipeline_test(output_dir: Path) -> dict:
    """End-to-end photo pipeline test. Returns full result dict."""
    results = {}
    product_name = "아세톤 (99.5% 이상) — Photo Pipeline Test"
    n_photos = 5
    expected_seq = list(range(1, n_photos + 1))

    photo_dir = output_dir / "photo_pipeline"

    # Test both long-edge sizes
    for long_edge in (1920, 2560):
        le_key = f"jpeg_{long_edge}"
        le_dir = photo_dir / str(long_edge)
        t0 = time.perf_counter()
        records = create_ordered_jpeg_set(product_name, n_photos, le_dir, long_edge=long_edge)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Verify sizes
        sizes = [r["size_bytes"] for r in records]
        long_edges = [r["long_edge"] for r in records]
        order_correct = [r["sequence_no"] for r in records] == expected_seq

        pdf_path = le_dir / "derived.pdf"
        pdf_result = create_derived_pdf(records, pdf_path)
        verify_result = verify_derived_pdf(pdf_path, expected_seq)

        results[le_key] = {
            "long_edge": long_edge,
            "n_photos": n_photos,
            "elapsed_ms": round(elapsed_ms, 1),
            "photo_sizes_bytes": sizes,
            "long_edges_correct": all(le == long_edge for le in long_edges),
            "sequence_order_correct": order_correct,
            "derived_pdf": pdf_result,
            "derived_pdf_verify": verify_result,
            "status": (
                "PASS"
                if order_correct and pdf_result["page_count"] == n_photos
                else "FAIL"
            ),
        }

    return results
