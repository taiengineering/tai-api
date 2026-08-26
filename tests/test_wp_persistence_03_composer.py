"""WP-PERSISTENCE-03 STEP-1 — Composer tests (OBJ-01 KNOT-2 read cutover).

pytest 호환. pytest 미설치 환경에서도 `python test_wp_persistence_03_composer.py` 로
self-runner 가 test_* 함수를 실행한다.

Fake Supabase client (KNOT-2):
    - base ledger 직독(safety_inspections / safety_inspection_results) = 금지.
    - read-only resolver RPC(fn_resolve_inspection_record) 만 허용하며, fixture 위에서
      DB resolver 를 모사해 current effective record 를 합성한다 (journal=0 가정).
    - 그 외 rpc / insert / update / delete / upsert = 즉시 실패.
"""
from __future__ import annotations

import os
import sys
import inspect as _inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.inspection_view_composer import (  # noqa: E402
    GENERAL_FIELD_COUNT,
    GENERAL_FORM_CODE,
    GENERAL_SCHEMA_ID,
    GENERAL_SCHEMA_VERSION,
    InspectionViewComposeError,
    compose_inspection_view,
)
import services.inspection_view_composer as composer_mod  # noqa: E402


# - effective record 모사 (DB fn_resolve_inspection_record, journal=0) -
_LEGACY_STATUS = {
    "in_progress": "IN_PROGRESS",
    "IN_PROGRESS": "IN_PROGRESS",
    "completed": "COMPLETED",
    "COMPLETED": "COMPLETED",
    "ISSUE": "COMPLETED",
    "HOLD": "COMPLETED",
}


def _norm_result_code(code):
    c = (code or "").lower()
    if c in ("normal", "ok", "pass"):
        return "NORMAL"
    if c == "hold":
        return "HOLD"
    if c in ("abnormal", "bad", "fail", "issue", "ng"):
        return "ABNORMAL"
    return "RESULT_CODE_UNRESOLVED"


def _resolve_record_from_tables(tables, inspection_id):
    insp = [r for r in tables.get("safety_inspections", []) if r.get("id") == inspection_id]
    if not insp:
        return {"error": "INSPECTION_NOT_FOUND", "detail": inspection_id}
    si = insp[0]
    results = []
    for r in tables.get("safety_inspection_results", []):
        if r.get("inspection_id") != inspection_id:
            continue
        results.append({
            "result_id": r.get("id"),
            "is_active": r.get("_is_active", True),
            "inspection_set_item_id": r.get("inspection_set_item_id"),
            "item_name": r.get("item_name"),
            "result_code": _norm_result_code(r.get("result_code")),
            "value_text": r.get("value_text"),
            "value_number": r.get("value_number"),
            "note": r.get("note"),
            "checked_at": r.get("checked_at"),
            "photo_url": r.get("photo_url"),
            "photo_urls": r.get("photo_urls"),
            "created_at": r.get("created_at"),
        })
    active_codes = [e["result_code"] for e in results if e["is_active"]]
    if not active_codes:
        overall = None
    elif "ABNORMAL" in active_codes:
        overall = "ABNORMAL"
    elif "HOLD" in active_codes:
        overall = "HOLD"
    else:
        overall = "NORMAL"
    return {
        "inspection_id": si.get("id"),
        "revision": 0,
        "is_active": si.get("_is_active", True),
        "inspection_status": _LEGACY_STATUS.get(si.get("status_code"), "COMPLETED"),
        "legacy_raw_status_code": si.get("status_code"),
        "assignment_id": si.get("assignment_id"),
        "asset_id": si.get("asset_id"),
        "inspector_id": si.get("inspector_id"),
        "inspection_date": si.get("inspection_date"),
        "submitted_by": si.get("submitted_by"),
        "factory_id": si.get("factory_id"),
        "results": results,
        "overall_result": overall,
    }


# - Fake Supabase (READ-ONLY; base 직독 금지, resolver RPC만 허용) -
class _Query:
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def in_(self, col, vals):
        s = set(vals)
        self._rows = [r for r in self._rows if r.get(col) in s]
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return type("Resp", (), {"data": list(self._rows)})()

    # write methods FORBIDDEN
    def _forbid(self, *_a, **_k):
        raise AssertionError("WRITE FORBIDDEN: composer must be READ-ONLY")

    insert = update = delete = upsert = _forbid


class _RpcCall:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return type("Resp", (), {"data": self._data})()


class FakeSupabase:
    def __init__(self, tables):
        self.tables = {k: list(v) for k, v in tables.items()}
        self.query_count = 0

    def table(self, name):
        # KNOT-2: composer must NOT read the base ledger directly.
        if name in ("safety_inspections", "safety_inspection_results"):
            raise AssertionError(
                f"DIRECT BASE READ FORBIDDEN: composer must resolve via RPC, not table({name!r})"
            )
        self.query_count += 1
        return _Query(self.tables.get(name, []))

    def rpc(self, name, params=None):
        if name == "fn_resolve_inspection_record":
            iid = (params or {}).get("p_inspection_id")
            return _RpcCall(_resolve_record_from_tables(self.tables, iid))
        raise AssertionError(
            f"RPC FORBIDDEN: only read-only fn_resolve_inspection_record allowed, got {name!r}"
        )


# - fixtures (production-accurate) -
POS_INSP = "3f9cf36f-5bbc-4dad-9ba6-e71643020e9a"
NEG_INSP = "217f0c15-56d5-48a4-88ef-8027e0a06057"
SET_ID = "7fee7518-0e77-445c-b822-d5178d069b3c"
WS_ID = "a99fdc96-68b4-4433-84d5-c1c30f1b79c3"
SI1, SI2, SI3 = (
    "eddb23a3-7c60-4c83-9832-945141d5284d",
    "90c198f4-7290-47f1-b2b5-d7c3481cb999",
    "5afdb267-0a37-40a2-8835-a8e3c42de287",
)
RESULT_IDS = [
    "6b3ac8bb-eaad-4568-b4b9-ed2ca7103d99",
    "baf2a402-3bb8-4901-9e99-214b8b04e481",
    "e707d159-c163-4e78-ab85-31101a50d3bf",
]
RID1, RID2, RID3 = RESULT_IDS


def _pos_tables(**over):
    t = {
        "safety_inspections": [
            {"id": POS_INSP, "assignment_id": WS_ID, "asset_id": None,
             "inspector_id": None, "inspection_date": "2026-05-14T00:00:00", "factory_id": "f-0003"},
        ],
        "work_schedules": [{"id": WS_ID, "inspection_set_id": SET_ID}],
        "safety_inspection_results": [
            {"id": RID1, "inspection_id": POS_INSP, "inspection_set_item_id": SI1, "item_name": None,
             "result_code": "NORMAL", "value_text": None, "value_number": None, "note": "외관 정상",
             "checked_at": "2026-05-14T07:49:43.778781+00:00", "photo_url": None, "photo_urls": [],
             "created_at": "2026-05-14T07:49:44.232993"},
            {"id": RID2, "inspection_id": POS_INSP, "inspection_set_item_id": SI2, "item_name": None,
             "result_code": "NORMAL", "value_text": None, "value_number": None, "note": "작동 정상",
             "checked_at": "2026-05-14T07:49:43.778781+00:00", "photo_url": None, "photo_urls": [],
             "created_at": "2026-05-14T07:49:44.232993"},
            {"id": RID3, "inspection_id": POS_INSP, "inspection_set_item_id": SI3, "item_name": None,
             "result_code": "NORMAL", "value_text": None, "value_number": None, "note": "안전장치 정상",
             "checked_at": "2026-05-14T07:49:43.778781+00:00", "photo_url": None, "photo_urls": [],
             "created_at": "2026-05-14T07:49:44.232993"},
        ],
        "inspection_set_items": [
            {"id": SI1, "inspection_set_id": SET_ID, "item_seq": 1, "item_name": "외관 상태 점검"},
            {"id": SI2, "inspection_set_id": SET_ID, "item_seq": 2, "item_name": "작동 시험"},
            {"id": SI3, "inspection_set_id": SET_ID, "item_seq": 3, "item_name": "안전장치 확인"},
        ],
        "inspection_sets": [{"id": SET_ID, "inspection_set_name": "소방시설공사업법 점검"}],
        "runtime_inspection_bridge": [
            {"id": "3894ddb5", "inspection_set_id": SET_ID, "runtime_form_schema_id": GENERAL_SCHEMA_ID}],
        "runtime_form_schema": [
            {"id": GENERAL_SCHEMA_ID, "status": "APPROVED_FOR_RUNTIME_USE", "version": 1, "field_count": 5,
             "source_trace": {"form_code": GENERAL_FORM_CODE, "source_table": "document_form_master"}}],
        "equipment_assets": [],
        "users": [{"id": "f267a20c-d191-4107-b685-9bec7f6aa0a6", "name": "김길동"}],
    }
    t.update(over)
    return t


def _neg_tables():
    rows = []
    for i, nm in enumerate(["작업 구역 정리정돈", "보호구 착용 확인", "설비 이상 유무", "비상구·소화기 위치", "작업 허가서 확인"]):
        rows.append({"id": f"neg{i}", "inspection_id": NEG_INSP, "inspection_set_item_id": None,
                     "item_name": nm, "result_code": "NORMAL", "value_text": None, "value_number": None,
                     "note": None, "checked_at": "2026-08-09T23:45:52.496926+00:00",
                     "photo_url": None, "photo_urls": None, "created_at": "2026-08-09T23:45:52"})
    t = _pos_tables()
    t["safety_inspections"] = [
        {"id": NEG_INSP, "assignment_id": None, "asset_id": None, "inspector_id": "f267a20c-d191-4107-b685-9bec7f6aa0a6",
         "inspection_date": "2026-08-09T23:45:52.496926", "factory_id": None}]
    t["safety_inspection_results"] = rows
    return t


def _expect_error(fn, code):
    try:
        fn()
    except InspectionViewComposeError as e:
        assert e.code == code, f"expected {code}, got {e.code} ({e.detail})"
        return
    raise AssertionError(f"expected InspectionViewComposeError {code}, no error raised")


# - T01–T07 positive -
def test_T01_positive_success_set_schema():
    vm = compose_inspection_view(POS_INSP, FakeSupabase(_pos_tables()))
    assert vm["inspection_id"] == POS_INSP
    assert vm["inspection_set_id"] == SET_ID
    assert vm["schema_id"] == GENERAL_SCHEMA_ID
    assert vm["form_code"] == GENERAL_FORM_CODE
    assert vm["schema_version"] == 1


def test_T02_effective_active_result_count_equals_view_count():
    t = _pos_tables()
    active_count = len(t["safety_inspection_results"])  # all active in this fixture
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    assert len(vm["fields"]["inspection_results"]) == active_count == 3  # ACTIVE EFFECTIVE == VIEW count


def test_T03_note_exact_preservation():
    vm = compose_inspection_view(POS_INSP, FakeSupabase(_pos_tables()))
    notes = [r["note"] for r in vm["fields"]["inspection_results"]]
    assert notes == ["외관 정상", "작동 정상", "안전장치 정상"]


def test_T04_row_order_seq_1_2_3():
    vm = compose_inspection_view(POS_INSP, FakeSupabase(_pos_tables()))
    names = [r["item_name"] for r in vm["fields"]["inspection_results"]]
    assert names == ["외관 상태 점검", "작동 시험", "안전장치 확인"]


def test_T05_positive_subject_null_missing():
    vm = compose_inspection_view(POS_INSP, FakeSupabase(_pos_tables()))
    assert vm["fields"]["inspection_subject"] is None
    assert "inspection_subject" in vm["completeness"]["missing_required_fields"]
    assert vm["completeness"]["is_complete"] is False


def test_T06_inspector_id_null_display_null_no_ws_fallback():
    # work_schedules.inspector_name 이 있어도 사용하지 않아야 함
    t = _pos_tables()
    t["work_schedules"] = [{"id": WS_ID, "inspection_set_id": SET_ID, "inspector_name": "심태왕"}]
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    assert vm["fields"]["inspector_display"] is None


def test_T07_pa_primary_resolved():
    vm = compose_inspection_view(POS_INSP, FakeSupabase(_pos_tables()))
    assert vm["inspection_set_id"] == SET_ID  # via assignment→ws.inspection_set_id


# - T08–T11 set resolution -
def test_T08_pa_vs_pb_mismatch_integrity_error():
    t = _pos_tables()
    # ws set = SET_ID, but a set_item resolves to a different set
    t["inspection_set_items"] = [
        {"id": SI1, "inspection_set_id": "OTHER-SET", "item_seq": 1, "item_name": "외관 상태 점검"},
        {"id": SI2, "inspection_set_id": SET_ID, "item_seq": 2, "item_name": "작동 시험"},
        {"id": SI3, "inspection_set_id": SET_ID, "item_seq": 3, "item_name": "안전장치 확인"},
    ]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "SOURCE_INTEGRITY_ERROR")


def test_T09_pa_unresolved_full_pb_one_set_fallback_success():
    t = _pos_tables()
    t["safety_inspections"] = [
        {"id": POS_INSP, "assignment_id": None, "asset_id": None, "inspector_id": None,
         "inspection_date": "2026-05-14T00:00:00", "factory_id": "f-0003"}]
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    assert vm["inspection_set_id"] == SET_ID


def test_T10_pa_unresolved_partial_coverage_unresolved():
    t = _pos_tables()
    t["safety_inspections"] = [
        {"id": POS_INSP, "assignment_id": None, "asset_id": None, "inspector_id": None,
         "inspection_date": "2026-05-14T00:00:00", "factory_id": "f-0003"}]
    # 한 result 의 set_item_id 를 NULL 로 → partial coverage
    t["safety_inspection_results"][2] = dict(t["safety_inspection_results"][2],
                                             inspection_set_item_id=None, item_name="안전장치 확인")
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "INSPECTION_SET_UNRESOLVED")


def test_T11_pb_multi_distinct_mixed():
    t = _pos_tables()
    t["safety_inspections"] = [
        {"id": POS_INSP, "assignment_id": None, "asset_id": None, "inspector_id": None,
         "inspection_date": "2026-05-14T00:00:00", "factory_id": "f-0003"}]
    t["inspection_set_items"] = [
        {"id": SI1, "inspection_set_id": SET_ID, "item_seq": 1, "item_name": "외관 상태 점검"},
        {"id": SI2, "inspection_set_id": "SET-B", "item_seq": 2, "item_name": "작동 시험"},
        {"id": SI3, "inspection_set_id": "SET-C", "item_seq": 3, "item_name": "안전장치 확인"},
    ]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "MIXED_INSPECTION_SET_SOURCE")


# - T12–T19 schema gate -
def test_T12_bridge_missing():
    t = _pos_tables()
    t["runtime_inspection_bridge"] = []
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "BRIDGE_NOT_FOUND")


def test_T13_bridge_schema_id_null():
    t = _pos_tables()
    t["runtime_inspection_bridge"] = [{"id": "b", "inspection_set_id": SET_ID, "runtime_form_schema_id": None}]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "PRESENTATION_SCHEMA_NOT_MAPPED")


def test_T14_schema_missing():
    t = _pos_tables()
    t["runtime_form_schema"] = []
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "SCHEMA_NOT_FOUND")


def test_T15_schema_not_approved():
    t = _pos_tables()
    t["runtime_form_schema"] = [dict(t["runtime_form_schema"][0], status="CANDIDATE")]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "SCHEMA_NOT_APPROVED")


def test_T16_approved_other_schema_unsupported():
    t = _pos_tables()
    t["runtime_inspection_bridge"] = [{"id": "b", "inspection_set_id": SET_ID, "runtime_form_schema_id": "OTHER-SCHEMA"}]
    t["runtime_form_schema"] = [
        {"id": "OTHER-SCHEMA", "status": "APPROVED_FOR_RUNTIME_USE", "version": 1, "field_count": 5,
         "source_trace": {"form_code": GENERAL_FORM_CODE}}]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "UNSUPPORTED_PRESENTATION_SCHEMA")


def test_T17_form_code_mismatch_unsupported():
    t = _pos_tables()
    t["runtime_form_schema"] = [dict(t["runtime_form_schema"][0], source_trace={"form_code": "OTHER-FORM"})]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "UNSUPPORTED_PRESENTATION_SCHEMA")


def test_T18_version_mismatch_unsupported():
    t = _pos_tables()
    t["runtime_form_schema"] = [dict(t["runtime_form_schema"][0], version=2)]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "UNSUPPORTED_PRESENTATION_SCHEMA")


def test_T19_field_count_mismatch_unsupported():
    t = _pos_tables()
    t["runtime_form_schema"] = [dict(t["runtime_form_schema"][0], field_count=7)]
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "UNSUPPORTED_PRESENTATION_SCHEMA")


# - T20–T24 item_name contract -
def test_T20_result_item_name_source_preservation():
    # CASE A: result.item_name non-null, set_item_id null
    t = _pos_tables()
    r = t["safety_inspection_results"][0]
    t["safety_inspection_results"][0] = dict(r, inspection_set_item_id=None, item_name="현장 기입 항목")
    # 나머지 두 행으로 set 은 P-A 로 이미 해소되므로 문제 없음
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    names = {rr["item_name"] for rr in vm["fields"]["inspection_results"]}
    assert "현장 기입 항목" in names


def test_T21_result_null_valid_setitem_derived():
    vm = compose_inspection_view(POS_INSP, FakeSupabase(_pos_tables()))  # positive = CASE D
    assert vm["fields"]["inspection_results"][0]["item_name"] == "외관 상태 점검"


def test_T22_result_master_mismatch_integrity_error():
    t = _pos_tables()
    t["safety_inspection_results"][0] = dict(t["safety_inspection_results"][0], item_name="다른 이름")
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "SOURCE_INTEGRITY_ERROR")


def test_T23_result_null_setitem_null_unresolved():
    # P-A resolved, 한 result 가 item_name NULL + set_item NULL → CASE E
    t = _pos_tables()
    t["safety_inspection_results"][0] = dict(t["safety_inspection_results"][0],
                                             inspection_set_item_id=None, item_name=None)
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "RESULT_ITEM_UNRESOLVED")


def test_T24_dangling_setitem_unresolved():
    t = _pos_tables()
    t["safety_inspection_results"][0] = dict(t["safety_inspection_results"][0],
                                             inspection_set_item_id="DANGLING-ID")
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "RESULT_ITEM_UNRESOLVED")


# - T25–T27 order / partial -
def test_T25_deterministic_order_null_seq_created_id():
    # 동일/NULL item_seq 에서 created_at → id stable
    t = _pos_tables()
    t["safety_inspections"] = [
        {"id": POS_INSP, "assignment_id": WS_ID, "asset_id": None, "inspector_id": None,
         "inspection_date": "2026-05-14T00:00:00", "factory_id": "f-0003"}]
    # 세 set_item 모두 seq=None, created_at 동일 → id ASC 로 정렬 (6b3ac8bb < baf2a402 < e707d159)
    t["inspection_set_items"] = [
        {"id": SI1, "inspection_set_id": SET_ID, "item_seq": None, "item_name": "외관 상태 점검"},
        {"id": SI2, "inspection_set_id": SET_ID, "item_seq": None, "item_name": "작동 시험"},
        {"id": SI3, "inspection_set_id": SET_ID, "item_seq": None, "item_name": "안전장치 확인"},
    ]
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    ids = [r["result_id"] for r in vm["fields"]["inspection_results"]]
    assert ids == sorted(ids)  # id ASC stable


def test_T26_inspection_date_null_partial_no_exception():
    t = _pos_tables()
    t["safety_inspections"] = [
        {"id": POS_INSP, "assignment_id": WS_ID, "asset_id": None, "inspector_id": None,
         "inspection_date": None, "factory_id": "f-0003"}]
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    assert vm["fields"]["inspected_at"] is None
    assert "inspected_at" in vm["completeness"]["missing_required_fields"]


def test_T27_no_results_pa_resolved_empty_missing():
    t = _pos_tables()
    t["safety_inspection_results"] = []
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    assert vm["fields"]["inspection_results"] == []
    assert "inspection_results" in vm["completeness"]["missing_required_fields"]


# - T28–T29 not found / negative -
def test_T28_inspection_not_found():
    _expect_error(lambda: compose_inspection_view("no-such-id", FakeSupabase(_pos_tables())), "INSPECTION_NOT_FOUND")


def test_T29_negative_legacy_unresolved():
    _expect_error(lambda: compose_inspection_view(NEG_INSP, FakeSupabase(_neg_tables())), "INSPECTION_SET_UNRESOLVED")


# - T30 write prohibition -
def test_T30_write_method_prohibited_static():
    src = _inspect.getsource(composer_mod)
    for bad in (".insert(", ".update(", ".delete(", ".upsert(", ".rpc("):
        assert bad not in src, f"forbidden write call {bad} found in composer source"


def test_T31_raw_code_is_effective_canonical():
    # KNOT-2: raw_code = Resolver 의 CURRENT EFFECTIVE result_code (canonical).
    # 소문자 등 legacy 표기는 resolver 가 정규화하며 Composer 는 재해석하지 않는다.
    t = _pos_tables()
    t["safety_inspection_results"][0] = dict(t["safety_inspection_results"][0], result_code="normal")
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    codes = [r["raw_code"] for r in vm["fields"]["inspection_results"]]
    assert all(c == "NORMAL" for c in codes)  # effective canonical, not "normal"


def test_T32_photo_urls_null_vs_empty_preserved():
    t = _pos_tables()
    t["safety_inspection_results"][0] = dict(t["safety_inspection_results"][0], photo_urls=None)
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    by_id = {r["result_id"]: r for r in vm["fields"]["inspection_results"]}
    assert by_id[RID1]["photo_urls"] is None      # NULL 그대로
    assert by_id[RID2]["photo_urls"] == []        # [] 그대로


def test_T33_fake_client_write_raises():
    fake = FakeSupabase(_pos_tables())
    try:
        fake.table("x").insert({"a": 1})
        raise AssertionError("insert should have raised")
    except AssertionError as e:
        assert "WRITE FORBIDDEN" in str(e)


def test_T34_exact_top_level_keys_no_extra():
    vm = compose_inspection_view(POS_INSP, FakeSupabase(_pos_tables()))
    assert set(vm.keys()) == {
        "inspection_id",
        "inspection_set_id",
        "schema_id",
        "form_code",
        "schema_version",
        "fields",
        "completeness",
    }  # extra key = 0 (no _source_result_count)


def test_T35_result_id_full_uuid_exact():
    t = _pos_tables()
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    view_ids = [r["result_id"] for r in vm["fields"]["inspection_results"]]
    source_ids = RESULT_IDS  # full production UUIDs, seq 1/2/3 order
    assert view_ids == source_ids  # SOURCE result_id == VIEW result_id, full UUID, no truncation
    for rid in view_ids:
        assert len(rid) == 36 and rid.count("-") == 4  # full UUID shape


# - T36–T41 KNOT-2 read cutover -
def test_T36_composer_no_direct_base_read_static():
    src = _inspect.getsource(composer_mod)
    assert '.table("safety_inspections")' not in src
    assert '.table("safety_inspection_results")' not in src


def test_T37_rpc_resolve_allowed_other_forbidden():
    fake = FakeSupabase(_pos_tables())
    resp = fake.rpc("fn_resolve_inspection_record", {"p_inspection_id": POS_INSP}).execute()
    assert resp.data["inspection_id"] == POS_INSP  # read-only resolver rpc allowed
    try:
        fake.rpc("fn_apply_inspection_record_command", {})
        raise AssertionError("non-resolver rpc should be forbidden")
    except AssertionError as e:
        assert "RPC FORBIDDEN" in str(e)


def test_T38_inactive_inspection_rejected():
    t = _pos_tables()
    t["safety_inspections"][0] = dict(t["safety_inspections"][0], _is_active=False)
    _expect_error(lambda: compose_inspection_view(POS_INSP, FakeSupabase(t)), "INSPECTION_INACTIVE")


def test_T39_inactive_result_excluded_count():
    # 3 active + 1 inactive → Web View count 3
    t = _pos_tables()
    t["safety_inspection_results"].append({
        "id": "dead0000-0000-0000-0000-000000000000", "inspection_id": POS_INSP,
        "inspection_set_item_id": SI1, "item_name": None, "result_code": "ABNORMAL",
        "value_text": None, "value_number": None, "note": "폐기된 결과",
        "checked_at": "2026-05-14T07:49:43.778781+00:00", "photo_url": None, "photo_urls": [],
        "created_at": "2026-05-14T07:49:44.232993", "_is_active": False,
    })
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    assert len(vm["fields"]["inspection_results"]) == 3  # inactive excluded, not silent-dropped active


def test_T40_inactive_cross_set_result_no_pb_contradiction():
    # P-A unresolved; 3 active → SET_ID, plus 1 INACTIVE → SET-X.
    # inactive result 는 P-B corroboration 에 참여하지 않으므로 MIXED 없이 SET_ID 로 해소.
    t = _pos_tables()
    t["safety_inspections"] = [
        {"id": POS_INSP, "assignment_id": None, "asset_id": None, "inspector_id": None,
         "inspection_date": "2026-05-14T00:00:00", "factory_id": "f-0003"}]
    t["inspection_set_items"] = [
        {"id": SI1, "inspection_set_id": SET_ID, "item_seq": 1, "item_name": "외관 상태 점검"},
        {"id": SI2, "inspection_set_id": SET_ID, "item_seq": 2, "item_name": "작동 시험"},
        {"id": SI3, "inspection_set_id": SET_ID, "item_seq": 3, "item_name": "안전장치 확인"},
        {"id": "SX", "inspection_set_id": "SET-X", "item_seq": 9, "item_name": "타 세트 항목"},
    ]
    t["safety_inspection_results"].append({
        "id": "dead0001-0000-0000-0000-000000000000", "inspection_id": POS_INSP,
        "inspection_set_item_id": "SX", "item_name": None, "result_code": "NORMAL",
        "value_text": None, "value_number": None, "note": None,
        "checked_at": "2026-05-14T07:49:43.778781+00:00", "photo_url": None, "photo_urls": [],
        "created_at": "2026-05-14T07:49:44.900000", "_is_active": False,
    })
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    assert vm["inspection_set_id"] == SET_ID  # inactive cross-set row excluded before P-B


def test_T41_abnormal_effective_reaches_raw_code():
    # legacy alias "issue" → canonical ABNORMAL → raw_code ABNORMAL (재해석 없음)
    t = _pos_tables()
    t["safety_inspection_results"][0] = dict(t["safety_inspection_results"][0], result_code="issue")
    vm = compose_inspection_view(POS_INSP, FakeSupabase(t))
    by_id = {r["result_id"]: r for r in vm["fields"]["inspection_results"]}
    assert by_id[RID1]["raw_code"] == "ABNORMAL"


# - self-runner (pytest 없이 실행) -
if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
