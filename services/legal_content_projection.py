"""Legal content projection — Public presentation resolver for law_article + law_attachment.

Raw SoT (law_article.article_text, law_attachment) is never modified.
This module decides what to show to end users by classifying article_text
and, when needed, falling back to law_attachment.

Content modes:
  ARTICLE_TEXT             — normal article; display article_text
  SOURCE_UI_STUB           — law enforcement site nav prompt; resolved via attachment
  INLINE_MEDIA             — real article with embedded <img id=…> or similar
  RAW_SOURCE_LINK          — contains /LSW/flDownload.do internal path
  SOURCE_CONTENT_UNRESOLVED — stub detected, but no substantial viable attachment found

Attachment-resolved sub-modes (returned as content_mode):
  ATTACHMENT_BODY    — exactly one substantial CLEAN attachment; show its text
  ATTACHMENT_INDEX   — multiple substantial CLEAN candidates; show list

Public contract (returned dict):
  content_mode: str
  display_text: str | None        # usable text for ARTICLE_TEXT / ATTACHMENT_BODY
  attachments:  list[dict]        # for ATTACHMENT_INDEX; each has id, title, text_length
  has_unresolved_media: bool
  unresolved_media_ids: list[str] # raw <img id="…"> values
"""
from __future__ import annotations

import re
from typing import Optional

# Minimum character count for an attachment to qualify as a substantial body.
# Short attachments (개정이유서, 법령별표 목차 references) are typically < 500 chars.
# Actual regulation body text is reliably > 1000 chars.
SUBSTANTIAL_TEXT_MIN_CHARS = 1000

# ── Classifier patterns ─────────────────────────────────────────────────────

_SOURCE_UI_STUB_PATTERNS = [
    re.compile(r"상단\s*메뉴"),
    re.compile(r"버튼을\s*이용하십시오"),
    re.compile(r"버튼을\s*이용해\s*주십시오"),
    re.compile(r"이용하여\s*주십시오"),
]

_RAW_DOWNLOAD_PATTERN = re.compile(r"/LSW/flDownload\.do\?flSeq=", re.IGNORECASE)
_INLINE_IMG_PATTERN = re.compile(r'<img\s[^>]*id="(\d+)"', re.IGNORECASE)


def _classify_article_text(text: str) -> str:
    """Return a coarse content classification for article_text."""
    if not text:
        return "EMPTY"
    if any(p.search(text) for p in _SOURCE_UI_STUB_PATTERNS):
        return "SOURCE_UI_STUB"
    if _RAW_DOWNLOAD_PATTERN.search(text):
        return "RAW_SOURCE_LINK"
    if _INLINE_IMG_PATTERN.search(text):
        return "INLINE_MEDIA"
    return "ARTICLE_TEXT"


def _is_title_artifact(title: str) -> bool:
    """True if article_title contains source UI stub text and must not be shown publicly."""
    if not title:
        return False
    return (
        any(p.search(title) for p in _SOURCE_UI_STUB_PATTERNS)
        or bool(_RAW_DOWNLOAD_PATTERN.search(title))
    )


def _extract_media_ids(text: str) -> list[str]:
    return _INLINE_IMG_PATTERN.findall(text or "")


def _substantial_attachments(attachments: list[dict]) -> list[dict]:
    """Return SUCCESS+CLEAN attachments whose text meets SUBSTANTIAL_TEXT_MIN_CHARS."""
    return [
        a for a in (attachments or [])
        if (
            a.get("download_status") == "SUCCESS"
            and a.get("extraction_verdict") == "CLEAN"
            and len(a.get("attachment_text") or "") >= SUBSTANTIAL_TEXT_MIN_CHARS
        )
    ]


def _clean_attachments(attachments: list[dict]) -> list[dict]:
    """Return SUCCESS+CLEAN attachments with any non-empty text (for metadata display)."""
    return [
        a for a in (attachments or [])
        if (
            a.get("download_status") == "SUCCESS"
            and a.get("extraction_verdict") == "CLEAN"
            and a.get("attachment_text")
        )
    ]


def _attachment_summary(a: dict) -> dict:
    body = a.get("attachment_text") or ""
    return {
        "id": a.get("id"),
        "title": a.get("attachment_title"),
        "text_length": len(body),
    }


def _attachment_summaries(lst: list[dict]) -> list[dict]:
    return [_attachment_summary(a) for a in lst]


# ── Public content resolver ──────────────────────────────────────────────────

def resolve_legal_content(
    article_text: Optional[str],
    attachments: Optional[list[dict]] = None,
) -> dict:
    """Resolve what to present publicly for a law_article row.

    Args:
        article_text: raw law_article.article_text value (may be None)
        attachments:  list of law_attachment rows for the same law_version_id.
                      Each dict should contain at least:
                        id, attachment_title, download_status,
                        extraction_verdict, attachment_text (may be absent/None)
                      Pass None or [] when no attachment lookup was performed.

    Returns dict: content_mode, display_text, attachments,
    has_unresolved_media, unresolved_media_ids.
    """
    text = (article_text or "").strip()
    classification = _classify_article_text(text)

    if classification == "ARTICLE_TEXT":
        return {
            "content_mode": "ARTICLE_TEXT",
            "display_text": text or None,
            "attachments": [],
            "has_unresolved_media": False,
            "unresolved_media_ids": [],
        }

    if classification == "INLINE_MEDIA":
        media_ids = _extract_media_ids(text)
        return {
            "content_mode": "INLINE_MEDIA",
            "display_text": text or None,
            "attachments": [],
            "has_unresolved_media": True,
            "unresolved_media_ids": media_ids,
        }

    if classification in ("SOURCE_UI_STUB", "RAW_SOURCE_LINK", "EMPTY"):
        substantial = _substantial_attachments(attachments or [])
        if not substantial:
            return {
                "content_mode": "SOURCE_CONTENT_UNRESOLVED",
                "display_text": None,
                "attachments": _attachment_summaries(_clean_attachments(attachments or [])),
                "has_unresolved_media": False,
                "unresolved_media_ids": [],
            }
        if len(substantial) == 1:
            body = (substantial[0].get("attachment_text") or "").strip()
            return {
                "content_mode": "ATTACHMENT_BODY",
                "display_text": body or None,
                "attachments": [_attachment_summary(substantial[0])],
                "has_unresolved_media": False,
                "unresolved_media_ids": [],
            }
        # Multiple substantial candidates — do not pick arbitrarily
        return {
            "content_mode": "ATTACHMENT_INDEX",
            "display_text": None,
            "attachments": _attachment_summaries(substantial),
            "has_unresolved_media": False,
            "unresolved_media_ids": [],
        }

    return {
        "content_mode": "SOURCE_CONTENT_UNRESOLVED",
        "display_text": None,
        "attachments": [],
        "has_unresolved_media": False,
        "unresolved_media_ids": [],
    }


# ── Public title builder ─────────────────────────────────────────────────────

def build_public_legal_title(row: dict) -> dict:
    """Build safe public-facing title fields for a law_article row.

    Removes source UI artifact text from the public title.
    Raw article_title is not modified; display_article_title is set to None
    when the raw value is a stub artifact.

    Returns:
        title: str — safe title for public display and search
        display_article_title: str | None — article_title for display;
                                            None when article_title is an artifact
    """
    law_name = row.get("law_name") or ""
    article_no = row.get("article_no")
    article_sub_no = row.get("article_sub_no")
    article_title = row.get("article_title")
    canonical_id = row.get("id") or ""

    if law_name and article_no:
        article_part = f"제{article_no}조"
        if article_sub_no:
            article_part += f"의{article_sub_no}"
        title_base = f"{law_name} {article_part}"
    else:
        title_base = None

    title_artifact = _is_title_artifact(article_title or "")

    if title_artifact:
        title = title_base or f"law_article/{canonical_id}"
        display_article_title = None
    else:
        if title_base and article_title:
            title = f"{title_base} ({article_title})"
        elif title_base:
            title = title_base
        else:
            title = article_title or f"law_article/{canonical_id}"
        display_article_title = article_title

    return {"title": title, "display_article_title": display_article_title}


# ── SEO helpers ─────────────────────────────────────────────────────────────

def is_sitemap_eligible_from_mode(content_mode: str) -> bool:
    """True if the final projection content_mode should appear in the sitemap.

    Only SOURCE_CONTENT_UNRESOLVED is excluded — pages with no user-visible
    content should not be submitted to search engines.
    All other modes produce a meaningful page.
    """
    return content_mode != "SOURCE_CONTENT_UNRESOLVED"


def robots_directive_for_mode(content_mode: str) -> str:
    """Return the robots meta directive for a given content_mode.

    SOURCE_CONTENT_UNRESOLVED → noindex,follow (no real body to index).
    All other modes → index,follow.
    """
    if content_mode == "SOURCE_CONTENT_UNRESOLVED":
        return "noindex,follow"
    return "index,follow"


# ── Search text derivation ──────────────────────────────────────────────────

def search_text_for_index(article_text: Optional[str], title: str) -> str:
    """Return clean search_text for the OpenSearch index.

    Strips SOURCE_UI_STUB / RAW_SOURCE_LINK / bare <img> tags so they
    never enter the search index. For INLINE_MEDIA, strips img markup only
    and preserves surrounding prose. Caller supplies the safe public title.

    Note: for ATTACHMENT_BODY rows the attachment body is not injected here
    (doing so would require N+1 attachment queries across 35k rows).
    Attachment body search enrichment is deferred to a future batch WO.
    """
    text = (article_text or "").strip()
    classification = _classify_article_text(text)

    if classification in ("SOURCE_UI_STUB", "RAW_SOURCE_LINK", "EMPTY"):
        return title
    if classification == "INLINE_MEDIA":
        cleaned = _INLINE_IMG_PATTERN.sub("", text).strip()
        return " ".join(filter(None, [title, cleaned]))
    # ARTICLE_TEXT
    return " ".join(filter(None, [title, text]))


def is_sitemap_eligible(article_text: Optional[str]) -> bool:
    """True if raw article_text classification indicates page has visible content.

    This is a raw-text heuristic. For full projection-aware eligibility
    (which accounts for attachment resolution), use is_sitemap_eligible_from_mode()
    with the resolved content_mode.

    Excludes EMPTY, SOURCE_UI_STUB, RAW_SOURCE_LINK.
    INLINE_MEDIA and ARTICLE_TEXT are eligible.
    Caller must still apply the >= 50 char length gate.
    """
    text = (article_text or "").strip()
    c = _classify_article_text(text)
    return c not in ("SOURCE_UI_STUB", "RAW_SOURCE_LINK", "EMPTY")
