"""
샘플 법령진단 결과 생성 v2 — 정제 파이프라인 포함

1. 엔진 호출 → full_result
2. anonymous_diagnosis_results에 임시 저장
3. _build_result_payload() 호출 → 정제된 JSON
4. 임시 레코드 삭제
5. JSON 저장

사용법:
  cd ~/tai-api
  python scripts/generate_sample_data.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from db import supabase_client
from db.supabase_client import get_supabase
from routers import diagnosis_result_web
from routers.diagnosis_result_web import _build_result_payload
from schemas.legal_engine import DiagnoseStep1Body
from services.diagnosis_runtime_step1 import RUNTIME_ENGINE_VERSION, run_diagnose_step1_runtime

ALLOWED = frozenset({"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"})

NEXAS_DIR = os.path.abspath(os.path.join(ROOT, "..", "taieng", "nexas"))
HTML_TARGETS = {
    "sample_facility": "sample-facility.html",
    "sample_manufacturing": "sample-manufacturing.html",
    "sample_construction": "sample-construction.html",
}

REQUIRED_FIELDS = (
    "rules_table",
    "obligation_counts",
    "law_groups",
    "summary",
    "key_obligations",
    "inspection_schedule",
    "risk_level",
    "recommended_plan",
    "input_data",
    "pdf_url",
)


class _SampleResultsTable:
    """anonymous_diagnosis_results 조회만 in-memory로 대체 (대용량 insert timeout 회피)."""

    def __init__(self, real_table, rows: dict):
        self._real = real_table
        self._rows = rows
        self._mode = None
        self._eq = None

    def select(self, *args, **kwargs):
        self._mode = "select"
        return self

    def eq(self, col, val):
        self._eq = (col, val)
        return self

    def limit(self, n):
        return self

    def insert(self, row):
        token = row["public_token"]
        self._rows[token] = row
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def execute(self):
        if self._mode == "delete" and self._eq:
            self._rows.pop(self._eq[1], None)
            return SimpleNamespace(data=[])
        if self._mode == "select" and self._eq and self._eq[0] == "public_token":
            row = self._rows.get(self._eq[1])
            return SimpleNamespace(data=[row] if row else [])
        return self._real.execute()


class _SampleSupabase:
    def __init__(self, real, rows: dict):
        self._real = real
        self._rows = rows

    def table(self, name: str):
        real_table = self._real.table(name)
        if name == "anonymous_diagnosis_results":
            return _SampleResultsTable(real_table, self._rows)
        return real_table


@contextmanager
def _use_sample_row(row: dict):
    rows = {row["public_token"]: row}
    real_get = get_supabase

    def patched_get():
        return _SampleSupabase(real_get(), rows)

    supabase_client.get_supabase = patched_get
    diagnosis_result_web.get_supabase = patched_get
    try:
        yield
    finally:
        supabase_client.get_supabase = real_get
        diagnosis_result_web.get_supabase = real_get


def patch_sample_html(name: str, sample_data: dict) -> None:
    html_name = HTML_TARGETS.get(name)
    if not html_name:
        return
    html_path = os.path.join(NEXAS_DIR, html_name)
    if not os.path.isfile(html_path):
        print(f"[{name}] HTML not found: {html_path}")
        return

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    payload = json.dumps(sample_data, ensure_ascii=False, indent=2)
    replacement = f"const SAMPLE_DATA = {payload};"
    pattern = r"const SAMPLE_DATA = \{[\s\S]*?\n\};"
    if not re.search(pattern, html):
        raise RuntimeError(f"SAMPLE_DATA block not found in {html_path}")

    html = re.sub(pattern, replacement, html, count=1)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[{name}] patched {html_path}")


def validate_refined(name: str, refined: dict, raw_rules: int, refined_rules: int) -> bool:
    missing = [field for field in REQUIRED_FIELDS if field not in refined]
    if missing:
        print(f"[{name}] 검증 실패 — 누락 필드: {missing}")
        return False

    ob_counts = refined.get("obligation_counts") or {}
    law_groups = refined.get("law_groups") or []
    if not isinstance(ob_counts, dict) or not ob_counts:
        print(f"[{name}] 검증 실패 — obligation_counts 비어 있음")
        return False
    if not isinstance(law_groups, list) or not law_groups:
        print(f"[{name}] 검증 실패 — law_groups 비어 있음")
        return False

    deduped = raw_rules - refined_rules
    print(f"[{name}] 정제 전후: {raw_rules} → {refined_rules} rules (중복제거 {deduped}건)")
    print(f"[{name}] obligation_counts: {ob_counts}")
    print(f"[{name}] law_groups: {len(law_groups)}개 법령")
    print(f"[{name}] 검증 OK")
    return True


def generate_sample(name: str, body: DiagnoseStep1Body, tier_code: str = "SAMPLE"):
    supabase = get_supabase()

    print(f"[{name}] 엔진 호출...")
    full_result = run_diagnose_step1_runtime(supabase, body, ALLOWED)
    raw_rules = len(full_result.get("rules_table") or full_result.get("rules") or [])
    print(f"[{name}] 엔진 원본: {raw_rules} rules")

    token = f"SAMPLE-{name.upper()}-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)
    input_data = dict(body.input or {})
    for field in [
        "worker_count",
        "employee_count",
        "floor_area",
        "total_floor_area",
        "direct_workers",
        "subcon_workers",
        "contract_amount_eok",
    ]:
        val = getattr(body, field, None)
        if val is not None and field not in input_data:
            input_data[field] = val
    worker_count = input_data.get("worker_count") or input_data.get("workers")
    if not worker_count:
        worker_count = int(input_data.get("direct_workers") or 0) + int(input_data.get("subcon_workers") or 0)
        if worker_count:
            input_data["worker_count"] = worker_count
    input_data["sector"] = body.sector

    row = {
        "id": str(uuid.uuid4()),
        "public_token": token,
        "input_data": input_data,
        "partial_result": {},
        "full_result": full_result,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "status": "ACTIVE",
        "source_type": "sample_generator",
        "engine_version": RUNTIME_ENGINE_VERSION,
        "tier_code": tier_code,
    }

    # in-memory 임시 저장 후 _build_result_payload() 정제 (DB insert timeout 회피)
    with _use_sample_row(row):
        payload = _build_result_payload(token, free_preview_limit=None)
        refined = payload.get("data", payload)
        refined_rules = len(refined.get("rules_table") or [])
        print(f"[{name}] 정제 후: {refined_rules} rules (중복제거: {raw_rules - refined_rules}건)")
        print(f"[{name}] obligation_counts: {refined.get('obligation_counts', {})}")
        print(f"[{name}] law_groups: {len(refined.get('law_groups', []))}개 법령")
        print(f"[{name}] risk_level: {refined.get('risk_level')}")
        if not validate_refined(name, refined, raw_rules, refined_rules):
            raise RuntimeError(f"{name} 검증 실패")

    os.makedirs(os.path.join(ROOT, "scripts", "output"), exist_ok=True)
    path = os.path.join(ROOT, "scripts", "output", f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(refined, f, ensure_ascii=False, indent=2, default=str)
    print(f"[{name}] → {path}")

    patch_sample_html(name, refined)
    return refined


facility_body = DiagnoseStep1Body(
    factory_id=None,
    sector="BUILDING",
    input={
        "company_name": "서울타워 오피스 복합건물",
        "business_no": "111-22-33333",
        "ceo_name": "박관리",
        "address": "서울특별시 중구 남대문로 789",
    },
    building_use_type="오피스",
    floor_area=25000.0,
    total_floor_area=85000.0,
    floor_count=28,
    worker_count=120,
    employee_count=120,
    electric_capacity=3000.0,
    elevator_count=12,
    gas_capacity_m3=500.0,
    boiler_capacity_kw=2000.0,
    annual_energy_toe=800.0,
    has_boiler=True,
    has_high_pressure_gas=False,
    has_hazardous_material=False,
    has_chemical_substance=False,
)

manufacturing_body = DiagnoseStep1Body(
    factory_id=None,
    sector="MANUFACTURING",
    input={
        "company_name": "한국정밀제조(주) 안산 제2공장",
        "business_no": "222-33-44444",
        "ceo_name": "김제조",
        "address": "경기도 안산시 단원구 산업로 456",
        "processes": [
            {"name": "제련·원료처리", "equipments": ["용해로", "전기로", "냉각탑", "집진기", "원료이송컨베이어"]},
            {"name": "가공·성형", "equipments": ["프레스기", "CNC선반", "레이저절단기", "연삭기", "용접기"]},
            {"name": "도장·표면처리", "equipments": ["스프레이부스", "도장건조로", "산세정수장치", "환기장치"]},
            {"name": "조립·검사", "equipments": ["조립라인", "품질검사장비", "지게차(2대)"]},
            {"name": "포장·출하", "equipments": ["포장기계", "대량저장시설", "지게차(1대)"]},
        ],
        "hazardous_chemicals": ["톨루엔", "아세톤", "염산", "수산화나트륨"],
        "hazardous_material_types": ["인화성액체", "산화성액체"],
    },
    ksic_major="C24",
    floor_area=15000.0,
    total_floor_area=22000.0,
    worker_count=300,
    employee_count=300,
    electric_capacity=5000.0,
    has_high_pressure_gas=True,
    has_boiler=True,
    has_hazardous_material=True,
    has_chemical_substance=True,
    boiler_capacity_kw=3000.0,
    gas_capacity_m3=200.0,
    elevator_count=3,
    annual_energy_toe=1500.0,
)

construction_body = DiagnoseStep1Body(
    factory_id=None,
    sector="CONSTRUCTION",
    input={
        "company_name": "대한건설(주) 강남 오피스빌딩 신축 현장",
        "business_no": "333-44-55555",
        "ceo_name": "이건설",
        "address": "서울특별시 강남구 삼성동 123-4",
        "construction_phases": [
            {"name": "토공·기초", "works": ["굴착", "토류운반", "항타공사", "파일공사", "흙막이공사"]},
            {"name": "구조체", "works": ["철근배근", "거푸집", "콘크리트타설", "철골조립", "용접"]},
            {"name": "방수·단열", "works": ["외부방수", "내부방수", "단열시공"]},
            {"name": "전기·설비", "works": ["전기배선", "수변실", "승강기설치", "소방설비", "기계설비(HVAC)", "배관"]},
            {"name": "마감·인테리어", "works": ["외벽마감", "내부마감", "유리시공", "도장"]},
        ],
        "heavy_equipment": ["타워크레인(2대)", "굴삭기(3대)", "덤프트럭(5대)", "콘크리트펌프카", "철근절단기"],
    },
    construction_type="건축",
    contract_amount_eok=300.0,
    direct_workers=200,
    subcon_workers=150,
    electrical_capacity_kw=2000.0,
    has_crane=True,
    has_high_work=True,
    has_tunnel_bridge=False,
    has_blasting=False,
    floor_count=28,
)


if __name__ == "__main__":
    print("=" * 60)
    print("샘플 법령진단 데이터 생성 v2 (정제 파이프라인 포함)")
    print("=" * 60)
    print()

    ok = True
    for name, body, tier in [
        ("sample_facility", facility_body, "BUILDING_LARGE_V2"),
        ("sample_manufacturing", manufacturing_body, "INDUSTRY_STANDARD"),
        ("sample_construction", construction_body, "CONSTRUCTION_PREMIUM"),
    ]:
        try:
            generate_sample(name, body, tier)
        except Exception as e:
            ok = False
            print(f"[{name}] 실패: {e}")
            import traceback

            traceback.print_exc()
        print()

    if ok:
        print("완료. scripts/output/sample_*.json 확인 후 nexas/sample-*.html SAMPLE_DATA 교체.")
    else:
        sys.exit(1)
