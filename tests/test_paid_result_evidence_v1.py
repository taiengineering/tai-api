"""tests/test_paid_result_evidence_v1.py — E01 ~ E17

PAID-DIAGNOSIS-VALUE-REBUILD-01 · STEP4C-2 PKG-2B
대상: services/paid_result_evidence_svc.py

픽스처의 조문 원문은 public.law_article 의 실제 저장값에서 가져온 발췌다
(산업안전보건기준에 관한 규칙 제221조 계열 · 제338조). 실데이터에서
제221조 · 제221조의2 · 의3 · 의4 · 의5 가 전부 article_no = 221 로 모이고
제338조에 '전문' 스텁이 함께 있다는 사실 자체가 이 PKG 가 푸는 문제다.

테스트는 DB 를 부르지 않는다. loader 는 전부 주입한다.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from services.paid_result_evidence_svc import (
    ARTICLE_STATUS_DELETED,
    ARTICLE_TYPE_REQUIRED,
    EVIDENCE_VERSION,
    MATCH_RULE,
    RESOLUTION_RULE,
    build_lookup_requests,
    build_paid_result_evidence_v1,
    is_candidate_row,
    normalize_text,
    parse_base_article_no,
    resolve_articles,
)

LAW = "산업안전보건기준에 관한 규칙"
LAW_ID = "law-0001"

# ─────────────────────────────────────────────────────────────────────────────
# 조문 원문 발췌 (public.law_article 실측)
# ─────────────────────────────────────────────────────────────────────────────

T221 = (
    "제221조(가스배관 등의 손상 방지) 사업주는 항타기를 사용하여 작업할 때에 "
    "가스배관, 지중전선로 및 그 밖의 지하공작물의 손상으로 근로자가 위험에 처할 "
    "우려가 있는 경우에는 미리 작업장소에 가스배관 등을 조사하여야 한다."
)
T221_2_STUB = "제3관 굴착기 <신설 2022.10.18>"
T221_2 = (
    "제221조의2(충돌위험 방지조치)\n"
    "[①] ① 사업주는 굴착기에 사람이 부딪히는 것을 방지하기 위해 후사경과 "
    "후방영상표시장치 등 굴착기를 운전하는 사람이 좌우 및 후방을 확인할 수 있는 "
    "장치를 굴착기에 갖춰야 한다."
)
T221_3 = (
    "제221조의3(좌석안전띠의 착용)\n"
    "[①] ① 사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다.\n"
    "[②] ② 굴착기를 운전하는 사람은 좌석안전띠를 착용해야 한다."
)
T221_4 = (
    "제221조의4(잠금장치의 체결) 사업주는 굴착기 퀵커플러(quick coupler)에 버킷, "
    "브레이커(breaker), 크램셸(clamshell) 등 작업장치를 장착 또는 해체하는 경우에는 "
    "잠금장치를 체결하고 이를 확인해야 한다."
)
T221_5 = (
    "제221조의5(인양작업 시 조치)\n"
    "[①] ① 사업주는 다음 각 호의 사항을 모두 갖춘 굴착기의 경우에는 굴착기를 "
    "사용하여 화물 인양작업을 할 수 있다."
)
T338_STUB = "제2절 굴착작업 등의 위험 방지"
T338 = (
    "제338조(굴착작업 사전조사 등) 사업주는 굴착작업을 할 때에 토사등의 붕괴 또는 "
    "낙하에 의한 위험을 미리 방지하기 위하여 다음 각 호의 사항을 점검해야 한다."
)

# ─────────────────────────────────────────────────────────────────────────────
# 픽스처 helper
# ─────────────────────────────────────────────────────────────────────────────


def article(
    row_id: str,
    article_no: int,
    text: str,
    *,
    sub_no: Any = None,
    sort: str = "",
    kind: str = ARTICLE_TYPE_REQUIRED,
    title: str = "",
    law_id: str = LAW_ID,
    status: str = "ACTIVE",
    version_id: str = "ver-1",
    enforcement_date: str = "2025-09-01",
) -> Dict[str, Any]:
    return {
        "id": row_id,
        "law_id": law_id,
        "law_version_id": version_id,
        "article_no": article_no,
        "article_sub_no": sub_no,
        "article_no_sort": sort,
        "article_type": kind,
        "article_title": title,
        "article_text": text,
        "enforcement_date": enforcement_date,
        "article_status_code": status,
    }


#: 실데이터와 같은 모양: article_no = 221 에 조문 5행 + 전문 스텁 1행.
ARTICLES_221 = [
    article("a-221-000", 221, T221, sub_no=None, sort="0221-000", title="가스배관 등의 손상 방지"),
    article("a-221-002s", 221, T221_2_STUB, sub_no=2, sort="0221-002", kind="전문"),
    article("a-221-002", 221, T221_2, sub_no=2, sort="0221-002", title="충돌위험 방지조치"),
    article("a-221-003", 221, T221_3, sub_no=3, sort="0221-003", title="좌석안전띠의 착용"),
    article("a-221-004", 221, T221_4, sub_no=4, sort="0221-004", title="잠금장치의 체결"),
    article("a-221-005", 221, T221_5, sub_no=5, sort="0221-005", title="인양작업 시 조치"),
]

ARTICLES_338 = [
    article("a-338-stub", 338, T338_STUB, sub_no=None, sort="0338-000", kind="전문"),
    article("a-338-000", 338, T338, sub_no=None, sort="0338-000", title="굴착작업 사전조사 등"),
]

LAWS = [{"id": LAW_ID, "law_name": LAW}]


def obligation(ref: int, law_article: Any, evidence: Any, *, law_name: str = LAW, what: str = "") -> Dict[str, Any]:
    return {
        "identity": {"source_index": ref},
        "duty": {"what": what},
        "legal": {"law_name": law_name, "law_article": law_article, "evidence": evidence},
    }


class RecordingLoader:
    """호출 횟수를 세는 loader. DB 왕복이 2회인지 확인하기 위해 존재한다."""

    def __init__(self, law_rows: List[Dict[str, Any]], article_rows: List[Dict[str, Any]]) -> None:
        self.law_rows = law_rows
        self.article_rows = article_rows
        self.law_calls: List[Any] = []
        self.article_calls: List[Any] = []

    def load_laws(self, law_names):
        self.law_calls.append(list(law_names))
        return [row for row in self.law_rows if row["law_name"] in set(law_names)]

    def load_articles(self, law_ids, article_nos):
        self.article_calls.append((list(law_ids), list(article_nos)))
        ids = set(law_ids)
        nos = set(article_nos)
        return [r for r in self.article_rows if r["law_id"] in ids and r["article_no"] in nos]


def only(result: Dict[str, Any]) -> Dict[str, Any]:
    assert len(result["articles"]) == 1, result["articles"]
    return result["articles"][0]


# ─────────────────────────────────────────────────────────────────────────────
# E01 — 후보 1개 + exact evidence
# ─────────────────────────────────────────────────────────────────────────────


def test_E01_single_candidate_exact_evidence_resolves():
    obligations = [obligation(0, "338", "사업주는 굴착작업을 할 때에 토사등의 붕괴 또는 낙하에 의한 위험을")]
    result = resolve_articles(obligations, LAWS, ARTICLES_338)

    assert result["evidence_version"] == EVIDENCE_VERSION
    assert result["resolution"]["rule"] == RESOLUTION_RULE
    assert result["resolution"]["source_obligation_count"] == 1
    assert result["resolution"]["resolved_obligation_count"] == 1
    assert result["resolution"]["unresolved_obligation_count"] == 0
    assert result["resolution"]["precise_article_count"] == 1
    assert result["unresolved"] == []

    row = only(result)
    assert row["law_name"] == LAW
    assert row["article_no"] == 338
    assert row["article_sub_no"] is None
    assert row["article_title"] == "굴착작업 사전조사 등"
    assert row["related_obligation_refs"] == [0]
    assert row["provenance"]["law_article_id"] == "a-338-000"
    assert row["provenance"]["match_rule"] == MATCH_RULE
    assert row["provenance"]["source_table"] == "public.law_article"


# ─────────────────────────────────────────────────────────────────────────────
# E02 / E03 — 제221조 후보 5개에서 의5 · 의3 을 각각 분리한다
# ─────────────────────────────────────────────────────────────────────────────


def test_E02_221_inyang_resolves_to_sub_no_5_only():
    evidence = "사업주는 다음 각 호의 사항을 모두 갖춘 굴착기의 경우에는 굴착기를 사용하여 화물 인양작업을 할 수 있다."
    result = resolve_articles([obligation(0, "221", evidence)], LAWS, ARTICLES_221)

    row = only(result)
    assert row["article_no"] == 221
    assert row["article_sub_no"] == 5
    assert row["article_no_sort"] == "0221-005"
    assert row["article_title"] == "인양작업 시 조치"
    assert result["unresolved"] == []


def test_E03_221_seatbelt_resolves_to_sub_no_3_only():
    evidence = "사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다."
    result = resolve_articles([obligation(0, "221", evidence)], LAWS, ARTICLES_221)

    row = only(result)
    assert row["article_sub_no"] == 3
    assert row["article_no_sort"] == "0221-003"
    assert row["article_title"] == "좌석안전띠의 착용"


def test_E02_E03_together_produce_two_distinct_articles():
    """같은 article_no 221 인데 서로 다른 조문 행으로 갈라진다 — 이 PKG 의 핵심."""
    obligations = [
        obligation(0, "221", "굴착기를 사용하여 화물 인양작업을 할 수 있다."),
        obligation(1, "221", "굴착기를 운전하는 사람은 좌석안전띠를 착용해야 한다."),
        obligation(2, "221", "굴착기에 사람이 부딪히는 것을 방지하기 위해 후사경과"),
        obligation(3, "221", "굴착기 퀵커플러(quick coupler)에 버킷"),
    ]
    result = resolve_articles(obligations, LAWS, ARTICLES_221)

    assert result["resolution"]["precise_article_count"] == 4
    assert result["resolution"]["resolved_obligation_count"] == 4
    assert result["unresolved"] == []
    assert [a["article_sub_no"] for a in result["articles"]] == [2, 3, 4, 5]


# ─────────────────────────────────────────────────────────────────────────────
# E04 / E14 — '전문' 스텁 제외
# ─────────────────────────────────────────────────────────────────────────────


def test_E04_338_professional_stub_excluded():
    result = resolve_articles(
        [obligation(0, "338", "토사등의 붕괴 또는 낙하에 의한 위험을 미리 방지하기 위하여")],
        LAWS,
        ARTICLES_338,
    )
    row = only(result)
    assert row["provenance"]["law_article_id"] == "a-338-000"
    assert row["article_title"] == "굴착작업 사전조사 등"


def test_E14_professional_row_is_never_a_candidate():
    # 전문 스텁 본문과 정확히 일치하는 evidence 여도 후보가 아니므로 풀리지 않는다.
    result = resolve_articles([obligation(0, "338", T338_STUB)], LAWS, [ARTICLES_338[0]])
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "NO_EXACT_EVIDENCE_MATCH"

    assert is_candidate_row(ARTICLES_338[1]) is True
    assert is_candidate_row(ARTICLES_338[0]) is False
    assert is_candidate_row(ARTICLES_221[1]) is False  # 221 의2 전문 스텁


# ─────────────────────────────────────────────────────────────────────────────
# E05 / E06 — fail closed
# ─────────────────────────────────────────────────────────────────────────────


def test_E05_zero_exact_match_is_unresolved():
    result = resolve_articles(
        [obligation(0, "221", "이 문장은 어느 조문 원문에도 들어 있지 않다.")], LAWS, ARTICLES_221
    )
    assert result["articles"] == []
    assert result["resolution"]["resolved_obligation_count"] == 0
    assert result["resolution"]["unresolved_obligation_count"] == 1
    assert result["unresolved"] == [{
        "obligation_ref": 0,
        "law_name": LAW,
        "law_article": "221",
        "reason": "NO_EXACT_EVIDENCE_MATCH",
    }]


def test_E06_two_exact_matches_is_unresolved_and_selects_nothing():
    shared = "사업주는 안전조치를 하여야 한다."
    rows = [
        article("dup-a", 900, f"제900조(가) {shared}", sub_no=None, sort="0900-000"),
        article("dup-b", 900, f"제900조의2(나) {shared}", sub_no=2, sort="0900-002"),
    ]
    result = resolve_articles([obligation(0, "900", shared)], LAWS, rows)

    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "MULTIPLE_EXACT_EVIDENCE_MATCHES"
    # 임의 선택 0 — 어느 행도 결과에 들어가지 않는다.
    assert result["resolution"]["precise_article_count"] == 0
    assert result["resolution"]["resolved_obligation_count"] == 0


def test_E06_multiple_match_does_not_prefer_latest_or_lowest_sub_no():
    shared = "사업주는 안전조치를 하여야 한다."
    rows = [
        article("dup-old", 900, f"제900조 {shared}", sub_no=None, sort="0900-000",
                enforcement_date="2020-01-01"),
        article("dup-new", 900, f"제900조의9 {shared}", sub_no=9, sort="0900-009",
                enforcement_date="2025-09-01"),
    ]
    result = resolve_articles([obligation(0, "900", shared)], LAWS, rows)
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "MULTIPLE_EXACT_EVIDENCE_MATCHES"


# ─────────────────────────────────────────────────────────────────────────────
# E07 — law_name 은 exact 만
# ─────────────────────────────────────────────────────────────────────────────


def test_E07_law_name_exact_only_no_ilike_fallback():
    # 저장된 법령명이 다르면(부분 문자열이어도) 풀리지 않는다.
    result = resolve_articles(
        [obligation(0, "338", "굴착작업을 할 때에", law_name="산업안전보건법")],
        LAWS,
        ARTICLES_338,
    )
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "LAW_NOT_FOUND"


def test_E07_duplicate_exact_law_name_is_ambiguous():
    laws = [{"id": "law-a", "law_name": LAW}, {"id": "law-b", "law_name": LAW}]
    result = resolve_articles([obligation(0, "338", "굴착작업을 할 때에")], laws, ARTICLES_338)
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "LAW_NAME_AMBIGUOUS"


def test_E07_loader_receives_exact_names_only():
    loader = RecordingLoader(LAWS, ARTICLES_338)
    build_paid_result_evidence_v1(
        {"normalized_obligations": [obligation(0, "338", "굴착작업을 할 때에")]}, loader=loader
    )
    assert loader.law_calls == [[LAW]]


# ─────────────────────────────────────────────────────────────────────────────
# E08 / E09 / E10 — 매칭 규칙의 경계
# ─────────────────────────────────────────────────────────────────────────────


def test_E08_whitespace_differences_still_match():
    evidence = "사업주는  굴착기를\n운전하는   사람이 좌석안전띠를\t착용하도록 해야 한다."
    result = resolve_articles([obligation(0, "221", evidence)], LAWS, ARTICLES_221)
    assert only(result)["article_sub_no"] == 3

    assert normalize_text("  a \n b\t\tc ") == "a b c"
    assert normalize_text("   ") is None
    assert normalize_text(None) is None


def test_E09_punctuation_or_semantic_similarity_does_not_match():
    # 쉼표 하나가 더 들어간 문장 — 의미는 같아도 문자열은 다르다.
    comma = "사업주는 굴착기를 운전하는 사람이, 좌석안전띠를 착용하도록 해야 한다."
    result = resolve_articles([obligation(0, "221", comma)], LAWS, ARTICLES_221)
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "NO_EXACT_EVIDENCE_MATCH"

    # 공백을 지운 형태도 매칭하지 않는다. 정규화는 공백을 '합칠' 뿐 '지우지' 않는다.
    squeezed = "사업주는굴착기를운전하는사람이좌석안전띠를착용하도록해야한다."
    squeezed_result = resolve_articles([obligation(0, "221", squeezed)], LAWS, ARTICLES_221)
    assert squeezed_result["articles"] == []

    # 동의어 치환도 매칭하지 않는다.
    synonym = "사업주는 굴착기를 조종하는 사람이 좌석안전띠를 착용하도록 해야 한다."
    synonym_result = resolve_articles([obligation(0, "221", synonym)], LAWS, ARTICLES_221)
    assert synonym_result["articles"] == []


def test_E10_duty_what_is_never_used_as_fallback():
    result = resolve_articles(
        [obligation(
            0, "221",
            "이 문장은 조문 원문에 없다.",
            what="사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다.",
        )],
        LAWS,
        ARTICLES_221,
    )
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "NO_EXACT_EVIDENCE_MATCH"

    # build_lookup_requests 는 duty 를 아예 읽지 않는다.
    request = build_lookup_requests([obligation(0, "221", "x", what="y")])[0]
    assert set(request) == {
        "obligation_ref", "law_name", "base_article_no", "raw_law_article", "evidence"
    }


# ─────────────────────────────────────────────────────────────────────────────
# E11 / E12 — grouping · ordering
# ─────────────────────────────────────────────────────────────────────────────


def test_E11_two_obligations_on_same_article_group_into_one_entry():
    obligations = [
        obligation(0, "221", "사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다."),
        obligation(1, "221", "굴착기를 운전하는 사람은 좌석안전띠를 착용해야 한다."),
    ]
    result = resolve_articles(obligations, LAWS, ARTICLES_221)

    assert result["resolution"]["precise_article_count"] == 1
    assert result["resolution"]["resolved_obligation_count"] == 2
    row = only(result)
    assert row["related_obligation_refs"] == [0, 1]
    # article_text 는 한 번만 실린다.
    assert sum(1 for a in result["articles"] if a["article_text"] == row["article_text"]) == 1


def test_E12_ordering_is_stable_and_input_order_independent():
    forward = [
        obligation(0, "221", "굴착기를 사용하여 화물 인양작업을 할 수 있다."),
        obligation(1, "221", "굴착기를 운전하는 사람은 좌석안전띠를 착용해야 한다."),
        obligation(2, "338", "굴착작업을 할 때에 토사등의 붕괴"),
        obligation(3, "221", "굴착기에 사람이 부딪히는 것을 방지하기 위해"),
    ]
    rows = ARTICLES_221 + ARTICLES_338
    a = resolve_articles(forward, LAWS, rows)
    b = resolve_articles(list(reversed(forward)), LAWS, list(reversed(rows)))

    order = [x["article_no_sort"] for x in a["articles"]]
    assert order == ["0221-002", "0221-003", "0221-005", "0338-000"]
    assert order == [x["article_no_sort"] for x in b["articles"]]
    assert a["articles"] == b["articles"]


# ─────────────────────────────────────────────────────────────────────────────
# E13 / E15 — 후보 자격 · 입력 형식
# ─────────────────────────────────────────────────────────────────────────────


def test_E13_deleted_candidate_is_excluded():
    rows = [
        article("del", 338, T338, sub_no=None, sort="0338-000", status=ARTICLE_STATUS_DELETED),
    ]
    result = resolve_articles([obligation(0, "338", "굴착작업을 할 때에")], LAWS, rows)
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "NO_EXACT_EVIDENCE_MATCH"
    assert is_candidate_row(rows[0]) is False


@pytest.mark.parametrize(
    "raw", ["제19조", "19의2", "19-2", "", "  ", None, "가", "19조", 19.5, True],
)
def test_E15_non_numeric_law_article_is_unresolved(raw):
    assert parse_base_article_no(raw) is None
    result = resolve_articles([obligation(0, raw, "굴착작업을 할 때에")], LAWS, ARTICLES_338)
    assert result["articles"] == []
    assert result["unresolved"][0]["reason"] == "ARTICLE_NO_NOT_NUMERIC"


def test_E15_numeric_forms_that_are_accepted():
    assert parse_base_article_no("221") == 221
    assert parse_base_article_no(" 221 ") == 221
    assert parse_base_article_no(221) == 221
    assert parse_base_article_no("0221") == 221


def test_missing_law_name_or_evidence_is_unresolved():
    a = resolve_articles([obligation(0, "338", None)], LAWS, ARTICLES_338)
    assert a["unresolved"][0]["reason"] == "EVIDENCE_MISSING"
    b = resolve_articles([obligation(0, "338", "굴착작업", law_name="")], LAWS, ARTICLES_338)
    assert b["unresolved"][0]["reason"] == "LAW_NAME_MISSING"


# ─────────────────────────────────────────────────────────────────────────────
# E16 / E17 — 부작용 · 왕복 횟수
# ─────────────────────────────────────────────────────────────────────────────


def test_E16_input_is_not_mutated():
    materials = {
        "normalized_obligations": [
            obligation(0, "221", "굴착기를 사용하여 화물 인양작업을 할 수 있다."),
            obligation(1, "338", "굴착작업을 할 때에 토사등의 붕괴"),
            obligation(2, "제19조", "풀리지 않는 입력"),
        ]
    }
    before = copy.deepcopy(materials)
    laws_before = copy.deepcopy(LAWS)
    rows_before = copy.deepcopy(ARTICLES_221 + ARTICLES_338)

    build_paid_result_evidence_v1(
        materials, loader=RecordingLoader(LAWS, ARTICLES_221 + ARTICLES_338)
    )
    resolve_articles(materials["normalized_obligations"], LAWS, ARTICLES_221 + ARTICLES_338)

    assert materials == before
    assert LAWS == laws_before
    assert ARTICLES_221 + ARTICLES_338 == rows_before


def test_E17_db_roundtrips_are_exactly_two_regardless_of_obligation_count():
    obligations = []
    evidences = [
        "굴착기를 사용하여 화물 인양작업을 할 수 있다.",
        "굴착기를 운전하는 사람은 좌석안전띠를 착용해야 한다.",
        "굴착기에 사람이 부딪히는 것을 방지하기 위해",
        "굴착기 퀵커플러(quick coupler)에 버킷",
        "굴착작업을 할 때에 토사등의 붕괴",
    ]
    for i in range(25):
        law_article = "338" if i % 5 == 4 else "221"
        obligations.append(obligation(i, law_article, evidences[i % 5]))

    loader = RecordingLoader(LAWS, ARTICLES_221 + ARTICLES_338)
    result = build_paid_result_evidence_v1({"normalized_obligations": obligations}, loader=loader)

    assert len(loader.law_calls) == 1, "law_master 질의는 1회"
    assert len(loader.article_calls) == 1, "law_article 질의는 1회 — 조문마다 부르지 않는다"
    law_ids, article_nos = loader.article_calls[0]
    assert law_ids == [LAW_ID]
    assert sorted(article_nos) == [221, 338]

    assert result["resolution"]["source_obligation_count"] == 25
    assert result["resolution"]["resolved_obligation_count"] == 25
    assert result["resolution"]["unresolved_obligation_count"] == 0
    assert result["resolution"]["precise_article_count"] == 5


def test_entrypoint_handles_empty_and_malformed_materials_without_db():
    class Exploding:
        def load_laws(self, *_):
            raise AssertionError("호출되면 안 된다")

        def load_articles(self, *_):
            raise AssertionError("호출되면 안 된다")

    for materials in [None, {}, {"normalized_obligations": None}, {"normalized_obligations": []}]:
        result = build_paid_result_evidence_v1(materials, loader=Exploding())
        assert result["articles"] == []
        assert result["unresolved"] == []
        assert result["resolution"]["source_obligation_count"] == 0
        assert result["resolution"]["precise_article_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 경계 — 이번 PKG 가 만들지 않는 것
# ─────────────────────────────────────────────────────────────────────────────


def test_output_carries_no_precedent_and_no_official_url():
    obligations = [obligation(0, "221", "굴착기를 사용하여 화물 인양작업을 할 수 있다.")]
    result = resolve_articles(obligations, LAWS, ARTICLES_221)

    blob = repr(result)
    for banned in ["law.go.kr", "precedent", "판례", "source_url", "case_number", "case_name"]:
        assert banned not in blob, banned

    assert set(result) == {"evidence_version", "resolution", "articles", "unresolved"}
    assert set(result["articles"][0]) == {
        "law_name", "article_no", "article_sub_no", "article_no_sort",
        "article_title", "article_text", "enforcement_date",
        "related_obligation_refs", "provenance",
    }


def test_service_module_makes_no_korean_article_label():
    """'제221조의5' 같은 표기는 backend 가 만들지 않는다 — 구조만 넘긴다."""
    import inspect

    import services.paid_result_evidence_svc as svc

    source = inspect.getsource(svc)
    body = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    # docstring 을 걷어낸 실행부에 조문 표기 문자열 리터럴이 없어야 한다.
    for banned in ["제{", "조의", "f\"제", "'제"]:
        assert banned not in body.split('"""')[-1], banned
