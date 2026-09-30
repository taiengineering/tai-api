"""Legal content projection — Public presentation resolver for law_article + law_attachment.

Raw SoT (law_article.article_text, law_attachment) is never modified.
This module decides what to show to end users by classifying article_text
and, when needed, falling back to law_attachment.

Content modes:
  ARTICLE_TEXT             — normal article; display article_text
  SOURCE_UI_STUB           — law enforcement site nav prompt; resolved via attachment
  INLINE_MEDIA             — real article with embedded <img ...> tags
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
  unresolved_media_ids: list[str] # raw <img id="…"> / alt="imgN" values
"""
from __future__ import annotations

import re
from typing import Optional

# Minimum character count for an attachment to qualify as a substantial body.
# Short attachments (개정이유서, 법령별표 목차 references) are typically < 500 chars.
# Actual regulation body text is reliably > 1000 chars.
SUBSTANTIAL_TEXT_MIN_CHARS = 1000

# ── Classifier patterns ─────────────────────────────────────────────────────

# SOURCE_UI_STUB: requires AND of navigation-menu signal + button-navigation phrase.
# Single `이용하여 주십시오` alone is NOT a stub indicator (generic law prose).
_STUB_MENU_PATTERN = re.compile(r"상단\s*메뉴")
_STUB_BUTTON_PATTERNS = [
    re.compile(r"버튼을\s*이용하십시오"),
    re.compile(r"버튼을\s*이용해\s*주십시오"),
    re.compile(r"이용하여\s*주십시오"),
]

_RAW_DOWNLOAD_PATTERN = re.compile(r"/LSW/flDownload\.do\?flSeq=", re.IGNORECASE)

# INLINE_MEDIA detection: any <img opening tag (broad; catches all variants).
_INLINE_IMG_DETECT_PATTERN = re.compile(r'<img[\s>]', re.IGNORECASE)
# ID extraction from <img ... id="digits">
_INLINE_IMG_ID_PATTERN = re.compile(r'<img\s[^>]*id="(\d+)"', re.IGNORECASE)
# Alt-based ID extraction: alt="imgNNNN"
_INLINE_IMG_ALT_ID_PATTERN = re.compile(r'alt="img(\d+)"', re.IGNORECASE)
# Search cleaning: opening img tags and closing </img> tags
_INLINE_IMG_OPEN_PATTERN = re.compile(r'<img\b[^>]*/?>',  re.IGNORECASE)
_INLINE_IMG_CLOSE_PATTERN = re.compile(r'</img\s*>',       re.IGNORECASE)

# Title artifact patterns — standalone (unconditional)
_STUB_TITLE_STANDALONE_PATTERNS = [
    re.compile(r"상단\s*메뉴"),
    re.compile(r"버튼을\s*이용하십시오"),
    re.compile(r"버튼을\s*이용해\s*주십시오"),
    re.compile(r"이용하여\s*주십시오"),
]
# Title artifact patterns — context-dependent (only when article_text is SOURCE_UI_STUB)
_STUB_TITLE_CONTEXT_PATTERNS = [
    re.compile(r"의\s*자세한\s*내용"),
]


def _is_source_ui_stub(text: str) -> bool:
    """True if text is a navigation-prompt stub: requires BOTH menu AND button signal."""
    return bool(_STUB_MENU_PATTERN.search(text)) and any(
        p.search(text) for p in _STUB_BUTTON_PATTERNS
    )


def _classify_article_text(text: str) -> str:
    """Return a coarse content classification for article_text."""
    if not text:
        return "EMPTY"
    if _is_source_ui_stub(text):
        return "SOURCE_UI_STUB"
    if _RAW_DOWNLOAD_PATTERN.search(text):
        return "RAW_SOURCE_LINK"
    if _INLINE_IMG_DETECT_PATTERN.search(text):
        return "INLINE_MEDIA"
    return "ARTICLE_TEXT"


def _is_title_artifact(title: str, article_text_classification: str = None) -> bool:
    """True if article_title is a source UI stub artifact and must not be shown publicly.

    Standalone patterns are unconditional. Context patterns fire only when
    article_text_classification is SOURCE_UI_STUB, preventing over-removal of
    normal titles that happen to contain common phrases.
    """
    if not title:
        return False
    if (any(p.search(title) for p in _STUB_TITLE_STANDALONE_PATTERNS)
            or bool(_RAW_DOWNLOAD_PATTERN.search(title))):
        return True
    if article_text_classification == "SOURCE_UI_STUB":
        if any(p.search(title) for p in _STUB_TITLE_CONTEXT_PATTERNS):
            return True
    return False


def _extract_media_ids(text: str) -> list[str]:
    """Extract numeric media IDs from <img id="N"> and alt="imgN" attributes."""
    id_ids = _INLINE_IMG_ID_PATTERN.findall(text or "")
    alt_ids = _INLINE_IMG_ALT_ID_PATTERN.findall(text or "")
    seen: set[str] = set()
    result = []
    for i in id_ids + alt_ids:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


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
    """Return SUCCESS+CLEAN attachments (text not required — metadata display OK)."""
    return [
        a for a in (attachments or [])
        if (
            a.get("download_status") == "SUCCESS"
            and a.get("extraction_verdict") == "CLEAN"
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
                      For bounded Phase-A/B fetches, SUCCESS+CLEAN rows beyond
                      the batch limit will have no attachment_text — they are
                      included in ATTACHMENT_INDEX metadata but not counted as
                      substantial.  Pass None or [] when no lookup was performed.

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
        # Multiple substantial: show all SUCCESS+CLEAN in metadata (includes un-fetched rows)
        all_clean = _clean_attachments(attachments or [])
        return {
            "content_mode": "ATTACHMENT_INDEX",
            "display_text": None,
            "attachments": _attachment_summaries(all_clean),
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

    Uses article_text classification as context for detecting navigation-
    description titles (e.g. `「KC 62619」의 자세한 내용은`) that standalone
    patterns would miss.

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

    # Classify article_text for context-dependent title artifact detection
    article_text = row.get("article_text") or ""
    article_text_classification = _classify_article_text(article_text)
    title_artifact = _is_title_artifact(article_title or "", article_text_classification)

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
    """Return clean search_text using raw article_text only (no attachment resolution).

    Strips SOURCE_UI_STUB / RAW_SOURCE_LINK artifacts and img markup.
    For projection-aware search (with attachment body), use search_text_from_projection().
    """
    text = (article_text or "").strip()
    classification = _classify_article_text(text)
    if classification in ("SOURCE_UI_STUB", "RAW_SOURCE_LINK", "EMPTY"):
        return title
    if classification == "INLINE_MEDIA":
        cleaned = _INLINE_IMG_OPEN_PATTERN.sub("", text)
        cleaned = _INLINE_IMG_CLOSE_PATTERN.sub("", cleaned).strip()
        return " ".join(filter(None, [title, cleaned]))
    # ARTICLE_TEXT
    return " ".join(filter(None, [title, text]))


def search_text_from_projection(projection: dict, title: str) -> str:
    """Return search_text from a fully resolved projection dict.

    Includes attachment body for ATTACHMENT_BODY, attachment titles for
    ATTACHMENT_INDEX. For INLINE_MEDIA, strips all img markup.
    SOURCE_CONTENT_UNRESOLVED → title only.
    """
    mode = projection.get("content_mode", "ARTICLE_TEXT")
    display = projection.get("display_text") or ""
    if mode == "ARTICLE_TEXT":
        return " ".join(filter(None, [title, display]))
    if mode == "ATTACHMENT_BODY":
        return " ".join(filter(None, [title, display]))
    if mode == "INLINE_MEDIA":
        cleaned = _INLINE_IMG_OPEN_PATTERN.sub("", display)
        cleaned = _INLINE_IMG_CLOSE_PATTERN.sub("", cleaned).strip()
        return " ".join(filter(None, [title, cleaned]))
    if mode == "ATTACHMENT_INDEX":
        att_titles = " ".join(
            filter(None, (a.get("title") or "" for a in (projection.get("attachments") or [])))
        )
        return " ".join(filter(None, [title, att_titles]))
    # SOURCE_CONTENT_UNRESOLVED
    return title


def is_sitemap_eligible(article_text: Optional[str]) -> bool:
    """Legacy raw-text heuristic (no attachment resolution).

    For full projection-aware eligibility use is_sitemap_eligible_from_mode()
    with the resolved content_mode.

    Excludes EMPTY, SOURCE_UI_STUB, RAW_SOURCE_LINK.
    INLINE_MEDIA and ARTICLE_TEXT are eligible.
    Caller must still apply the >= 50 char length gate.
    """
    text = (article_text or "").strip()
    c = _classify_article_text(text)
    return c not in ("SOURCE_UI_STUB", "RAW_SOURCE_LINK", "EMPTY")
