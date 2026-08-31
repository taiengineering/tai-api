"""tests/test_paid_result_product_v1.py — A01 ~ A15

PAID-DIAGNOSIS-VALUE-REBUILD-01 · STEP4C-2 PKG-2C
대상: services/paid_result_product_svc.py

이 층은 조립만 한다. 그래서 테스트가 확인하는 것도 두 가지뿐이다.

    1) 기존 Product Contract 가 한 글자도 달라지지 않았는가
    2) evidence 가 계약이 만든 materials 로부터, 주입된 loader 로만 붙었는가

조문 원문은 public.law_article 실측 발췌다(산업안전보건기준에 관한 규칙
제221조 계열 · 제338조). DB 는 부르지 않는다 — loader 는 전부 주입한다.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from services.paid_result_contract_svc import (
    CONTRACT_VERSION,
    build_paid_result_contract_v1,
)
from services.paid_result_evidence_svc import EVIDENCE_VERSION
from services.paid_result_product_svc import (
    EVIDENCE_KEY,
    MATERIALS_KEY,
    build_paid_result_product_v1,
)

LAW = "산업안전보건기준에 관한 규칙"
LAW_ID = "law-0001"

CONTRACT_KEYS = {
    "contract_version",
    "diagnosis",
    "diagnosis_profile",
    "paid_result_materials_v1",
}

# ─────────────────────────────────────────────────────────────────────────────
# 조문 원문 발췌 (public.law_article 실측)
# ─────────────────────────────────────────────────────────────────────────────

T221_3 = (
    "제221조의3(좌석안전띠의 착용)\n"
    "[①] ① 사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다.\n"
    "[②] ② 굴착기를 운전하는 사람은 좌석안전띠를 착용해야 한다."
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

EV_221_3 = "사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다."
EV_221_5 = "굴착기를 사용하여 화물 인양작업을 할 수 있다."
EV_338 = "토사등의 붕괴 또는 낙하에 의한 위험을 미리 방지하기 위하여"
EV_NONE = "이 문장은 어느 조문 원문에도 들어 있지 않다."


def article(
    row_id: str,
    article_no: int,
    text: str,
    *,
    sub_no: Any = None,
    sort: str = "",
    kind: str = "조문",
    title: str = "",
) -> Dict[str, Any]:
    return {
        "id": row_id,
        "law_id": LAW_ID,
        "law_version_id": "ver-1",
        "article_no": article_no,
        "article_sub_no": sub_no,
        "article_no_sort": sort,
        "article_type": kind,
        "article_title": title,
        "article_text": text,
        "enforcement_date": "2025-09-01",
        "article_status_code": "ACTIVE",
    }


ARTICLE_ROWS = [
    article("a-221-003", 221, T221_3, sub_no=3, sort="0221-003", title="좌석안전띠의 착용"),
    article("a-221-005", 221, T221_5, sub_no=5, sort="0221-005", title="인양작업 시 조치"),
    article("a-338-stub", 338, T338_STUB, sub_no=None, sort="0338-000", kind="전문"),
    article("a-338-000", 338, T338, sub_no=None, sort="0338-000", title="굴착작업 사전조사 등"),
]
LAW_ROWS = [{"id": LAW_ID, "law_name": LAW}]


# ─────────────────────────────────────────────────────────────────────────────
# 저장 row 픽스처 — 실제 컬럼 이름과 full_result 모양을 그대로 쓴다.
# ─────────────────────────────────────────────────────────────────────────────

def raw_obligation(law_article: str, evidence: str, *, atom: str, detail: str) -> Dict[str, Any]:
    return {
        "atom_id": atom,
        "law_name": LAW,
        "law_article": law_article,
        "evidence": evidence,
        "obligation_detail": detail,
        "check_result": "PASS",
        "applicability": {"engine_applicability": "APPLICABLE"},
        "triggered_by": ["excavation"],
        "source_atom_ids": [atom],
        "mapped_field": "has_excavation",
        "enrichment": {},
    }


def stored_row(obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": "row-0001",
        "public_token": "tok-should-never-leak",
        "created_at": "2026-08-11T01:25:02.786506+00:00",
        "tier_code": "PAID",
        "status": "COMPLETED",
        "engine_version": "leg-1",
        "rule_version": "rule-1",
        "paid_amount": 550000,
        "payment_ref": "pay-0001",
        "ci_hash": "ci-0001",
        "claimed_user_id": None,
        "auth_log_id": None,
        "input_data": {
            "company_name": "샘플 건설현장",
            "sector": "CONSTRUCTION",
            "workers": 86,
            "address": "경기도 화성시",
        },
        "full_result": {
            "obligations_raw": obligations,
            "facility_used": {"has_excavation": True},
        },
    }


DEFAULT_OBLIGATIONS = [
    raw_obligation("221", EV_221_5, atom="atom-1", detail="인양작업 시 조치"),
    raw_obligation("221", EV_221_3, atom="atom-2", detail="좌석안전띠 착용"),
    raw_obligation("338", EV_338, atom="atom-3", detail="굴착작업 사전조사"),
]

ROW = stored_row(DEFAULT_OBLIGATIONS)


class RecordingLoader:
    """호출을 기록하는 loader. 주입 여부와 왕복 횟수를 확인한다."""

    def __init__(self, laws=LAW_ROWS, articles=ARTICLE_ROWS) -> None:
        self._laws = laws
        self._articles = articles
        self.law_calls: List[Any] = []
        self.article_calls: List[Any] = []

    def load_laws(self, law_names):
        self.law_calls.append(list(law_names))
        return [r for r in self._laws if r["law_name"] in set(law_names)]

    def load_articles(self, law_ids, article_nos):
        self.article_calls.append((list(law_ids), list(article_nos)))
        ids, nos = set(law_ids), set(article_nos)
        return [a for a in self._articles if a["law_id"] in ids and a["article_no"] in nos]


def assembler_code() -> str:
    """assembler 의 '실행부' — 모듈 docstring 과 # 주석을 걷어낸 나머지.

    주석은 "무엇을 하지 않는다" 를 적는 자리다. 그 문장을 그대로 스캔하면
    규칙을 적었다는 이유로 규칙 위반이 된다. 그래서 문구를 바꾸는 대신
    검사 대상에서 주석을 뺀다.
    """
    import inspect

    import services.paid_result_product_svc as svc

    after_docstring = inspect.getsource(svc).split('"""')[-1]
    return "\n".join(
        line for line in after_docstring.splitlines()
        if not line.lstrip().startswith("#")
    )


class ExplodingLoader:
    """DB 가 죽은 상황."""

    class Boom(RuntimeError):
        pass

    def load_laws(self, law_names):
        raise ExplodingLoader.Boom("supabase unreachable")

    def load_articles(self, law_ids, article_nos):
        raise ExplodingLoader.Boom("supabase unreachable")


# ─────────────────────────────────────────────────────────────────────────────
# A01 ~ A04 — payload 모양
# ─────────────────────────────────────────────────────────────────────────────


def test_A01_top_level_keys_are_contract_four_plus_evidence_one():
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())

    assert set(product) == CONTRACT_KEYS | {EVIDENCE_KEY}
    assert len(product) == 5
    # 기존 4키가 그대로 있고, 이름이 바뀌거나 사라지지 않았다.
    for key in CONTRACT_KEYS:
        assert key in product


def test_A02_contract_part_is_exactly_the_base_contract():
    base = build_paid_result_contract_v1(ROW)
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())

    stripped = {k: v for k, v in product.items() if k != EVIDENCE_KEY}
    assert stripped == base

    # 세 조각 각각도 delta 0.
    assert product["diagnosis"] == base["diagnosis"]
    assert product["diagnosis_profile"] == base["diagnosis_profile"]
    assert product[MATERIALS_KEY] == base[MATERIALS_KEY]


def test_A03_contract_version_is_unchanged():
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    assert product["contract_version"] == CONTRACT_VERSION == 1


def test_A04_evidence_version_is_one():
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    assert product[EVIDENCE_KEY]["evidence_version"] == EVIDENCE_VERSION == 1


# ─────────────────────────────────────────────────────────────────────────────
# A05 / A12 — evidence 의 입력은 계약이 만든 materials 하나뿐
# ─────────────────────────────────────────────────────────────────────────────


def test_A05_resolver_input_is_exactly_contract_materials():
    seen: Dict[str, Any] = {}

    import services.paid_result_product_svc as svc

    real = svc.build_paid_result_evidence_v1

    def spy(materials, loader=None):
        seen["materials"] = materials
        return real(materials, loader=loader)

    svc.build_paid_result_evidence_v1 = spy
    try:
        product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    finally:
        svc.build_paid_result_evidence_v1 = real

    base = build_paid_result_contract_v1(ROW)
    assert seen["materials"] == base[MATERIALS_KEY]
    # 넘긴 객체가 payload 안의 그 객체와 같은 것이어야 한다 — 따로 만든 사본이 아니다.
    assert seen["materials"] is product[MATERIALS_KEY]


def test_A12_materializer_is_called_exactly_once():
    import services.paid_result_contract_svc as contract_svc

    calls = {"n": 0}
    real = contract_svc.build_paid_result_materials_v1

    def counting(full_result):
        calls["n"] += 1
        return real(full_result)

    contract_svc.build_paid_result_materials_v1 = counting
    try:
        build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    finally:
        contract_svc.build_paid_result_materials_v1 = real

    assert calls["n"] == 1, "Materializer 는 계약이 한 번 돌린다. assembler 가 다시 돌리지 않는다"


def test_A12_resolver_never_reads_full_result_directly():
    """row['full_result'] 를 지워도 evidence 는 계약의 materials 로 만들어진다."""
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    resolved = product[EVIDENCE_KEY]["resolution"]["resolved_obligation_count"]

    assert "full_result" not in assembler_code(), \
        "assembler 실행부가 full_result 를 직접 열지 않는다"
    assert resolved == 3


# ─────────────────────────────────────────────────────────────────────────────
# A06 ~ A08 — loader 주입 · 정상 attach · 부분 실패
# ─────────────────────────────────────────────────────────────────────────────


def test_A06_injected_loader_is_the_one_used():
    loader = RecordingLoader()
    build_paid_result_product_v1(ROW, evidence_loader=loader)

    assert loader.law_calls == [[LAW]]
    assert len(loader.article_calls) == 1
    law_ids, article_nos = loader.article_calls[0]
    assert law_ids == [LAW_ID]
    assert sorted(article_nos) == [221, 338]


def test_A07_resolved_articles_are_attached():
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    evidence = product[EVIDENCE_KEY]

    assert evidence["resolution"]["source_obligation_count"] == 3
    assert evidence["resolution"]["resolved_obligation_count"] == 3
    assert evidence["resolution"]["unresolved_obligation_count"] == 0
    assert evidence["resolution"]["precise_article_count"] == 3
    assert evidence["unresolved"] == []

    identity = [(a["article_no"], a["article_sub_no"]) for a in evidence["articles"]]
    assert identity == [(221, 3), (221, 5), (338, None)]
    # 전문 스텁이 아니라 조문 행이 붙었다.
    assert evidence["articles"][2]["article_title"] == "굴착작업 사전조사 등"
    # 조문 원문이 실제로 실린다.
    assert evidence["articles"][0]["article_text"].startswith("제221조의3(좌석안전띠의 착용)")


def test_A08_unresolved_obligation_still_produces_a_product():
    row = stored_row(DEFAULT_OBLIGATIONS + [
        raw_obligation("221", EV_NONE, atom="atom-4", detail="풀리지 않는 의무"),
        raw_obligation("제19조", EV_338, atom="atom-5", detail="숫자가 아닌 조문"),
    ])
    product = build_paid_result_product_v1(row, evidence_loader=RecordingLoader())

    assert set(product) == CONTRACT_KEYS | {EVIDENCE_KEY}
    evidence = product[EVIDENCE_KEY]
    assert evidence["resolution"]["source_obligation_count"] == 5
    assert evidence["resolution"]["resolved_obligation_count"] == 3
    assert evidence["resolution"]["unresolved_obligation_count"] == 2
    assert {u["reason"] for u in evidence["unresolved"]} == {
        "NO_EXACT_EVIDENCE_MATCH", "ARTICLE_NO_NOT_NUMERIC",
    }
    # 의무 자체는 계약에서 5건 그대로 살아 있다.
    assert len(product[MATERIALS_KEY]["normalized_obligations"]) == 5


# ─────────────────────────────────────────────────────────────────────────────
# A09 — DB 예외는 삼키지 않는다
# ─────────────────────────────────────────────────────────────────────────────


def test_A09_db_exception_propagates_and_is_not_swallowed():
    with pytest.raises(ExplodingLoader.Boom):
        build_paid_result_product_v1(ROW, evidence_loader=ExplodingLoader())


def test_A09_assembler_has_no_exception_handling_at_all():
    body = assembler_code()
    for banned in ["try:", "except", "contextlib.suppress", "finally:"]:
        assert banned not in body, f"예외를 삼킬 수 있는 구문: {banned}"


# ─────────────────────────────────────────────────────────────────────────────
# A10 / A11 — mutation 0
# ─────────────────────────────────────────────────────────────────────────────


def test_A10_row_is_not_mutated():
    row = copy.deepcopy(ROW)
    before = copy.deepcopy(row)
    build_paid_result_product_v1(row, evidence_loader=RecordingLoader())
    assert row == before


def test_A11_base_contract_is_not_mutated():
    base_before = build_paid_result_contract_v1(ROW)
    snapshot = copy.deepcopy(base_before)

    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())

    # 조립 뒤에도 계약을 따로 만들면 같은 값이 나온다.
    assert build_paid_result_contract_v1(ROW) == snapshot
    # 결과에서 evidence 를 떼면 그 값과 동일하다.
    assert {k: v for k, v in product.items() if k != EVIDENCE_KEY} == snapshot
    # 새 dict 이고 계약 객체를 덮어쓴 것이 아니다.
    assert product is not base_before


def test_deterministic_same_input_same_output():
    a = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    b = build_paid_result_product_v1(copy.deepcopy(ROW), evidence_loader=RecordingLoader())
    assert a == b


# ─────────────────────────────────────────────────────────────────────────────
# A13 ~ A15 — 신규 노출 0
# ─────────────────────────────────────────────────────────────────────────────


def test_A13_evidence_adds_no_new_identifier_exposure():
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    evidence_blob = repr(product[EVIDENCE_KEY])

    for token in [
        "public_token", "tok-should-never-leak",
        "result_id", "row-0001",
        "payment_ref", "pay-0001", "ci_hash", "ci-0001",
        "claimed_user_id", "auth_log_id", "input_data",
    ]:
        assert token not in evidence_blob, f"evidence 가 새로 노출: {token}"

    # 계약의 diagnosis 부분이 새 필드를 얻지도 않았다.
    base = build_paid_result_contract_v1(ROW)
    assert set(product["diagnosis"]) == set(base["diagnosis"])


def test_A14_no_precedent_anywhere_in_evidence():
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    blob = repr(product[EVIDENCE_KEY])
    for token in ["precedent", "판례", "case_number", "case_name", "court_name", "decision_date"]:
        assert token not in blob, token


def test_A15_no_official_url_anywhere_in_evidence():
    product = build_paid_result_product_v1(ROW, evidence_loader=RecordingLoader())
    blob = repr(product[EVIDENCE_KEY])
    for token in ["law.go.kr", "source_url", "http://", "https://"]:
        assert token not in blob, token

    # 링크 자리를 비워두지도 않는다 — 키 자체가 없다.
    for entry in product[EVIDENCE_KEY]["articles"]:
        assert set(entry) == {
            "law_name", "article_no", "article_sub_no", "article_no_sort",
            "article_title", "article_text", "enforcement_date",
            "related_obligation_refs", "provenance",
        }


def test_assembler_touches_no_public_surface():
    body = assembler_code()
    for banned in [
        "APIRouter", "@router", "FastAPI", "Depends", "requests.", "httpx",
        "supabase.table", "insert(", "update(", "delete(", "upsert(",
    ]:
        assert banned not in body, f"경계 위반: {banned}"
