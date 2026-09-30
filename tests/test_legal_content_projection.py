"""Unit tests for services/legal_content_projection.py.

P01–P10: resolve_legal_content matrix
S01–S05: search_text_for_index
M01–M06: is_sitemap_eligible
P49: source artifact title excluded from public title and search_text
P50–P51: is_sitemap_eligible_from_mode
P52: robots_directive_for_mode
P53: LegalAdapter uses shared projection (no independent stub rules)

PATCH-002:
  KC_TITLE: actual production KC 62619 title shape
  FALSE_NEG: 6 false-negative title matrix
  IMG_SRC: <img src=...> variant INLINE_MEDIA detection
  IMG_CLOSE: </img> search cleaning
  IMG_CENSUS: broad <img coverage
  STUB_HARD: hardened stub predicate (generic prose != stub)
  SEARCH_PROJ: projection-aware search_text (ATTACHMENT_BODY / INDEX / INLINE)
  BOUNDED: bounded attachment fetch test
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
    search_text_from_projection,
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


# ── PATCH-002: KC actual title + 6 false-negative matrix ────────────────────

class TestKCActualTitleShape:
    """KC_TITLE: actual production KC 62619 article_title form."""

    KC_ACTUAL_TITLE = "「전기용품 안전기준(KC 62619)」의 자세한 내용은"

    def _row(self, article_title):
        return {
            "id": "kc-uuid",
            "law_name": "전기용품안전관리법",
            "article_no": 1,
            "article_sub_no": None,
            "article_title": article_title,
            "article_text": KC_STUB,  # SOURCE_UI_STUB context
        }

    def test_kc_title_display_article_title_is_none(self):
        result = build_public_legal_title(self._row(self.KC_ACTUAL_TITLE))
        assert result["display_article_title"] is None, (
            "KC 62619 actual title must be detected as artifact when article_text is SOURCE_UI_STUB"
        )

    def test_kc_title_not_in_public_title(self):
        result = build_public_legal_title(self._row(self.KC_ACTUAL_TITLE))
        assert "자세한 내용은" not in result["title"]
        assert "KC 62619" not in result["title"] or "전기용품안전관리법" in result["title"]

    def test_kc_title_public_title_uses_law_plus_article_no(self):
        result = build_public_legal_title(self._row(self.KC_ACTUAL_TITLE))
        assert "전기용품안전관리법" in result["title"]
        assert "제1조" in result["title"]


class TestTitleFalseNegativeMatrix:
    """FALSE_NEG: 6 production title shapes that were false negatives before PATCH-002."""

    # All titles are of the form `「...」의 자세한 내용은`
    # They appear with SOURCE_UI_STUB article_text context
    STUB_ARTICLE_TEXT = KC_STUB  # any SOURCE_UI_STUB text

    FALSE_NEGATIVE_TITLES = [
        "「전기용품 안전기준(KC 62619)」의 자세한 내용은",
        "「KC 60884-1」의 자세한 내용은",
        "「KC 60335-2-17」의 자세한 내용은",
        "전기통신사업용 무선설비의 기술기준의 자세한 내용은",
        "잔류성유기오염물질공정시험기준의 자세한 내용은",
        "가정용 섬유제품 예비안전기준의 자세한 내용은",
    ]

    def _row(self, article_title):
        return {
            "id": "fn-uuid",
            "law_name": "테스트법령",
            "article_no": 1,
            "article_sub_no": None,
            "article_title": article_title,
            "article_text": self.STUB_ARTICLE_TEXT,
        }

    @pytest.mark.parametrize("stub_title", FALSE_NEGATIVE_TITLES)
    def test_false_negative_title_detected_as_artifact(self, stub_title):
        result = build_public_legal_title(self._row(stub_title))
        assert result["display_article_title"] is None, (
            f"Title should be artifact: {stub_title!r}"
        )
        assert "자세한 내용은" not in result["title"], (
            f"Artifact text leaked into public title: {result['title']!r}"
        )

    def test_normal_title_with_content_description_not_removed(self):
        """A title with `내용` (unrelated to stub) on a normal article must NOT be removed."""
        row = {
            "id": "normal-uuid",
            "law_name": "산업안전보건법",
            "article_no": 5,
            "article_sub_no": None,
            "article_title": "안전보건교육의 내용 및 시간",
            "article_text": NORMAL_TEXT,  # ARTICLE_TEXT context
        }
        result = build_public_legal_title(row)
        assert result["display_article_title"] == "안전보건교육의 내용 및 시간"


# ── PATCH-002: INLINE_MEDIA broadened regex ──────────────────────────────────

class TestInlineMediaBroadened:
    """IMG_SRC + IMG_CLOSE + IMG_CENSUS: <img src=...> and </img> handling."""

    IMG_SRC_TEXT = (
        '별표 2 <img src="http://www.law.go.kr/flDownload.do?flSeq=22909013" '
        'alt="img22909013"> 이하 기준을 따른다.'
    )

    IMG_CLOSE_TEXT = (
        '별표 3 <img id="99887766">내용</img> 이하 기준을 따른다.'
    )

    def test_img_src_classified_as_inline_media(self):
        from services.legal_content_projection import _classify_article_text
        assert _classify_article_text(self.IMG_SRC_TEXT) == "INLINE_MEDIA"

    def test_img_src_resolve_mode(self):
        r = resolve_legal_content(self.IMG_SRC_TEXT)
        assert r["content_mode"] == "INLINE_MEDIA"
        assert r["has_unresolved_media"] is True

    def test_img_src_not_in_search_text(self):
        title = "건설기준 별표2"
        result = search_text_for_index(self.IMG_SRC_TEXT, title)
        assert "<img" not in result
        assert "이하 기준을 따른다" in result

    def test_img_close_tag_removed_from_search_text(self):
        title = "건설기준 별표3"
        result = search_text_for_index(self.IMG_CLOSE_TEXT, title)
        assert "<img" not in result
        assert "</img>" not in result
        assert "이하 기준을 따른다" in result

    def test_img_alt_id_extracted(self):
        """alt="imgN" format yields numeric ID."""
        from services.legal_content_projection import _extract_media_ids
        ids = _extract_media_ids(self.IMG_SRC_TEXT)
        assert "22909013" in ids

    def test_img_src_display_text_preserved_raw(self):
        """display_text must keep raw markup — caller handles rendering."""
        r = resolve_legal_content(self.IMG_SRC_TEXT)
        assert r["display_text"] == self.IMG_SRC_TEXT

    def test_multiple_img_tags_all_detected(self):
        """All <img variants in a single article are classified as INLINE_MEDIA."""
        from services.legal_content_projection import _classify_article_text
        mixed = (
            '조항1 <img id="111"> 조항2 '
            '<img src="http://www.law.go.kr/flDownload.do?flSeq=222" alt="img222"> '
            '조항3'
        )
        assert _classify_article_text(mixed) == "INLINE_MEDIA"

    def test_364_img_articles_coverage_logic(self):
        """Verify that articles with any <img variant are classified INLINE_MEDIA,
        not ARTICLE_TEXT. Simulates the 44-row gap between old id-only regex and new."""
        from services.legal_content_projection import _classify_article_text
        # Old id-based regex missed these
        no_id_variants = [
            '<img src="http://www.law.go.kr/flDownload.do?flSeq=111">',
            '<img alt="img222" src="...">',
            '<img\nsrc="http://...">',
        ]
        for variant in no_id_variants:
            text = f"조항 {variant} 이하 기준을 따른다."
            cls = _classify_article_text(text)
            assert cls == "INLINE_MEDIA", f"Expected INLINE_MEDIA for: {variant!r}"


# ── PATCH-002: SOURCE_UI_STUB hardening ──────────────────────────────────────

class TestStubPredicateHardening:
    """STUB_HARD: single `이용하여 주십시오` in normal prose must NOT be stub."""

    def test_generic_use_phrase_alone_is_not_stub(self):
        from services.legal_content_projection import _classify_article_text
        normal = "이 자료를 이용하여 주십시오. 해당 법령을 참고하시기 바랍니다."
        assert _classify_article_text(normal) == "ARTICLE_TEXT"

    def test_button_phrase_alone_without_menu_is_not_stub(self):
        from services.legal_content_projection import _classify_article_text
        normal = "버튼을 이용하십시오. 관련 정보를 확인하세요."
        assert _classify_article_text(normal) == "ARTICLE_TEXT"

    def test_menu_plus_button_is_stub(self):
        from services.legal_content_projection import _classify_article_text
        assert _classify_article_text(KC_STUB) == "SOURCE_UI_STUB"

    def test_menu_alone_without_button_is_not_stub(self):
        from services.legal_content_projection import _classify_article_text
        text = "상단 메뉴에서 관련 정보를 확인하시기 바랍니다. 이 조항은 일반 조항입니다."
        # No button phrase → not a stub
        assert _classify_article_text(text) == "ARTICLE_TEXT"


# ── PATCH-002: projection-aware search_text ──────────────────────────────────

class TestSearchTextFromProjection:
    """SEARCH_PROJ: search_text_from_projection uses resolved content."""

    TITLE = "전기용품안전관리법 제1조"
    BODY_45983 = "가" * 45983

    def test_search_att_body_includes_resolved_body(self):
        """SEARCH-ATT-BODY: KC real-shape → search_text includes 45,983-char body."""
        clean_att = {
            "id": "att-001",
            "attachment_title": "KC 62619 Ed 2.0",
            "download_status": "SUCCESS",
            "extraction_verdict": "CLEAN",
            "attachment_text": self.BODY_45983,
        }
        projection = resolve_legal_content(KC_STUB, [clean_att])
        assert projection["content_mode"] == "ATTACHMENT_BODY"
        result = search_text_from_projection(projection, self.TITLE)
        assert self.TITLE in result
        assert len(result) > len(self.TITLE) + 1000
        assert "상단 메뉴" not in result
        assert "버튼을 이용하십시오" not in result

    def test_search_att_index_includes_attachment_titles(self):
        """SEARCH-ATT-INDEX: multiple substantial → stub text absent + titles present."""
        atts = [
            {"id": "att-a", "attachment_title": "시험방법 A",
             "download_status": "SUCCESS", "extraction_verdict": "CLEAN",
             "attachment_text": "가" * 2000},
            {"id": "att-b", "attachment_title": "시험방법 B",
             "download_status": "SUCCESS", "extraction_verdict": "CLEAN",
             "attachment_text": "나" * 1500},
        ]
        projection = resolve_legal_content(KC_STUB, atts)
        assert projection["content_mode"] == "ATTACHMENT_INDEX"
        result = search_text_from_projection(projection, self.TITLE)
        assert "상단 메뉴" not in result
        assert "시험방법 A" in result
        assert "시험방법 B" in result

    def test_search_inline_src_removes_img_markup(self):
        """SEARCH-INLINE-SRC: <img src=...> and </img> removed, prose kept."""
        img_text = (
            '별표 1 <img src="http://www.law.go.kr/flDownload.do?flSeq=22909013" '
            'alt="img22909013"> 이하 기준을 따른다. </img>'
        )
        projection = resolve_legal_content(img_text)
        assert projection["content_mode"] == "INLINE_MEDIA"
        title = "건설기준 별표1"
        result = search_text_from_projection(projection, title)
        assert "<img" not in result
        assert "</img>" not in result
        assert "이하 기준을 따른다" in result

    def test_search_unresolved_is_title_only(self):
        projection = resolve_legal_content(KC_STUB, [])
        assert projection["content_mode"] == "SOURCE_CONTENT_UNRESOLVED"
        result = search_text_from_projection(projection, self.TITLE)
        assert result == self.TITLE

    def test_search_article_text_includes_body(self):
        projection = resolve_legal_content(NORMAL_TEXT)
        result = search_text_from_projection(projection, self.TITLE)
        assert self.TITLE in result
        assert NORMAL_TEXT in result


# ── PATCH-002: bounded attachment fetch ──────────────────────────────────────

class TestBoundedAttachmentFetch:
    """BOUNDED: _fetch_attachments_for_version fetches text for at most
    ATTACHMENT_CANDIDATE_BATCH_LIMIT candidates, not all 520."""

    def test_bounded_batch_limit_respected(self):
        """Given 520 SUCCESS+CLEAN metadata rows, Phase B text fetch is bounded."""
        from unittest.mock import MagicMock, call
        from routers.public_safety_search import (
            ATTACHMENT_CANDIDATE_BATCH_LIMIT,
            _fetch_attachments_for_version,
        )

        # Build 520 SUCCESS+CLEAN metadata rows (no attachment_text in Phase A)
        meta_rows = [
            {
                "id": f"att-{i:04d}",
                "attachment_title": f"첨부 {i}",
                "attachment_no": i,
                "download_status": "SUCCESS",
                "extraction_verdict": "CLEAN",
            }
            for i in range(520)
        ]

        phase_a_result = MagicMock()
        phase_a_result.data = meta_rows

        # Phase B: return substantial text for the bounded candidates
        phase_b_data = [
            {"id": f"att-{i:04d}", "attachment_text": "가" * 2000}
            for i in range(ATTACHMENT_CANDIDATE_BATCH_LIMIT)
        ]
        phase_b_result = MagicMock()
        phase_b_result.data = phase_b_data

        # Build Supabase mock that tracks which query is metadata vs text
        q_meta = MagicMock()
        for m in ("select", "eq", "order"):
            getattr(q_meta, m).return_value = q_meta
        q_meta.execute.return_value = phase_a_result

        q_text = MagicMock()
        for m in ("select", "in_"):
            getattr(q_text, m).return_value = q_text
        q_text.execute.return_value = phase_b_result

        call_count = {"meta": 0, "text": 0, "in_ids": []}

        def make_q_side_effect(select_str):
            if "attachment_text" in select_str:
                call_count["text"] += 1
                return q_text
            else:
                call_count["meta"] += 1
                return q_meta

        tbl = MagicMock()
        tbl.select.side_effect = make_q_side_effect

        client = MagicMock()
        client.table.return_value = tbl

        # Capture the .in_() call to verify bounded IDs
        captured_ids = []
        original_in = q_text.in_
        def capture_in(col, ids):
            captured_ids.extend(ids)
            return q_text
        q_text.in_ = capture_in

        result = _fetch_attachments_for_version(client, "ver-large-001")

        # Verify Phase A was called (metadata fetch)
        assert call_count["meta"] == 1, "Phase A metadata query must be called once"
        # Verify Phase B was called (text fetch)
        assert call_count["text"] == 1, "Phase B text query must be called once"
        # Verify Phase B is bounded
        assert len(captured_ids) <= ATTACHMENT_CANDIDATE_BATCH_LIMIT, (
            f"Phase B must fetch at most {ATTACHMENT_CANDIDATE_BATCH_LIMIT} texts, "
            f"not {len(captured_ids)}"
        )
        # Result has all 520 metadata rows (from Phase A)
        assert len(result) == 520

    def test_zero_candidates_skips_phase_b(self):
        """If no SUCCESS+CLEAN candidates, Phase B must not be called."""
        from unittest.mock import MagicMock
        from routers.public_safety_search import _fetch_attachments_for_version

        meta_rows = [
            {"id": "att-001", "attachment_title": "실패파일",
             "attachment_no": 1, "download_status": "FAILED", "extraction_verdict": None}
        ]
        phase_a_result = MagicMock()
        phase_a_result.data = meta_rows

        phase_b_called = {"count": 0}

        q = MagicMock()
        for m in ("select", "eq", "order", "in_"):
            getattr(q, m).return_value = q
        q.execute.return_value = phase_a_result

        def select_side(fields):
            if "attachment_text" in fields:
                phase_b_called["count"] += 1
            return q

        tbl = MagicMock()
        tbl.select.side_effect = select_side
        client = MagicMock()
        client.table.return_value = tbl

        _fetch_attachments_for_version(client, "ver-no-candidates")
        assert phase_b_called["count"] == 0, "Phase B must not run when no candidates"
