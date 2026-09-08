"""WO-SHARED-LEGAL-TIME-NORMALIZER-V1-001 STEP 4B-4A (+PATCH-1) — N01~N32 + 실값 회귀 + static boundary + PATCH-1 negatives.

PURE module 단위테스트. DB/network/LLM 불필요.
"""
from __future__ import annotations

import copy
import inspect

from services.legal_time_normalizer import (
    VERSION,
    normalize_legal_time_text,
    normalize_obligation_legal_time,
)

N = normalize_legal_time_text


# ── RECURRING ──
def test_N01_every_15day():
    assert N("15일마다") == {"source_text": "15일마다", "status": "NORMALIZED",
                             "type": "RECURRING", "value": 15, "unit": "DAY", "operator": "EVERY"}


def test_N02_every_2month():
    r = N("2개월마다")
    assert (r["type"], r["value"], r["unit"], r["operator"]) == ("RECURRING", 2, "MONTH", "EVERY")


def test_N03_N04_year_once():
    for t in ("1년에 1회", "1년에 한번", "1년에 한 번"):
        r = N(t)
        assert (r["type"], r["value"], r["unit"], r["operator"]) == ("RECURRING", 1, "YEAR", "EVERY")
        assert r["source_text"] == t


def test_N05_maenyeon():
    r = N("매년")
    assert (r["type"], r["value"], r["unit"]) == ("RECURRING", 1, "YEAR")


def test_N06_maewol():
    r = N("매월")
    assert (r["type"], r["value"], r["unit"]) == ("RECURRING", 1, "MONTH")


def test_N07_quarter_once():
    r = N("분기 1회")
    assert (r["type"], r["value"], r["unit"]) == ("RECURRING", 1, "QUARTER")


def test_N08_half_year_once():
    r = N("반기 1회")
    assert (r["type"], r["value"], r["unit"]) == ("RECURRING", 1, "HALF_YEAR")


# ── EVENT_DEADLINE ──
def test_N09_basis_within():
    r = N("선임인원 교체 후 1개월 이내")
    assert r["type"] == "EVENT_DEADLINE"
    assert r["basis_text"] == "선임인원 교체"
    assert (r["value"], r["unit"], r["operator"]) == (1, "MONTH", "WITHIN")


def test_N10_within_no_basis():
    r = N("14일 이내")
    assert r["type"] == "EVENT_DEADLINE"
    assert (r["value"], r["unit"], r["operator"]) == (14, "DAY", "WITHIN")
    assert "basis_text" not in r


def test_N11_before_basis_no_numeric():
    r = N("작업 시작 전")
    assert r["type"] == "EVENT_DEADLINE"
    assert r["operator"] == "BEFORE"
    assert r["basis_text"] == "작업 시작"
    assert "value" not in r and "unit" not in r


def test_N12_before_variant_source_preserved():
    r = N("작업시작전(재시작포함)")
    assert r["type"] == "EVENT_DEADLINE" and r["operator"] == "BEFORE"
    assert r["source_text"] == "작업시작전(재시작포함)"
    assert "value" not in r and "unit" not in r


# ── CONTINUOUS / IMMEDIATE / ONE_TIME ──
def test_N13_continuous():
    r = N("상시")
    assert r == {"source_text": "상시", "status": "NORMALIZED", "type": "CONTINUOUS"}


def test_N14_continuous_variant():
    r = N("상시(설비운용시)")
    assert r["type"] == "CONTINUOUS"
    assert r["source_text"] == "상시(설비운용시)"
    assert "value" not in r and "unit" not in r


def test_N15_immediate():
    assert N("즉시")["type"] == "IMMEDIATE"
    assert N("즉시(...)")["type"] == "IMMEDIATE"


def test_N16_one_time():
    for t in ("최초 1회", "최초 1번", "최초 한 번"):
        assert N(t)["type"] == "ONE_TIME"


# ── RAW_ONLY ──
def test_N17_bare_year_raw_only():
    assert N("1년") == {"source_text": "1년", "status": "RAW_ONLY"}


def test_N18_bare_3month_raw_only():
    assert N("3개월")["status"] == "RAW_ONLY"


def test_N19_jeonggijeok_raw_only():
    assert N("정기적으로")["status"] == "RAW_ONLY"


def test_N20_susi_raw_only():
    assert N("수시")["status"] == "RAW_ONLY"


def test_N21_delegation_raw_only():
    assert N("시행규칙위임")["status"] == "RAW_ONLY"


def test_N22_quarter_hours_raw_only():
    assert N("분기 3시간") == {"source_text": "분기 3시간", "status": "RAW_ONLY"}
    assert N("분기3시간")["status"] == "RAW_ONLY"


def test_N23_twice_per_year_raw_only():
    assert N("연 2회")["status"] == "RAW_ONLY"
    assert N("월 2회")["status"] == "RAW_ONLY"
    assert N("주 3회")["status"] == "RAW_ONLY"


def test_N24_malformed_fail_close():
    for bad in (None, 123, [], {}, "", "   "):
        assert N(bad) is None


def test_N25_source_text_exact():
    for t in ("15일마다", "선임인원 교체 후 1개월 이내", "상시(설비운용시)", "1년", "분기 3시간"):
        assert N(t)["source_text"] == t


def test_N26_N27_N28_obligation_timing_cycle_independent():
    ob = {
        "obligation_detail": {"when": "작업 시작 전"},
        "enrichment": {"inspection_cycle": "1년에 1회"},
    }
    out = normalize_obligation_legal_time(ob)
    assert out["version"] == "v1"
    assert out["timing"]["type"] == "EVENT_DEADLINE"
    assert out["cycle"]["type"] == "RECURRING"
    assert out["timing"]["source_text"] == "작업 시작 전"
    assert out["cycle"]["source_text"] == "1년에 1회"


def test_N29_absent_not_null():
    out = normalize_obligation_legal_time({"enrichment": {"inspection_cycle": "매년"}})
    assert "cycle" in out and "timing" not in out
    assert normalize_obligation_legal_time({"obligation_detail": {}, "enrichment": {}}) is None
    assert normalize_obligation_legal_time({}) is None
    assert normalize_obligation_legal_time(None) is None


def test_N30_input_mutation_zero():
    ob = {"obligation_detail": {"when": "즉시"}, "enrichment": {"inspection_cycle": "상시"}}
    before = copy.deepcopy(ob)
    normalize_obligation_legal_time(ob)
    assert ob == before


def test_N31_deterministic():
    ob = {"obligation_detail": {"when": "선임인원 교체 후 1개월 이내"},
          "enrichment": {"inspection_cycle": "15일마다"}}
    first = normalize_obligation_legal_time(ob)
    for _ in range(100):
        assert normalize_obligation_legal_time(copy.deepcopy(ob)) == first


def test_N32_no_db_network_llm_dependency():
    import services.legal_time_normalizer as M
    src = inspect.getsource(M)
    for banned in ("supabase", "get_supabase", "requests", "http", "openai", "anthropic", "socket"):
        assert banned not in src


# ── 실측값 회귀 (fixture only) ──
def test_real_value_regression():
    cases = {
        "14일이내": ("EVENT_DEADLINE", "NORMALIZED"),
        "작업시작전(재시작포함)": ("EVENT_DEADLINE", "NORMALIZED"),
        "해당 작업 전": ("EVENT_DEADLINE", "NORMALIZED"),
        "상시(설비운용시)": ("CONTINUOUS", "NORMALIZED"),
        "매년": ("RECURRING", "NORMALIZED"),
        "즉시": ("IMMEDIATE", "NORMALIZED"),
        "정기적으로": (None, "RAW_ONLY"),
        "최초+정기+수시": (None, "RAW_ONLY"),
        "분기3시간": (None, "RAW_ONLY"),
    }
    for text, (typ, status) in cases.items():
        r = N(text)
        assert r["status"] == status, text
        assert r.get("type") == typ, text
        assert r["source_text"] == text


def test_within_no_basis_variants():
    r = N("14일이내")
    assert (r["type"], r["value"], r["unit"], r["operator"]) == ("EVENT_DEADLINE", 14, "DAY", "WITHIN")
    assert "basis_text" not in r


# ── PATCH-1: source_text EXACT (공백 보존) ──
def test_patch1_source_text_exact_with_whitespace():
    r = N("  15일마다  ")
    assert r["status"] == "NORMALIZED" and r["type"] == "RECURRING"
    assert r["value"] == 15 and r["unit"] == "DAY"
    assert r["source_text"] == "  15일마다  "   # 원문 EXACT(trim 안 함)
    # cycle 원문 공백도 보존
    out = normalize_obligation_legal_time({"enrichment": {"inspection_cycle": " 상시 "}})
    assert out["cycle"]["type"] == "CONTINUOUS"
    assert out["cycle"]["source_text"] == " 상시 "


# ── PATCH-1: CONTINUOUS/IMMEDIATE over-normalization 차단 ──
def test_patch1_continuous_immediate_compound_raw_only():
    assert N("상시 또는 필요시")["status"] == "RAW_ONLY"
    assert N("즉시 또는 14일 이내")["status"] == "RAW_ONLY"
    assert N("상시 점검")["status"] == "RAW_ONLY"
    assert N("즉시 보고 후 조치")["status"] == "RAW_ONLY"
    # 정확/괄호주석만 NORMALIZED 유지
    assert N("상시")["type"] == "CONTINUOUS"
    assert N("상시(설비운용시)")["type"] == "CONTINUOUS"
    assert N("즉시")["type"] == "IMMEDIATE"


# ── PATCH-1: WITHIN full-match (복합문 앞부분 있으면 RAW_ONLY) ──
def test_patch1_within_fullmatch_only():
    assert N("필요시 14일 이내")["status"] == "RAW_ONLY"    # 기준(후/부터) 없이 접두어만 → RAW_ONLY
    assert N("즉시 또는 14일 이내")["status"] == "RAW_ONLY"
    # 허용 형태
    assert N("14일 이내")["type"] == "EVENT_DEADLINE"
    assert N("설치 후 30일 이내")["basis_text"] == "설치"
    assert N("선임사유부터 14일 이내")["basis_text"] == "선임사유"


# ── PATCH-1: BEFORE 도 접속절 붙으면 RAW_ONLY ──
def test_patch1_before_compound_raw_only():
    assert N("작업 시작 전 또는 변경 시")["status"] == "RAW_ONLY"
    assert N("작업 시작 전")["type"] == "EVENT_DEADLINE"
    assert N("작업시작전(재시작포함)")["type"] == "EVENT_DEADLINE"


# ── static boundary: 공용 pure module 고정 ──
def test_static_boundary_pure_module():
    import services.legal_time_normalizer as M
    src = inspect.getsource(M)
    for banned in ("inspection_sets", "supabase", "db.", "routers.",
                   "openai", "anthropic", "rtm_engine", "law_engine", "CYCLE_CODE_MAP"):
        assert banned not in src
    assert VERSION == "v1"
