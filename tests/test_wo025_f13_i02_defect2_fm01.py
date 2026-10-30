"""WO025-F13-I02-DEFECT2 FM01 구현 검증 테스트.

I02_DEFECT2_TEST_MATRIX_R4.md (R5 기준) — 45 명명 케이스, 48 평가 포인트.
T37b = Gate 8 (운영 DB 적용 후) → 이 단계에서 SKIP.

FM01 = has_scaffold_at_ge_2m_subject_to_art56
APPROVED_SUBJECT_KINDS: STEEL_PIPE_SCAFFOLD, STEEL_FRAME_SCAFFOLD,
  MOBILE_SCAFFOLD, SYSTEM_SCAFFOLD, LOG
CONDITIONAL_HOLD: LEANING_SCAFFOLD, HOOK_SCAFFOLD
EXCLUDED: SUSPENDED_GONDOLA_SCAFFOLD, WORK_CHAIR_SUSPENDED_SCAFFOLD,
  HANGING_SCAFFOLD, HORSE_TRESTLE_SCAFFOLD
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from schemas.legal_engine import DiagnoseStep1Body
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.work_source.merge import merge_or_raise
from services.work_source.projector import project_work_rows

FM01 = "has_scaffold_at_ge_2m_subject_to_art56"


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _scaffold_row(
    kind: Optional[str] = None,
    height_m: Any = None,
    active: bool = True,
    subtype: Optional[str] = None,
) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    if kind is not None:
        attrs["scaffold_kind"] = kind
    if height_m is not None:
        attrs["height_m"] = height_m
    return {
        "work_type": "SCAFFOLD",
        "work_subtype": subtype,
        "attributes": attrs,
        "active": active,
    }


def _step1(sector: str = "CONSTRUCTION", fm01_in_input: bool = False, tsp: Any = None) -> DiagnoseStep1Body:
    inp: Dict[str, Any] = {}
    if fm01_in_input:
        inp[FM01] = True
    body = DiagnoseStep1Body(sector=sector, input=inp)
    body._tsp = tsp
    return body


# ─────────────────────────────────────────────────────────────────────────────
# T01~T07: 화이트리스트 종류별 기본 발행
# ─────────────────────────────────────────────────────────────────────────────

def test_T01_steel_pipe_scaffold_ge2m_fm01_true():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5)])
    assert out.get(FM01) is True


def test_T02_steel_pipe_scaffold_lt2m_fm01_absent():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=1.9)])
    assert FM01 not in out


def test_T03_steel_pipe_scaffold_exactly_2m_fm01_true():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.0)])
    assert out.get(FM01) is True


def test_T04_steel_frame_scaffold_ge2m_fm01_true():
    out = project_work_rows([_scaffold_row("STEEL_FRAME_SCAFFOLD", height_m=2.5)])
    assert out.get(FM01) is True


def test_T05_mobile_scaffold_ge2m_fm01_true():
    out = project_work_rows([_scaffold_row("MOBILE_SCAFFOLD", height_m=3.0)])
    assert out.get(FM01) is True


def test_T06_system_scaffold_ge2m_fm01_true():
    out = project_work_rows([_scaffold_row("SYSTEM_SCAFFOLD", height_m=2.0)])
    assert out.get(FM01) is True


def test_T07_log_scaffold_ge2m_fm01_true():
    out = project_work_rows([_scaffold_row("LOG", height_m=2.5)])
    assert out.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T08~T09: CONDITIONAL_HOLD 종류 — 미발행
# ─────────────────────────────────────────────────────────────────────────────

def test_T08_leaning_scaffold_conditional_hold_fm01_absent():
    out = project_work_rows([_scaffold_row("LEANING_SCAFFOLD", height_m=3.0)])
    assert FM01 not in out


def test_T09_hook_scaffold_conditional_hold_fm01_absent():
    out = project_work_rows([_scaffold_row("HOOK_SCAFFOLD", height_m=3.0)])
    assert FM01 not in out


# ─────────────────────────────────────────────────────────────────────────────
# T10~T13: 제외 비계 종류 — 항상 미발행
# ─────────────────────────────────────────────────────────────────────────────

def test_T10_suspended_gondola_scaffold_excluded_fm01_absent():
    out = project_work_rows([_scaffold_row("SUSPENDED_GONDOLA_SCAFFOLD", height_m=3.0)])
    assert FM01 not in out


def test_T11_work_chair_suspended_scaffold_excluded_fm01_absent():
    out = project_work_rows([_scaffold_row("WORK_CHAIR_SUSPENDED_SCAFFOLD", height_m=3.0)])
    assert FM01 not in out


def test_T12_hanging_scaffold_excluded_fm01_absent():
    out = project_work_rows([_scaffold_row("HANGING_SCAFFOLD", height_m=3.0)])
    assert FM01 not in out


def test_T13_horse_trestle_scaffold_excluded_fm01_absent():
    out = project_work_rows([_scaffold_row("HORSE_TRESTLE_SCAFFOLD", height_m=3.0)])
    assert FM01 not in out


# ─────────────────────────────────────────────────────────────────────────────
# T14~T17: 높이 유효성 — fail-closed
# ─────────────────────────────────────────────────────────────────────────────

def test_T14_steel_pipe_scaffold_height_missing_fm01_absent():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD")])
    assert FM01 not in out


def test_T15_steel_pipe_scaffold_height_zero_fm01_absent():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=0)])
    assert FM01 not in out


def test_T16_steel_pipe_scaffold_height_negative_fm01_absent():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=-1)])
    assert FM01 not in out


def test_T17_steel_pipe_scaffold_height_bool_excluded():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=True)])
    assert FM01 not in out


# ─────────────────────────────────────────────────────────────────────────────
# T18: any-TRUE 집계 (서브케이스 A~D = 4 평가 포인트)
# ─────────────────────────────────────────────────────────────────────────────

def test_T18A_approved_plus_hold_any_true():
    rows = [
        _scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5),
        _scaffold_row("LEANING_SCAFFOLD", height_m=3.0),
    ]
    out = project_work_rows(rows)
    assert out.get(FM01) is True


def test_T18B_only_hold_rows_fm01_absent():
    rows = [
        _scaffold_row("LEANING_SCAFFOLD", height_m=3.0),
        _scaffold_row("HOOK_SCAFFOLD", height_m=5.0),
    ]
    out = project_work_rows(rows)
    assert FM01 not in out


def test_T18C_two_approved_rows_any_true():
    rows = [
        _scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5),
        _scaffold_row("STEEL_FRAME_SCAFFOLD", height_m=2.5),
    ]
    out = project_work_rows(rows)
    assert out.get(FM01) is True


def test_T18D_two_approved_rows_both_lt2m_fm01_absent():
    rows = [
        _scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=1.5),
        _scaffold_row("STEEL_FRAME_SCAFFOLD", height_m=1.5),
    ]
    out = project_work_rows(rows)
    assert FM01 not in out


# ─────────────────────────────────────────────────────────────────────────────
# T19~T23b: 빈 입력 및 None 처리
# ─────────────────────────────────────────────────────────────────────────────

def test_T19_empty_rows_fm01_absent():
    out = project_work_rows([])
    assert FM01 not in out


def test_T20_no_scaffold_rows_fm01_absent():
    rows = [{"work_type": "FORKLIFT", "work_subtype": None, "attributes": {}, "active": True}]
    out = project_work_rows(rows)
    assert FM01 not in out


def test_T21_inactive_scaffold_fm01_absent():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=3.0, active=False)])
    assert FM01 not in out


def test_T22_scaffold_kind_absent_fm01_absent():
    row = {"work_type": "SCAFFOLD", "work_subtype": None, "attributes": {"height_m": 3.0}, "active": True}
    out = project_work_rows([row])
    assert FM01 not in out


def test_T23_empty_list_fm01_absent():
    out = project_work_rows([])
    assert FM01 not in out


def test_T23b_none_rows_fm01_absent():
    out = project_work_rows(None)
    assert FM01 not in out


# ─────────────────────────────────────────────────────────────────────────────
# T24~T25: 작업 subtype 독립성
# ─────────────────────────────────────────────────────────────────────────────

def test_T24_steel_pipe_scaffold_ge2m_no_subtype_fm01_true():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.0, subtype=None)])
    assert out.get(FM01) is True


def test_T25_steel_pipe_scaffold_ge2m_assembly_subtype_fm01_true():
    out = project_work_rows([_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.0, subtype="ASSEMBLY")])
    assert out.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T26: build_facility() — step1_body.input FM01 직접 읽기 금지
# ─────────────────────────────────────────────────────────────────────────────

def test_T26_build_facility_does_not_read_fm01_from_input():
    body = DiagnoseStep1Body(
        sector="CONSTRUCTION",
        input={FM01: True},
    )
    facility = build_facility(body, trusted_server_projections=None)
    assert FM01 not in facility


# ─────────────────────────────────────────────────────────────────────────────
# T27: _projected_work → _tsp → facility FM01
# ─────────────────────────────────────────────────────────────────────────────

def test_T27_projected_work_sets_tsp_and_facility_fm01():
    work_rows = [_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5)]
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={},
        work_rows=work_rows,
    )
    assert step1._tsp == {FM01: True}
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert facility.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T28: external FM01 차단 + projected True → facility True
# ─────────────────────────────────────────────────────────────────────────────

def test_T28_external_fm01_blocked_projected_true_facility_true():
    work_rows = [_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5)]
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={FM01: True},  # external — fail-closed 제거됨
        work_rows=work_rows,
    )
    # _tsp는 projector 출처만
    assert step1._tsp == {FM01: True}
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert facility.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T29: external FM01, projector 미발행 → _tsp 미설정 → facility FM01 absent
# ─────────────────────────────────────────────────────────────────────────────

def test_T29_external_fm01_projector_absent_tsp_none():
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={FM01: True},  # external
        work_rows=[],               # projector 미실행
    )
    assert step1._tsp is None
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert FM01 not in facility


# ─────────────────────────────────────────────────────────────────────────────
# T30: _tsp 단독 채널 — input FM01 absent, _tsp에서만 facility FM01
# ─────────────────────────────────────────────────────────────────────────────

def test_T30_tsp_only_channel_facility_fm01_true():
    body = DiagnoseStep1Body(sector="CONSTRUCTION", input={})
    body._tsp = {FM01: True}
    facility = build_facility(body, trusted_server_projections=body._tsp)
    assert facility.get(FM01) is True
    # input에는 없어야 함
    assert FM01 not in (body.input or {})


# ─────────────────────────────────────────────────────────────────────────────
# T31: External + _tsp 공존 — 서버 투영 결과만 반영
# ─────────────────────────────────────────────────────────────────────────────

def test_T31_external_plus_tsp_only_projector_source_in_facility():
    # form_data FM01=True (외부), projector도 True → _tsp=True
    work_rows = [_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5)]
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={FM01: True},  # external — 제거됨
        work_rows=work_rows,
    )
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    # facility FM01=True는 projector 출처
    assert facility.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T32: CONSTRUCTION safe end-to-end
# ─────────────────────────────────────────────────────────────────────────────

def test_T32_construction_safe_end_to_end():
    work_rows = [_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=3.0)]
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={},
        work_rows=work_rows,
    )
    assert step1._tsp == {FM01: True}
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert facility.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T33: BUILDING safe end-to-end
# ─────────────────────────────────────────────────────────────────────────────

def test_T33_building_safe_end_to_end():
    work_rows = [_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.0)]
    step1 = build_saas_leg_step1(
        sector="BUILDING",
        source_facts={},
        work_rows=work_rows,
    )
    assert step1._tsp == {FM01: True}
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert facility.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T34: INDUSTRIAL unified safe end-to-end (sector gate 없음 확인)
# ─────────────────────────────────────────────────────────────────────────────

def test_T34_industrial_safe_end_to_end_no_sector_gate():
    work_rows = [_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        work_rows=work_rows,
    )
    assert step1._tsp == {FM01: True}
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert facility.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T35: INDUSTRIAL legacy 우회 차단 (_tsp=None → FM01 absent)
# ─────────────────────────────────────────────────────────────────────────────

def test_T35_industrial_legacy_tsp_none_facility_fm01_absent():
    # INDUSTRIAL legacy path: body.input에 FM01 있어도 _tsp=None
    body = DiagnoseStep1Body(sector="INDUSTRIAL", input={FM01: True})
    # _tsp = None (기본값, legacy 경로는 미설정)
    assert body._tsp is None
    facility = build_facility(body, trusted_server_projections=None)
    assert FM01 not in facility


# ─────────────────────────────────────────────────────────────────────────────
# T36: FM01 not in _LEG_INPUT_FIELDS (canonical_applicability 1차 차단 확인)
# ─────────────────────────────────────────────────────────────────────────────

def test_T36_fm01_not_in_leg_input_fields():
    assert FM01 not in _LEG_INPUT_FIELDS


# ─────────────────────────────────────────────────────────────────────────────
# T37a: 로컬 Published leaf fixture — applicable_condition FM01 is_true leaf (Gate 4)
# 운영 DB 변경 전 로컬 fixture로 시뮬레이션. facility에 FM01=True가 전달되는지 확인.
# (facility 파이프라인 검증: _tsp → build_facility → FM01 in facility dict)
# ─────────────────────────────────────────────────────────────────────────────

def test_T37a_local_fixture_fm01_reaches_facility():
    body = DiagnoseStep1Body(sector="CONSTRUCTION", input={})
    body._tsp = {FM01: True}
    facility = build_facility(body, trusted_server_projections=body._tsp)
    # facility FM01=True → LEG Runtime evaluate_rtm 호출 시 Art.56 발화 조건 충족
    assert facility.get(FM01) is True


# T37a-LEG-EVAL: 로컬 RTM 엔진 직접 실행 (WO025-F13-I02-FM01-FINAL-GATE-017)
# evaluate_rtm() HTTP 호출 없이 실제 RTM 평가기(ConditionExtractor + BooleanComparator +
# ApplicableEvaluator)를 직접 사용. 운영 DB 없이 Forward SQL 이후 상태를 로컬 fixture로
# 시뮬레이션. 임의 모의 결과(mock 반환값) 사용 금지 계약 준수 — 평가기 로직 자체가 실행됨.
#
# LEG RTM 엔진 경로: /Users/taiwangsim/leg/development/engine/rtm_engine
# 핵심 근거: ConditionExtractor.extract() — mapped_field not in NUMERIC_FIELDS
#   → default Leaf(field, is_true). 0ddbaec7은 special dispatch dict 미등록.
#   → mapped_field="has_scaffold_at_ge_2m_subject_to_art56" 이면 is_true leaf 자동 생성.
def test_T37a_rtm_engine_fm01_condition_evaluation():
    """RTM 평가기가 FM01 is_true 조건을 올바르게 처리하는지 검증 (로컬 격리 실행)."""
    import sys
    _RTM_PATH = "/Users/taiwangsim/leg/development/engine/rtm_engine"
    if _RTM_PATH not in sys.path:
        sys.path.insert(0, _RTM_PATH)
    try:
        from rtm.applicable import (
            ApplicableEvaluator, ConditionExtractor, BooleanComparator, Tri, _BOOL_OP, Leaf,
        )
        from rtm.repository import Repository, RepositoryProvenance
        from rtm.contract import RuntimeInput, NUMERIC_FIELDS
    except ImportError as e:
        pytest.skip(f"LEG RTM 엔진 미설치: {e}")

    FM01_FIELD = "has_scaffold_at_ge_2m_subject_to_art56"
    ATOM_ID = "0ddbaec7-2a05-5c80-98e4-439301afe77a"

    # Forward SQL 이후 상태 시뮬레이션: mapped_field = FM01_FIELD
    # 0ddbaec7은 special dispatch dict 미등록 → default boolean leaf 경로
    fixture_atom = {
        "atom_id": ATOM_ID,
        "mapped_field": FM01_FIELD,
        "semantic_clause_id": "art56-fm01-local-fixture",
        "law_name": "", "law_article": "제56조",
        "evidence": "비계가 2미터 이상인 경우",
        "action": None, "condition": None, "exception": None,
        "threshold": None, "unit": None, "cycle_frequency": None,
    }
    prov = RepositoryProvenance("fixture", "fixture", "fixture", "fixture", 1)
    repo = Repository([fixture_atom], prov)
    rule = repo._rules[0]

    # 검증 1: FM01_FIELD not in NUMERIC_FIELDS → is_true leaf (default boolean path)
    assert FM01_FIELD not in NUMERIC_FIELDS
    cond = ConditionExtractor.extract(rule)
    assert isinstance(cond, Leaf)
    assert cond.field == FM01_FIELD and cond.op == _BOOL_OP

    # 검증 2: FM01=True → APPLICABLE (Art.56 발화)
    inp_true = RuntimeInput(conditions={FM01_FIELD: True})
    assert BooleanComparator.evaluate(inp_true, cond) == Tri.APPLICABLE

    # 검증 3: FM01 absent → UNKNOWN (≠ FALSE: absent=UNKNOWN 원칙)
    inp_absent = RuntimeInput(conditions={})
    assert BooleanComparator.evaluate(inp_absent, cond) == Tri.UNKNOWN

    # 검증 4: FM01=False → NOT_APPLICABLE
    inp_false = RuntimeInput(conditions={FM01_FIELD: False})
    assert BooleanComparator.evaluate(inp_false, cond) == Tri.NOT_APPLICABLE

    # 검증 5: ApplicableEvaluator 전체 — atom 0ddbaec7이 APPLICABLE set에 포함
    evaluator = ApplicableEvaluator(repo)
    result_true = evaluator.evaluate_all(inp_true)
    assert any(e.rule.atom_id == ATOM_ID for e in result_true.applicable)

    # 검증 6: FM01 absent → 0ddbaec7 APPLICABLE set 미포함
    result_absent = evaluator.evaluate_all(inp_absent)
    assert not any(e.rule.atom_id == ATOM_ID for e in result_absent.applicable)


@pytest.mark.skip(reason="T37a-BLOCKED (LEGACY): 이 SKIP은 기존 IV-01 차단 기록 보존용.")
def test_T37a_leg_evaluation_blocked():
    """IV-01: LEG_RUNTIME_URL HTTP 경로 BLOCKED 기록. T37a_rtm_engine으로 대체됨."""
    pass


# T37b: Gate 8 (Post-DB) — 운영 DB 적용 후 실행. 이 단계에서 SKIP.
@pytest.mark.skip(reason="T37b: Gate 8 — 운영 DB 적용 후 Post-Exec 검증. 이 단계에서 실행 금지.")
def test_T37b_post_db_art56_fires():
    pass


# ─────────────────────────────────────────────────────────────────────────────
# T38: source_facts FM01=True, work_rows 없음 → _tsp 미설정 (fail-closed)
# ─────────────────────────────────────────────────────────────────────────────

def test_T38_source_facts_fm01_no_work_rows_tsp_none():
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={FM01: True},
        work_rows=[],
    )
    assert step1._tsp is None
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert FM01 not in facility


# ─────────────────────────────────────────────────────────────────────────────
# T39: source_facts FM01=True, projector FM01 미발행 → _tsp 미설정
# ─────────────────────────────────────────────────────────────────────────────

def test_T39_source_facts_fm01_projector_not_emitting_tsp_none():
    # LEANING_SCAFFOLD: CONDITIONAL_HOLD → projector FM01 미발행
    work_rows = [_scaffold_row("LEANING_SCAFFOLD", height_m=3.0)]
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={FM01: True},
        work_rows=work_rows,
    )
    assert step1._tsp is None
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert FM01 not in facility


# ─────────────────────────────────────────────────────────────────────────────
# T40: source_facts FM01=True, projector FM01=True → _tsp=True (projector 출처만)
# ─────────────────────────────────────────────────────────────────────────────

def test_T40_source_facts_fm01_projector_true_tsp_from_projector():
    work_rows = [_scaffold_row("STEEL_PIPE_SCAFFOLD", height_m=2.5)]
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={FM01: True},  # external — 제거됨
        work_rows=work_rows,
    )
    # _tsp=True는 projector 결과, source_facts 아님
    assert step1._tsp == {FM01: True}
    facility = build_facility(step1, trusted_server_projections=step1._tsp)
    assert facility.get(FM01) is True


# ─────────────────────────────────────────────────────────────────────────────
# T41: Persistent + Transient any-TRUE — run_diagnosis() 실제 경로 (IV-02 보정)
# IV-02: 기존 테스트는 _fm01_for_tsp를 테스트 내부에서 재계산 후 assert만 함.
# 보정: 실제 run_diagnosis() → _build_unified_step1_body() → step1._tsp 설정 경로 실행.
# DB 접근은 stub으로 대체; 실제 병합·전달 코드(merge_or_raise, _build_unified_step1_body)는 실행.
# ─────────────────────────────────────────────────────────────────────────────

class _T41StubTable:
    """Supports all chaining patterns used by list_work_facts and auth/disc queries."""
    def __init__(self, rows):
        self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def insert(self, row): return self
    def update(self, *a, **k): return self
    def execute(self):
        class _R:
            pass
        r = _R()
        r.data = self._rows if self._rows is not None else [{"id": "x"}]
        r.error = None
        return r


class _T41StubSupabase:
    def __init__(self, work_rows=None):
        self._work_rows = work_rows or []
        self._auth = [{"id": "auth1", "ci_hash": "cihash", "name": "t", "phone": "",
                       "free_count": 0, "free_limit": 3, "status": "ACTIVE"}]
        self._disc = [{"id": "disc1", "ci_hash": "cihash", "agreed": True}]
        self._ins = [{"id": "res1", "public_token": "tok"}]

    def table(self, name):
        if name == "diagnosis_auth_log": return _T41StubTable(self._auth)
        if name == "diagnosis_disclaimer_log": return _T41StubTable(self._disc)
        if name == "anonymous_diagnosis_results": return _T41StubTable(self._ins)
        if name == "factory_work_facts": return _T41StubTable(self._work_rows)
        return _T41StubTable([{"id": "x"}])


_T41_CAPTURED: Dict[str, Any] = {}


def _t41_fake_run_step1(supabase, step1_body):
    _T41_CAPTURED["step1_body"] = step1_body
    return {"status": "success", "data": {"rules_table": [], "applicable_count": 0}}


def _t41_auto_tier(sector, floor_area=0.0, contract_amount_eok=0.0, user_tier=None):
    return {
        "CONSTRUCTION": "CONSTRUCTION_FREE",
        "BUILDING": "BUILDING_FREE",
    }.get(sector, "INDUSTRY_FREE")


_T41_FREE_CODES = frozenset({"CONSTRUCTION_FREE", "BUILDING_FREE", "INDUSTRY_FREE"})


def _t41_db_work_row(scaffold_kind: str, height_m: float) -> Dict[str, Any]:
    """factory_work_facts DB 행 형식 (load_work_rows_optional 반환값과 동일)."""
    return {
        "id": "row1", "factory_id": "fac1",
        "work_type": "SCAFFOLD", "work_subtype": None,
        "equipment_ref": None, "material_ref": None, "location_ref": None,
        "attributes": {"scaffold_kind": scaffold_kind, "height_m": height_m},
        "active": True,
        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
    }


def _t41_run(
    sector: str,
    form_data: Optional[Dict[str, Any]] = None,
    *,
    persistent_work_rows: Optional[list] = None,
    transient_work_attrs: Optional[list] = None,
):
    """
    실제 run_diagnosis() 경로 실행. DB는 stub; 병합·전달 코드는 실제 실행.
    persistent_work_rows: factory_work_facts DB 행 (factory_id=fac1 자동 설정).
    transient_work_attrs: WorkRowInput dict 목록 (validate_payload 경유).
    반환: 캡처된 step1_body.
    """
    from schemas.diagnosis_integrated import DiagnosisRunBody, WorkRowInput
    from services import diagnosis_integrated_svc as svc
    from services.canonical.leg_input_contract import build_unified_leg_input

    _T41_CAPTURED.clear()
    fd: Dict[str, Any] = dict(form_data or {})
    if sector == "CONSTRUCTION":
        fd.setdefault("appendix3_item_no", 48)
    else:
        fd.setdefault("appendix3_item_no", 28)

    body_kwargs: Dict[str, Any] = {
        "auth_token": "tok",
        "disclaimer_log_id": "disc1",
        "sector": sector,
        "form_data": fd,
    }
    if persistent_work_rows is not None:
        body_kwargs["factory_id"] = "fac1"
    if transient_work_attrs:
        body_kwargs["work_rows"] = [WorkRowInput(**r) for r in transient_work_attrs]

    body = DiagnosisRunBody(**body_kwargs)
    stub = _T41StubSupabase(work_rows=persistent_work_rows or [])

    svc.run_diagnosis(
        supabase=stub,
        body=body,
        run_step1_func=_t41_fake_run_step1,
        auto_tier_func=_t41_auto_tier,
        build_partial_func=lambda full: {},
        now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={},
        free_tier_codes=_T41_FREE_CODES,
        engine_version="test",
        unified_step1_factory_func=build_unified_leg_input,
    )
    return _T41_CAPTURED.get("step1_body")


def test_T41A_persistent_true_transient_none_fm01_for_tsp_true():
    # Persistent factory_work_facts에 FM01 트리거 행 → run_diagnosis() → _tsp 설정
    db_row = _t41_db_work_row("STEEL_PIPE_SCAFFOLD", 2.5)
    step1 = _t41_run("CONSTRUCTION", persistent_work_rows=[db_row])
    assert step1 is not None
    assert step1._tsp == {FM01: True}


def test_T41B_persistent_none_transient_true_fm01_for_tsp_true():
    # 트랜지언트 work_rows에 FM01 트리거 행 → run_diagnosis() → _tsp 설정
    trans = [{"work_type": "SCAFFOLD", "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": 2.5}, "active": True}]
    step1 = _t41_run("CONSTRUCTION", transient_work_attrs=trans)
    assert step1 is not None
    assert step1._tsp == {FM01: True}


def test_T41C_both_none_fm01_for_tsp_false():
    # FM01 트리거 없음 → _tsp=None
    step1 = _t41_run("CONSTRUCTION")
    assert step1 is not None
    assert step1._tsp is None


def test_T41D_worksource_load_error_raises_503():
    # WorkSourceLoadError → HTTPException 503 보존 확인
    from fastapi import HTTPException
    from unittest.mock import patch
    from services.work_source.store import WorkSourceLoadError

    def _raise_load(*args, **kwargs):
        raise WorkSourceLoadError("query failed", factory_id="fac1")

    with patch("services.work_source.store.list_work_facts", side_effect=_raise_load):
        with pytest.raises(HTTPException) as exc_info:
            _t41_run("CONSTRUCTION", persistent_work_rows=[])
        assert exc_info.value.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# T42: model_copy() 후 PrivateAttr _tsp 유지 (R4-04 정정)
# ─────────────────────────────────────────────────────────────────────────────

def test_T42_model_copy_preserves_private_attr_tsp():
    body = DiagnoseStep1Body(sector="CONSTRUCTION", input={"some_field": True})
    body._tsp = {FM01: True}
    copied = body.model_copy(update={"input": {"other_field": True}})
    assert copied._tsp == {FM01: True}


def test_T42b_tsp_set_after_model_copy_is_safe():
    body = DiagnoseStep1Body(sector="CONSTRUCTION", input={})
    copied = body.model_copy(update={"input": {"x": 1}})
    copied._tsp = {FM01: True}
    assert copied._tsp == {FM01: True}
    # 원본은 영향 없음
    assert body._tsp is None


# ─────────────────────────────────────────────────────────────────────────────
# T43: 외부 body.input FM01=True, _tsp=None → facility FM01 absent
# ─────────────────────────────────────────────────────────────────────────────

def test_T43_external_input_fm01_tsp_none_facility_absent():
    body = DiagnoseStep1Body(sector="CONSTRUCTION", input={FM01: True})
    assert body._tsp is None
    facility = build_facility(body, trusted_server_projections=None)
    assert FM01 not in facility


# ─────────────────────────────────────────────────────────────────────────────
# IV-03: Projector FM01 경계 조건 (WO025-F13-I02-FM01-CODE-IV-CORRECTION-015)
# validate_payload: transient height_m=inf/nan → WorkSourceValidationError (isfinite gate)
# persistent path(DB raw): validate_payload 미경유 → projector 직접 처리 → isfinite 필요
# 보정: math.isfinite() 추가 → P01 C2 scaffold_height_m 과 일관성.
# ─────────────────────────────────────────────────────────────────────────────

def test_iv03_height_inf_fm01_absent():
    # height_m=inf → math.isfinite() 검사 실패 → FM01 absent (projector 보정)
    import math as _math
    row = {"work_type": "SCAFFOLD", "work_subtype": None, "active": True,
           "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": _math.inf}}
    out = project_work_rows([row])
    assert FM01 not in out, "height_m=inf must not emit FM01 (isfinite guard)"


def test_iv03_height_nan_fm01_absent():
    # height_m=nan → isinstance(float) but nan >= 2 is False → FM01 absent (기존 동작 유지)
    import math as _math
    row = {"work_type": "SCAFFOLD", "work_subtype": None, "active": True,
           "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": _math.nan}}
    out = project_work_rows([row])
    assert FM01 not in out, "height_m=nan must not emit FM01"


def test_iv03_is_dalbi_true_conflict_fm01_absent():
    # IV-06 복원: is_dalbi=True + APPROVED_KIND + h≥2 → 모순 입력 → 해당 행 SKIP → FM01 absent
    # R2 Source Contract 원칙 6: "해당 행 FM01 기여 없음 (UNKNOWN)"
    row = {"work_type": "SCAFFOLD", "work_subtype": "ASSEMBLY", "active": True,
           "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": 3.0, "is_dalbi": True}}
    out = project_work_rows([row])
    assert FM01 not in out, "is_dalbi=True conflict row must not emit FM01 (IV-06)"


def test_iv03_is_dalbi_false_fm01_emitted():
    # is_dalbi=False → IV-06 적용 안 됨 → 정상 조건 → FM01=True (R2 T23b)
    row = {"work_type": "SCAFFOLD", "work_subtype": "ASSEMBLY", "active": True,
           "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": 3.0, "is_dalbi": False}}
    out = project_work_rows([row])
    assert out.get(FM01) is True, "is_dalbi=False must not block FM01 (IV-06 not triggered)"


def test_iv03_is_dalbi_conflict_and_valid_row_fm01_true():
    # any-TRUE 집계 유지: 상충 행(SKIP) + 정상 행 → 정상 행에 의해 FM01=True
    conflict_row = {"work_type": "SCAFFOLD", "work_subtype": "ASSEMBLY", "active": True,
                    "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": 3.0, "is_dalbi": True}}
    valid_row = {"work_type": "SCAFFOLD", "work_subtype": "USE_WITH_WORKERS", "active": True,
                 "attributes": {"scaffold_kind": "SYSTEM_SCAFFOLD", "height_m": 2.5}}
    out = project_work_rows([conflict_row, valid_row])
    assert out.get(FM01) is True, "valid row overrides conflict row via any-TRUE aggregate"


def test_iv03_all_rows_is_dalbi_conflict_fm01_absent():
    # 모든 행이 상충(is_dalbi=True) → FM01 absent (not FALSE, not NOT_APPLICABLE)
    rows = [
        {"work_type": "SCAFFOLD", "active": True,
         "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": 3.0, "is_dalbi": True}},
        {"work_type": "SCAFFOLD", "active": True,
         "attributes": {"scaffold_kind": "SYSTEM_SCAFFOLD", "height_m": 5.0, "is_dalbi": True}},
    ]
    out = project_work_rows(rows)
    assert FM01 not in out, "all conflict rows → FM01 absent (UNKNOWN, not FALSE)"


def test_iv03_transient_height_inf_blocked_by_validate_payload():
    # transient 경로: validate_payload가 height_m=inf를 WorkSourceValidationError로 차단
    import math as _math
    from services.work_source.store import WorkSourceValidationError, validate_payload
    payload = {"work_type": "SCAFFOLD", "active": True,
               "attributes": {"scaffold_kind": "STEEL_PIPE_SCAFFOLD", "height_m": _math.inf}}
    with pytest.raises(WorkSourceValidationError, match="finite"):
        validate_payload(payload)


# ─────────────────────────────────────────────────────────────────────────────
# 보안 불변식 — 인젝션 차단 확인
# ─────────────────────────────────────────────────────────────────────────────

def test_sec_fm01_not_in_leg_input_fields_invariant():
    """FM01이 _LEG_INPUT_FIELDS에 절대 포함되지 않아야 함."""
    assert FM01 not in _LEG_INPUT_FIELDS


def test_sec_source_facts_fm01_removed_by_fail_closed():
    """build_saas_leg_step1: source_facts FM01은 진입 즉시 제거됨."""
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts={FM01: True},
        work_rows=None,
    )
    assert step1._tsp is None
    facility = build_facility(step1, trusted_server_projections=None)
    assert FM01 not in facility


def test_sec_build_facility_ignores_inp_fm01():
    """build_facility: inp FM01은 sector 무관 무시됨."""
    for sector in ("CONSTRUCTION", "BUILDING", "INDUSTRIAL"):
        body = DiagnoseStep1Body(sector=sector, input={FM01: True})
        facility = build_facility(body, trusted_server_projections=None)
        assert FM01 not in facility, f"sector={sector}: FM01 should not be in facility"


def test_sec_tsp_false_not_propagated():
    """_tsp FM01=False → facility FM01 absent (True만 전달)."""
    body = DiagnoseStep1Body(sector="CONSTRUCTION", input={})
    body._tsp = {FM01: False}
    facility = build_facility(body, trusted_server_projections=body._tsp)
    assert FM01 not in facility
