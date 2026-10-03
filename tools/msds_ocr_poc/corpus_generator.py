"""Synthetic MSDS corpus generator.

Produces PDF + JPEG for each fixture using reportlab and Pillow.
Korean text uses AppleGothic (macOS) with Latin fallback.
"""
import io
import json
import os
import random
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .corpus_data import MsdsFixture, ALL_FIXTURES

_APPLE_GOTHIC = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
_FONT_NAME = "AppleGothic"
_FONT_REGISTERED = False

W, H = A4  # 595 x 842 pts

PAGE_FILL_TEXT = (
    "이 페이지는 MSDS 문서의 나머지 섹션입니다. "
    "Section 2 유해성·위험성 / Section 4 응급조치 / "
    "Section 5 폭발·화재 시 대처방법 / Section 6 누출 사고 시 대처방법. "
    "This page contains additional safety information. "
)


def _register_font() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    if os.path.exists(_APPLE_GOTHIC):
        pdfmetrics.registerFont(TTFont(_FONT_NAME, _APPLE_GOTHIC))
        _FONT_REGISTERED = True


def _font() -> str:
    _register_font()
    return _FONT_NAME if _FONT_REGISTERED else "Helvetica"


# ---------------------------------------------------------------------------
# MSDS text content builders
# ---------------------------------------------------------------------------

def _section1_lines(f: MsdsFixture) -> list[str]:
    lines = [
        "물질안전보건자료 (Material Safety Data Sheet)",
        "",
        "1. 화학제품과 회사에 관한 정보 (Product and Company Identification)",
        "",
        f"제품명 (Product Name):  {f.product_name}",
        f"제조사 (Manufacturer):  {f.manufacturer_name}",
    ]
    if f.supplier_name:
        lines.append(f"공급자 (Supplier):       {f.supplier_name}")
    if f.product_code:
        lines.append(f"제품코드 (Product Code): {f.product_code}")
    lines += [
        "",
        "비상연락처 (Emergency):  1599-0000",
        "개정일 (Revision Date):  2026-01-01",
        "",
        "2. 유해성·위험성 (Hazard Identification)",
        "",
        "GHS 분류에 따른 유해·위험성 분류를 포함합니다.",
        "분류: 인화성 액체, 급성독성(경구/피부/흡입), 피부 부식/자극",
    ]
    return lines


def _section3_lines(f: MsdsFixture) -> list[str]:
    lines = [
        "",
        "3. 구성성분의 명칭 및 함유량 (Composition / Information on Ingredients)",
        "",
    ]
    for idx, cas in enumerate(f.cas_numbers, 1):
        lines += [
            f"  성분 {idx} (Component {idx}):",
            f"  CAS 번호 (CAS No.):   {cas}",
            f"  함유량 (Content):     제품별 상이 / Varies by product",
            "",
        ]
    return lines


def _filler_lines(page_num: int) -> list[str]:
    return [
        f"",
        f"(Page {page_num} — Additional Sections)",
        "",
        PAGE_FILL_TEXT * 3,
        "",
        "Section content continues on this page.",
    ]


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def _build_story(f: MsdsFixture, styles):
    font = _font()
    normal = styles["Normal"]
    normal.fontName = font
    normal.fontSize = 10
    normal.leading = 14

    story = []
    section1 = _section1_lines(f)

    for line in section1:
        story.append(Paragraph(line.replace("&", "&amp;"), normal))
        story.append(Spacer(1, 2))

    # Fill pages until CAS page
    for pg in range(2, f.cas_page):
        story.append(Paragraph(f"<br/>" * 40, normal))
        for line in _filler_lines(pg):
            story.append(Paragraph(line.replace("&", "&amp;"), normal))

    for line in _section3_lines(f):
        story.append(Paragraph(line.replace("&", "&amp;"), normal))

    # Fill remaining pages to reach total_pages
    for pg in range(f.cas_page + 1, f.total_pages + 1):
        story.append(Paragraph(f"<br/>" * 40, normal))
        for line in _filler_lines(pg):
            story.append(Paragraph(line.replace("&", "&amp;"), normal))

    return story


def generate_pdf(f: MsdsFixture, out_path: Path) -> None:
    _register_font()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story = _build_story(f, styles)
    doc.build(story)


# ---------------------------------------------------------------------------
# Image generation (JPEG scan simulation)
# ---------------------------------------------------------------------------

_JPEG_LONG_EDGE = 1920


def _render_text_to_image(lines: list[str], width: int = 1240, font_size: int = 18) -> Image.Image:
    img = Image.new("RGB", (width, 1754), color=(255, 255, 255))  # A4 ratio ~1:1.414
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(_APPLE_GOTHIC, font_size)
    except Exception:
        font = ImageFont.load_default()

    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(20, 20, 20), font=font)
        y += font_size + 6
        if y > img.height - 40:
            break
    return img


def _apply_variant(img: Image.Image, variant: str) -> Image.Image:
    if variant == "clean":
        return img
    if variant == "low_contrast":
        return ImageEnhance.Contrast(img).enhance(0.35)
    if variant == "rotated":
        return img.rotate(4.5, expand=True, fillcolor=(255, 255, 255))
    if variant == "small_text":
        w, h = img.size
        small = img.resize((w // 2, h // 2), Image.LANCZOS)
        return small.resize((w, h), Image.LANCZOS)
    if variant == "noise":
        import struct
        pixels = list(img.getdata())
        noisy = []
        for r, g, b in pixels:
            delta = random.randint(-30, 30)
            noisy.append((
                max(0, min(255, r + delta)),
                max(0, min(255, g + delta)),
                max(0, min(255, b + delta)),
            ))
        result = img.copy()
        result.putdata(noisy)
        return result
    if variant == "perspective":
        # Simple trapezoid — left side slightly compressed
        w, h = img.size
        coeffs = _find_perspective_coeffs(
            [(0, 0), (w, 0), (w, h), (0, h)],
            [(30, 20), (w - 10, 0), (w - 20, h), (0, h - 20)],
        )
        return img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC,
                              fillcolor=(255, 255, 255))
    return img


def _find_perspective_coeffs(src_coords, dst_coords):
    import numpy as np
    matrix = []
    for s, d in zip(src_coords, dst_coords):
        matrix.append([d[0], d[1], 1, 0, 0, 0, -s[0] * d[0], -s[0] * d[1]])
        matrix.append([0, 0, 0, d[0], d[1], 1, -s[1] * d[0], -s[1] * d[1]])
    A = np.matrix(matrix, dtype=float)
    B = np.array(src_coords).reshape(8)
    res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
    return np.array(res).reshape(8)


def generate_jpeg(f: MsdsFixture, out_path: Path, long_edge: int = _JPEG_LONG_EDGE) -> None:
    all_lines = (
        _section1_lines(f)
        + [""] * 6
        + _section3_lines(f)
    )
    img = _render_text_to_image(all_lines, font_size=20)
    img = _apply_variant(img, f.variant)

    # Resize to target long edge
    w, h = img.size
    if max(w, h) != long_edge:
        scale = long_edge / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    img.save(str(out_path), "JPEG", quality=85)


# ---------------------------------------------------------------------------
# Ground truth writer
# ---------------------------------------------------------------------------

def write_ground_truth(f: MsdsFixture, out_path: Path) -> None:
    gt = {
        "id": f.id,
        "product_name": f.product_name,
        "manufacturer_name": f.manufacturer_name,
        "supplier_name": f.supplier_name,
        "product_code": f.product_code,
        "cas_numbers": f.cas_numbers,
        "language": f.language,
        "variant": f.variant,
        "cas_page": f.cas_page,
        "total_pages": f.total_pages,
    }
    out_path.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Corpus generation entry point
# ---------------------------------------------------------------------------

def generate_corpus(output_dir: Path, fixtures: list[MsdsFixture] = None) -> list[dict]:
    if fixtures is None:
        fixtures = ALL_FIXTURES
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for f in fixtures:
        fdir = output_dir / f.id
        fdir.mkdir(exist_ok=True)

        pdf_path = fdir / f"{f.id}.pdf"
        jpeg_path = fdir / f"{f.id}.jpg"
        gt_path = fdir / "ground_truth.json"

        generate_pdf(f, pdf_path)
        generate_jpeg(f, jpeg_path)
        write_ground_truth(f, gt_path)

        generated.append({
            "id": f.id,
            "pdf": str(pdf_path),
            "jpeg": str(jpeg_path),
            "gt": str(gt_path),
            "fixture": f,
        })

    return generated
