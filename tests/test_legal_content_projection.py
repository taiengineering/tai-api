"""Unit tests for services/legal_content_projection.py.

P01–P10: resolve_legal_content matrix
S01–S05: search_text_for_index
M01–M06: is_sitemap_eligible
P49: source artifact title excluded from public title and search_text
P50–P51: is_sitemap_eligible_from_mode
P52: robots_directive_for_mode
P53: LegalAdapter uses shared projection (no independent stub rules)
"""
from __future__ import annotations

import pytest

from services.legal_content_projection import (
    build_public_legal_title,
    is_sitemap_eligible,
    is_sitemap_eligible_from_mode,
    resolve_legal_content,
    robots_directive_for_mode,
    search_text_for_index,
)

# ── Fixtures ────────────────────────────────────────────────────────────────

NORMAL_TEXT = "사업주는 근로자에게 안전교육을 실시하여야 한다." * 3

KC_STUB = (
    '「전기용품 안전기준(KC 62619)」의 자세한 내용은 상단 메뉴 "<img id="40425753">'
    '자세한 내용</img>" 버튼을 이용하십시오.'
)

INLINE_IMG_TEXT = (
    "별표 1 <img id=\"12345\" src=\"/some/path.gif\"> 이하 기준을 따른다."
)

RAW_DOWNLOAD_TEXT = (
    "첨부파일: /LSW/flDownload.do?flSeq=99887766 을 참조하시오."
)

CLEAN_ATTACH_SINGLE = [
    {
        "id": "att-uuid-001",
        "attachment_title": "KC 62619 Ed 2.0",
        "download_status": "SUCCESS",
        "extraction_verdict": "CLEAN",
        "attachment_text": "가" * 45983,
    }
]

CLEAN_ATTACH_MULTI = [
    {
        "id": "att-uuid-001",
        "attachment_title": "시험방법 A",
        "download_status": "SUCCESS",
        "extraction_verdict": "CLEAN",
        "attachment_text": "가" * 1000,
    },
    {
        "id": "att-uuid-002",
        "attachment_title": "시험방법 B",
        "download_status": "SUCCESS",
        "extraction_verdict": "CLEAN",
        "attachment_text": "나" * 2000,
    },
]

FAILED_ATTACH = [
    {
        "id": "att-uuid-fail",
        "attachment_title": "실패 파일",
        "download_status": "FAILED",
        "extraction_verdict": None,
        "attachment_text": None,
    }
]


# ── resolve_legal_content ────────────────────────────────────────────────────

class TestResolveLegalContent:

    def test_p01_normal_article_text(self):
        r = resolve_legal_content(NORMAL_TEXT)
        assert r["content_mode"] == "ARTICLE_TEXT"
        assert r["display_text"] == NORMAL_TEXT
        assert r["attachments"] == []
        assert r["has_unresolved_media"] is False
        assert r["unresolved_media_ids"] == []

    def test_p02_source_ui_stub_single_clean_attachment(self):
        r = resolve_legal_content(KC_STUB, CLEAN_ATTACH_SINGLE)
        assert r["content_mode"] == "ATTACHMENT_BODY"
        assert len(r["display_text"]) == 45983
        assert len(r["attachments"]) == 1
        assert r["attachments"][0]["id"] == "att-uuid-001"
        assert r["attachments"][0]["text_length"] == 45983
        assert r["has_unresolved_media"] is False

    def test_p03_source_ui_stub_multi_clean_attachment(self):
        r = resolve_legal_content(KC_STUB, CLEAN_ATTACH_MULTI)
        assert r["content_mode"] == "ATTACHMENT_INDEX"
        assert r["display_text"] is None
        assert len(r["attachments"]) == 2
        titles = {a["title"] for a in r["attachments"]}
        assert "시험방법 A" in titles and "시험방법 B" in titles

    def test_p04_source_ui_stub_no_clean_attachment(self):
        r = resolve_legal_content(KC_STUB, FAILED_ATTACH)
        assert r["content_mode"] == "SOURCE_CONTENT_UNRESOLVED"
        assert r["display_text"] is None

    def test_p05_source_ui_stub_no_attachments_at_all(self):
        r = resolve_legal_content(KC_STUB, [])
        assert r["content_mode"] == "SOURCE_CONTENT_UNRESOLVED"

    def test_p06_inline_media_article(self):
        r = resolve_legal_content(INLINE_IMG_TEXT)
        assert r["content_mode"] == "INLINE_MEDIA"
        assert r["display_text"] == INLINE_IMG_TEXT
        assert r["has_unresolved_media"] is True
        assert "12345" in r["unresolved_media_ids"]

    def test_p07_raw_source_link_resolves_to_attachment(self):
        r = resolve_legal_content(RAW_DOWNLOAD_TEXT, CLEAN_ATTACH_SINGLE)
        assert r["content_mode"] == "ATTACHMENT_BODY"

    def test_p08_none_article_text_no_attachments(self):
        r = resolve_legal_content(None, [])
        assert r["content_mode"] == "SOURCE_CONTENT_UNRESOLVED"
        assert r["display_text"] is None

    def test_p09_attachment_body_not_chosen_when_failed(self):
        r = resolve_legal_content(KC_STUB, FAILED_ATTACH)
        assert r["content_mode"] == "SOURCE_CONTENT_UNRESOLVED"

    def test_p10_normal_text_identity_unchanged(self):
        """Normal article_text must pass through identical — no stripping."""
        text = "제1조(목적) 이 법은 산업안전 및 보건에 관한 기준을 확립하기 위한 것이다."
        r = resolve_legal_content(text)
        assert r["display_text"] == text


# ── search_text_for_index ────────────────────────────────────────────────────

class TestSearchTextForIndex:

    def test_s01_normal_text_concatenated(self):
        title = "산업안전보건법 제29조"
        result = search_text_for_index(NORMAL_TEXT, title)
        assert title in result
        assert NORMAL_TEXT in result

    def test_s02_source_ui_stub_returns_only_title(self):
        title = "전기용품 안전기준(KC 62619) 제1조"
        result = search_text_for_index(KC_STUB, title)
        assert "상단 메뉴" not in result
        assert "버튼을 이용하십시오" not in result
        assert title in result

    def test_s03_raw_download_link_stripped(self):
        title = "대기오염공정시험기준 제3조"
        result = search_text_for_index(RAW_DOWNLOAD_TEXT, title)
        assert "/LSW/flDownload.do" not in result
        assert title in result

    def test_s04_inline_media_img_tag_removed(self):
        title = "건설기준 별표1"
        result = search_text_for_index(INLINE_IMG_TEXT, title)
        assert '<img' not in result
        assert "이하 기준을 따른다" in result

    def test_s05_none_text_returns_title(self):
        title = "산업안전보건법 제12조"
        result = search_text_for_index(None, title)
        assert result == title


# ── is_sitemap_eligible ──────────────────────────────────────────────────────

class TestIsSitemapEligible:

    def test_m01_normal_article_is_eligible(self):
        assert is_sitemap_eligible(NORMAL_TEXT) is True

    def test_m02_inline_media_is_eligible(self):
        assert is_sitemap_eligible(INLINE_IMG_TEXT) is True

    def test_m03_source_ui_stub_is_not_eligible(self):
        assert is_sitemap_eligible(KC_STUB) is False

    def test_m04_raw_download_is_not_eligible(self):
        assert is_sitemap_eligible(RAW_DOWNLOAD_TEXT) is False

    def test_m05_none_is_not_eligible(self):
        assert is_sitemap_eligible(None) is False

    def test_m06_empty_string_is_not_eligible(self):
        assert is_sitemap_eligible("") is False


# ── P49: Title artifact exclusion ───────────────────────────────────────────

class TestTitleArtifactExclusion:
    """P49 — source UI artifact in article_title must not appear in public title
    or search_text."""

    STUB_TITLE = "「전기용품 안전기준(KC 62619)」의 자세한 내용은 버튼을 이용하십시오"

    def _row(self, *, article_title=None):
        return {
            "id": "p49-uuid",
            "law_name": "전기용품안전관리법",
            "article_no": 5,
            "article_sub_no": None,
            "article_title": article_title,
            "article_text": KC_STUB,
        }

    def test_p49a_artifact_title_not_in_public_title(self):
        result = build_public_legal_title(self._row(article_title=self.STUB_TITLE))
        assert "버튼을 이용하십시오" not in result["title"]
        assert "상단 메뉴" not in result["title"]

    def test_p49b_display_article_title_is_none_for_artifact(self):
        result = build_public_legal_title(self._row(article_title=self.STUB_TITLE))
        assert result["display_article_title"] is None

    def test_p49c_clean_title_is_preserved(self):
        result = build_public_legal_title(self._row(article_title="목적"))
        assert result["display_article_title"] == "목적"
        assert "목적" in result["title"]

    def test_p49d_artifact_title_not_in_search_text(self):
        from services.shared_search.adapters.legal import _normalize_legal
        row = {
            "id": "p49-search-uuid",
            "record_kind": "law_article",
            "law_name": "전기용품안전관리법",
            "article_no": 5,
            "article_sub_no": None,
            "article_title": self.STUB_TITLE,
            "article_text": KC_STUB,
            "enforcement_date": "2023-01-01",
            "updated_at": "2023-01-01T00:00:00",
            "source_id": "LEG_OFFICIAL",
            "source_key": None,
        }
        result = _normalize_legal(row)
        assert result is not None
        assert "버튼을 이용하십시오" not in result["search_text"]
        assert "상단 메뉴" not in result["search_text"]


# ── P50–P52: SEO helpers ─────────────────────────────────────────────────────

class TestSeoHelpers:

    # P50 — SOURCE_CONTENT_UNRESOLVED excluded from sitemap
    def test_p50_unresolved_not_sitemap_eligible(self):
        assert is_sitemap_eligible_from_mode("SOURCE_CONTENT_UNRESOLVED") is False

    # P51 — raw stub but resolved to ATTACHMENT_BODY → sitemap eligible
    def test_p51_attachment_body_is_sitemap_eligible(self):
        assert is_sitemap_eligible_from_mode("ATTACHMENT_BODY") is True

    def test_p51b_article_text_mode_eligible(self):
        assert is_sitemap_eligible_from_mode("ARTICLE_TEXT") is True

    def test_p51c_attachment_index_eligible(self):
        assert is_sitemap_eligible_from_mode("ATTACHMENT_INDEX") is True

    def test_p51d_inline_media_eligible(self):
        assert is_sitemap_eligible_from_mode("INLINE_MEDIA") is True

    # P52 — dynamic robots directive
    def test_p52_unresolved_yields_noindex(self):
        assert robots_directive_for_mode("SOURCE_CONTENT_UNRESOLVED") == "noindex,follow"

    def test_p52b_attachment_body_yields_index(self):
        assert robots_directive_for_mode("ATTACHMENT_BODY") == "index,follow"

    def test_p52c_article_text_yields_index(self):
        assert robots_directive_for_mode("ARTICLE_TEXT") == "index,follow"


# ── P53: Adapter shared authority ────────────────────────────────────────────

class TestAdapterSharedAuthority:
    """P53 — LegalAdapter must not contain independent source-UI stub detection rules.
    Behavioral proof: stub article_text + stub article_title → clean title + clean search_text."""

    def test_p53_adapter_delegates_stub_detection_to_shared_module(self):
        from services.shared_search.adapters.legal import _normalize_legal
        row = {
            "id": "p53-uuid",
            "record_kind": "law_article",
            "law_name": "전기용품안전관리법",
            "article_no": 7,
            "article_sub_no": None,
            "article_title": "상단 메뉴 버튼을 이용하십시오",
            "article_text": KC_STUB,
            "enforcement_date": "2023-01-01",
            "updated_at": "2023-01-01T00:00:00",
            "source_id": "LEG_OFFICIAL",
            "source_key": None,
        }
        result = _normalize_legal(row)
        assert result is not None, "_normalize_legal must not return None for valid row"
        # Title: stub text must not appear
        assert "버튼을 이용하십시오" not in result["title"]
        assert "상단 메뉴" not in result["title"]
        # search_text: stub text must not appear
        assert "버튼을 이용하십시오" not in result["search_text"]
        assert "상단 메뉴" not in result["search_text"]
        # Law name must appear in title (shared title builder falls back to law+article_no)
        assert "전기용품안전관리법" in result["title"]

    def test_p53b_adapter_no_independent_stub_patterns(self):
        import inspect
        import services.shared_search.adapters.legal as legal_adapter_mod
        src = inspect.getsource(legal_adapter_mod)
        assert "from services.legal_content_projection import" in src, (
            "Adapter must import from shared legal_content_projection module"
        )
        assert "_SOURCE_UI_STUB_PATTERNS" not in src, (
            "Adapter must not define its own stub detection patterns"
        )
