"""Reference Form Thumbnail Service — WO-WWW-SS-THUMBNAIL-001 P2.

Converts an existing approved Preview image (PNG) to a lightweight WebP thumbnail.

Spec:
  Format      WebP
  Max long edge  320 px (preserves aspect ratio)
  Quality        70
  Max output     70 KB hard limit
  Background     white (replaces transparency)
  Metadata       stripped

Security limits:
  MAX_INPUT_BYTES    10 MB  (matches reference-forms-preview bucket limit)
  MAX_INPUT_PIXELS   50 MP  (decompression bomb guard)

Only PNG/JPEG/WEBP inputs are accepted in phase 1.
PDF rendering support is deferred to a later phase.

Usage:
    result = generate_thumbnail(png_bytes)
    # result.webp_bytes, result.output_sha256, result.byte_count, result.generation_version
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

try:
    from PIL import Image, UnidentifiedImageError
except ImportError as _pil_err:  # pragma: no cover
    raise ImportError(
        "Pillow is required for thumbnail generation. "
        "Add Pillow>=10.4.0,<11 to requirements.txt."
    ) from _pil_err

MAX_LONG_EDGE     = 320
WEBP_QUALITY      = 70
MAX_OUTPUT_BYTES  = 70 * 1024       # 70 KB hard limit
MAX_INPUT_BYTES   = 10 * 1024 * 1024  # 10 MB
MAX_INPUT_PIXELS  = 50_000_000      # 50 MP (≈ 7071×7071)

GENERATION_VERSION = "v1-pillow"

_ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}

# Module-level pixel limit — applied before any Image.open() call.
Image.MAX_IMAGE_PIXELS = MAX_INPUT_PIXELS


class ThumbnailInputError(ValueError):
    """Input image cannot be processed (corrupt, oversized, wrong format)."""


class ThumbnailSizeError(ValueError):
    """Generated WebP exceeds the maximum byte limit."""


@dataclass(frozen=True)
class ThumbnailResult:
    webp_bytes: bytes
    output_sha256: str
    byte_count: int
    generation_version: str


def generate_thumbnail(
    input_bytes: bytes,
    *,
    max_long_edge: int = MAX_LONG_EDGE,
) -> ThumbnailResult:
    """Convert a Preview image to a WebP thumbnail.

    Args:
        input_bytes: Raw bytes of the source image (PNG / JPEG / WEBP).
        max_long_edge: Maximum pixels on the longer dimension (default 320).

    Returns:
        ThumbnailResult with webp_bytes, output_sha256, byte_count, generation_version.

    Raises:
        ThumbnailInputError: Bad input (too large, wrong format, corrupt).
        ThumbnailSizeError:  Generated WebP exceeds MAX_OUTPUT_BYTES.
    """
    if len(input_bytes) > MAX_INPUT_BYTES:
        raise ThumbnailInputError(
            f"Input {len(input_bytes)} bytes exceeds limit {MAX_INPUT_BYTES}"
        )
    if not input_bytes:
        raise ThumbnailInputError("Input is empty")

    # Open and validate format
    try:
        img = Image.open(io.BytesIO(input_bytes))
        img.load()  # force full decode — catches corrupt files and triggers pixel bomb guard
    except (UnidentifiedImageError, Exception) as exc:
        raise ThumbnailInputError(f"Cannot open image: {exc}") from exc

    if img.format not in _ALLOWED_FORMATS:
        raise ThumbnailInputError(
            f"Unsupported format {img.format!r}. Allowed: {sorted(_ALLOWED_FORMATS)}"
        )

    # Explicit pixel count guard — independent of Pillow's module-level DecompressionBomb
    # check so that callers get a ThumbnailInputError regardless of PIL warning settings.
    if img.width * img.height > MAX_INPUT_PIXELS:
        raise ThumbnailInputError(
            f"Image {img.width}×{img.height} = {img.width * img.height} pixels "
            f"exceeds limit {MAX_INPUT_PIXELS}"
        )

    # Flatten alpha / palette to RGB with white background
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize — preserve aspect ratio
    w, h = img.size
    if max(w, h) > max_long_edge:
        if w >= h:
            new_w = max_long_edge
            new_h = max(1, round(h * max_long_edge / w))
        else:
            new_h = max_long_edge
            new_w = max(1, round(w * max_long_edge / h))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # Encode to WebP (no EXIF/XMP metadata)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
    webp_bytes = buf.getvalue()

    if len(webp_bytes) > MAX_OUTPUT_BYTES:
        raise ThumbnailSizeError(
            f"Generated thumbnail {len(webp_bytes)} bytes exceeds limit {MAX_OUTPUT_BYTES}"
        )

    sha256 = hashlib.sha256(webp_bytes).hexdigest()
    return ThumbnailResult(
        webp_bytes=webp_bytes,
        output_sha256=sha256,
        byte_count=len(webp_bytes),
        generation_version=GENERATION_VERSION,
    )
