"""WO-PAID-TIME-SHARED-NORMALIZER-001 — PAID consumer of shared legal_time_normalizer.

T1~T15. DB/network/LEG 불필요. forbidden modules 수정 0.
"""
from __future__ import annotations

import ast
import inspect
import io
from pathlib import Path

from openpyxl import load_workbook

from services.inspection_sets_svc.legal_time_read_model import attach_legal_time_normalized
from services.legal_time_normalizer import normalize_obligation_legal_time
from services.obligation_presentation_mapper import (
    map_diagnosis_presentation,
    map_operation_presentation,
)
from services.paid_result_excel_v1 import (
    LEGAL_CYCLE_COLUMNS,
    LEGAL_TIMING_COLUMNS,
    OBLIGATION_COLUMNS,
    SCHEDULE_COLUMNS,
    build_paid_result_excel_v1,
)
from services.paid_result_materializer import (
    TIMING_CHARACTER_MAP,
    build_paid_result_materials_v1,
)
from services.paid_result_public_projection_svc import build_public_premium_result_v1
from tests.test_paid_result_excel_v1 import _header, _ob, _premium, _rows
from tests.test_paid_result_materializer_v1 import _full_result, _obligation
from tests.test_paid_result_public_projection_v1 import _sample_product

_ROOT = Path(__file__).resolve().parents[1]
_PREV_OBLIGATION_COLUMNS = (
    "ref", "law_name", "law_article", "content_type", "obligation_type",
    "who", "recipient", "condition", "where", "how", "when", "inspection_cycle",
    "check_result", "canonical_source_text",
)
_PREV_SCHEDULE_COLUMNS = (
    "ref", "law_name", "law_article", "when", "inspection_cycle", "raw_cycle", "conflict",
)


def _mat(*, when=None, cycle=None):
    return build_paid_result_materials_v1(_full_result([
        _obligation(when=when, inspection_cycle=cycle),
    ]))


def _lt(materials):
    return materials["normalized_obligations"][0].get("legal_time_normalized")


# ── T1~T5 type coverage ──
def test_T1_recurring():
    n = _lt(_mat(cycle="1년에 1회"))
    c = n["cycle"]
    assert (c["type"], c["value"], c["unit"], c["operator"]) == ("RECURRING", 1, "YEAR", "EVERY")
    assert c["source_text"] == "1년에 1회"


def test_T2_event_deadline_before():
    t = _lt(_mat(when="작업 시작 전"))["timing"]
    assert t["type"] == "EVENT_DEADLINE" and t["operator"] == "BEFORE"
    assert t["basis_text"] == "작업 시작"
    assert "value" not in t and "unit" not in t


def test_T3_continuous():
    c = _lt(_mat(cycle="상시"))["cycle"]
    assert c["type"] == "CONTINUOUS"
    assert "value" not in c and "unit" not in c


def test_T4_immediate():
    assert _lt(_mat(when="즉시"))["timing"]["type"] == "IMMEDIATE"


def test_T5_raw_only():
    assert _lt(_mat(cycle="정기적으로"))["cycle"]["status"] == "RAW_ONLY"
    assert _lt(_mat(cycle="정기적으로"))["cycle"]["source_text"] == "정기적으로"


# ── T6 source_text EXACT (trim 안 함) ──
def test_T6_source_text_exact_preserves_padding():
    raw_when = "  매년  "
    n = _lt(_mat(when=raw_when))
    assert n["timing"]["source_text"] == raw_when
    assert n["timing"]["source_text"] != raw_when.strip()
    assert n["timing"]["type"] == "RECURRING"


# ── T7 SaaS == PAID deep equality ──
def test_T7_saas_paid_deep_equality():
    samples = [
        _obligation(when="즉시", inspection_cycle="매년"),
        _obligation(when="  매년  "),
        _obligation(when="작업 시작 전", inspection_cycle="1년에 1회"),
        _obligation(inspection_cycle="정기적으로"),
        _obligation(),
        _obligation(when="상시", inspection_cycle="상시"),
    ]
    for raw in samples:
        paid = normalize_obligation_legal_time(raw)
        saas_item = attach_legal_time_normalized({
            "legal_operation_presentation": map_operation_presentation(raw),
        })
        saas = saas_item.get("legal_time_normalized")
        assert paid == saas, raw


# ── T8 diagnosis == operation presentation timing/cycle ──
def test_T8_diagnosis_operation_presentation_timing_cycle():
    raw = _obligation(when="  매년  ", inspection_cycle="15일마다")
    d = map_diagnosis_presentation(raw)
    o = map_operation_presentation(raw)
    assert d["timing"] == o["timing"] == "  매년  "
    assert d["cycle"] == o["cycle"] == "15일마다"
    paid = _mat(when="  매년  ", cycle="15일마다")
    assert paid["normalized_obligations"][0]["presentation"]["timing"] == d["timing"]
    assert paid["normalized_obligations"][0]["presentation"]["cycle"] == d["cycle"]


# ── T9 absent → key 미생성 ──
def test_T9_absent_does_not_create_key():
    ob = _mat()["normalized_obligations"][0]
    assert "legal_time_normalized" not in ob
    projected = build_public_premium_result_v1({
        "paid_result_materials_v1": {"normalized_obligations": [ob], "meta": {}},
    })
    pub = projected["materials"]["obligations"][0]
    assert "legal_time_normalized" not in pub


# ── T10 projection purity ──
def test_T10_projection_purity_no_normalizer_import_or_call():
    path = _ROOT / "services" / "paid_result_public_projection_svc.py"
    src = path.read_text()
    assert "legal_time_normalizer" not in src
    assert "normalize_obligation_legal_time" not in src
    assert "normalize_legal_time_text" not in src
    tree = ast.parse(src)
    called = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called.append(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.append(fn.attr)
    assert "normalize_obligation_legal_time" not in called
    assert "normalize_legal_time_text" not in called


# ── T11 excel purity ──
def test_T11_excel_purity_no_normalizer_import_or_call():
    path = _ROOT / "services" / "paid_result_excel_v1.py"
    src = path.read_text()
    assert "legal_time_normalizer" not in src
    assert "normalize_obligation_legal_time" not in src
    assert "normalize_legal_time_text" not in src
    tree = ast.parse(src)
    called = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called.append(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.append(fn.attr)
    assert "normalize_obligation_legal_time" not in called
    assert "normalize_legal_time_text" not in called


# ── T12 excel 기존 컬럼 보존 ──
def test_T12_excel_existing_columns_preserved():
    assert OBLIGATION_COLUMNS[:len(_PREV_OBLIGATION_COLUMNS)] == _PREV_OBLIGATION_COLUMNS
    assert SCHEDULE_COLUMNS[:len(_PREV_SCHEDULE_COLUMNS)] == _PREV_SCHEDULE_COLUMNS
    for col in ("when", "inspection_cycle"):
        assert col in OBLIGATION_COLUMNS
    for col in ("when", "inspection_cycle", "raw_cycle", "conflict"):
        assert col in SCHEDULE_COLUMNS
    assert OBLIGATION_COLUMNS[len(_PREV_OBLIGATION_COLUMNS):] == LEGAL_TIMING_COLUMNS + LEGAL_CYCLE_COLUMNS
    assert SCHEDULE_COLUMNS[len(_PREV_SCHEDULE_COLUMNS):] == LEGAL_TIMING_COLUMNS + LEGAL_CYCLE_COLUMNS


# ── T13 excel normalized 출력 EXACT (재계산 아님) ──
def test_T13_excel_normalized_passthrough_exact_not_recomputed():
    fake = {
        "version": "v1",
        "timing": {
            "source_text": "NOT_RECOMPUTED",
            "status": "NORMALIZED",
            "type": "FAKE_TYPE",
            "operator": "FAKE_OP",
            "value": 99,
            "unit": "FAKE_UNIT",
            "basis_text": "FAKE_BASIS",
        },
        "cycle": {"source_text": "  매년  ", "status": "RAW_ONLY"},
    }
    p = _premium()
    p["materials"]["obligations"] = [
        _ob(17, when="상시", cycle="매월", raw="상시"),
    ]
    p["materials"]["obligations"][0]["legal_time_normalized"] = fake
    wb = load_workbook(io.BytesIO(build_paid_result_excel_v1(p)), data_only=False)
    for sheet, cols in (("Obligations", OBLIGATION_COLUMNS), ("Schedule", SCHEDULE_COLUMNS)):
        header = _header(wb[sheet])
        assert tuple(header) == cols
        row = _rows(wb[sheet])[0]
        by = dict(zip(header, row))
        assert by["when"] == "상시"
        assert by["inspection_cycle"] == "매월"
        assert by["legal_timing_source_text"] == "NOT_RECOMPUTED"
        assert by["legal_timing_status"] == "NORMALIZED"
        assert by["legal_timing_type"] == "FAKE_TYPE"
        assert by["legal_timing_operator"] == "FAKE_OP"
        assert by["legal_timing_value"] == 99
        assert by["legal_timing_unit"] == "FAKE_UNIT"
        assert by["legal_timing_basis_text"] == "FAKE_BASIS"
        assert by["legal_cycle_source_text"] == "  매년  "
        assert by["legal_cycle_status"] == "RAW_ONLY"
        assert by["legal_cycle_type"] is None
        assert by["legal_cycle_value"] is None
    sched = dict(zip(_header(wb["Schedule"]), _rows(wb["Schedule"])[0]))
    assert sched["raw_cycle"] == "상시"
    assert sched["conflict"] is False
    wb.close()


# ── T14 기존 PAID timing / R10 / R11 무변경 ──
def test_T14_existing_paid_timing_r10_r11_unchanged():
    import services.paid_result_materializer as M
    assert "def _normalize_timing" in inspect.getsource(M)
    assert "TIMING_CHARACTER_MAP" in inspect.getsource(M)
    assert "_r10_legal_timing_profile" in inspect.getsource(M.build_paid_result_materials_v1)
    assert "_r11_timing_character_summary" in inspect.getsource(M.build_paid_result_materials_v1)
    materials = _mat(when="상시", cycle="상시")
    ob = materials["normalized_obligations"][0]
    assert ob["timing"]["when"] == "상시"
    assert ob["timing"]["inspection_cycle"] == "상시"
    assert ob["timing"]["raw_cycle"] == "상시"
    assert ob["timing"]["conflict"] is False
    assert ob["timing"]["timing_character"] == TIMING_CHARACTER_MAP["상시"]
    assert "legal_timing_profile" in materials
    assert "timing_character_summary" in materials
    assert materials["timing_character_summary"]["counts"][ob["timing"]["timing_character"]] >= 1


# ── T15 official source only ──
def test_T15_official_source_only_obligations_raw():
    import services.paid_result_materializer as M
    loop = inspect.getsource(M.build_paid_result_materials_v1)
    assert "normalize_obligation_legal_time(raw_ob)" in loop
    assert "_text(" not in loop.split("normalize_obligation_legal_time(raw_ob)")[0][-80:]
    assert "legal_operation_presentation" not in inspect.getsource(M)
    assert "legal_time_read_model" not in inspect.getsource(M)
    tree = ast.parse((_ROOT / "services" / "paid_result_materializer.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "normalize_obligation_legal_time":
                assert len(node.args) == 1
                arg = node.args[0]
                assert isinstance(arg, ast.Name) and arg.id == "raw_ob"


def test_projection_passthrough_exact():
    product = _sample_product()
    fake = {"version": "v1", "timing": {"source_text": "PASS", "status": "RAW_ONLY"}}
    product["paid_result_materials_v1"]["normalized_obligations"][0]["legal_time_normalized"] = fake
    out = build_public_premium_result_v1(product)["materials"]["obligations"][0]
    assert out["legal_time_normalized"] is fake
    assert out["legal_time_normalized"]["timing"]["source_text"] == "PASS"
