#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
법령 원문 → GPT → master_building_legal_rules 자동 적재
섹터별 핵심 법령만 처리 (배치 단위: 조문 10개씩)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

try:
    from supabase import create_client
except ImportError:
    print("[ERROR] supabase 패키지 필요: pip install supabase")
    sys.exit(1)

try:
    import openai
except ImportError:
    print("[ERROR] openai 패키지 필요: pip install openai")
    sys.exit(1)

# ── .env 로드 (tai-api 루트 → tai-admin admin .env 순) ─────────────────
_ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(_ROOT / ".env")
    _admin_env = _ROOT.parent / "tai-admin" / "admin" / "full-version" / ".env"
    if _admin_env.is_file():
        load_dotenv(_admin_env)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or ""
)
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

TARGET_LAWS = {
    "MANUFACTURING": [
        "산업안전보건법",
        "산업안전보건법 시행령",
        "위험물안전관리법",
        "화학물질관리법",
        "고압가스 안전관리법",
        "에너지이용 합리화법",
    ],
    "CONSTRUCTION": [
        "건설산업기본법",
        "건설기술 진흥법",
        "산업안전보건법 시행령",
        "중대재해 처벌 등에 관한 법률",
    ],
    "SPECIAL_FACILITY": [
        "의료법",
        "의료법 시행령",
        "다중이용업소의 안전관리에 관한 특별법",
        "노인복지법",
        "사회복지사업법",
        "어린이놀이시설 안전관리법",
        "학교안전사고 예방 및 보상에 관한 법률",
    ],
}

SYSTEM_PROMPT = """
당신은 산업안전보건 법령 전문가입니다.
법령 조문과 항 내용을 분석하여 판정 룰을 JSON으로 출력하세요.

출력 형식 (배열):
[
  {
    "rule_id": "법령약어-번호 (예: OSH-MFG-101)",
    "law_name": "법령명",
    "law_article": "제XX조",
    "condition_code": "조건변수명 (worker_count/building_area/electric_capacity_kw/contract_amount/has_hazardous_material/has_high_pressure_gas/has_boiler/hospital_beds/student_count/employee_count 중 하나 — 반드시 DB 매핑용으로 employee_count는 상시근로자 수)",
    "condition_operator_code": "gte/lte/eq/in",
    "condition_value": 숫자 또는 null,
    "rule_type_code": "001(선임)/002(점검)/003(신고)/004(교육)/005(조치)",
    "appointment_required": true/false,
    "appointment_target_code": "safety_manager/health_manager/fire_safety_manager/electric_safety_manager/gas_safety_manager/hazmat_manager/energy_manager 중 하나 또는 null",
    "inspection_required": true/false,
    "report_required": true/false,
    "action_required": true/false,
    "obligation_summary": "한 줄 의무 요약 (예: 상시근로자 50명 이상 → 안전관리자 1명 선임)",
    "penalty_summary": "벌칙 요약 (예: 500만원 이하 과태료)",
    "sector": "MANUFACTURING/CONSTRUCTION/SPECIAL_FACILITY",
    "diagnosis_stage": 1
  }
]

규칙:
- 선임 의무가 있는 조문만 추출
- 수치 기준이 명확한 것만 추출 (모호한 것 제외)
- 조문당 최대 3개 룰
- condition_code는 산업안전 엔진 매핑에 맞게 employee_count(근로자수), electrical_capacity_kw 등 사용
- JSON만 출력 (설명 없음)
"""


def _sector_to_db(sector: str) -> str:
    """legal_engine.diagnose_step1 과 동일: SPECIAL_FACILITY → SPECIAL."""
    u = (sector or "").strip().upper()
    if u == "SPECIAL_FACILITY":
        return "SPECIAL"
    return u


def _map_rule_type_code(code: str | None) -> str | None:
    if not code:
        return None
    s = str(code).strip()
    if s.startswith("001"):
        return "APPOINTMENT"
    if s.startswith("002"):
        return "INSPECTION"
    if s.startswith("003"):
        return "REPORT"
    if s.startswith("004"):
        return "EDUCATION"
    if s.startswith("005"):
        return "ACTION"
    return s


def get_law_master_id(sb, law_name: str):
    r = sb.table("law_master").select("id").eq("law_name", law_name).limit(1).execute()
    if r.data:
        return r.data[0]["id"]
    r = sb.table("law_master").select("id").ilike("law_name", f"%{law_name}%").limit(1).execute()
    if r.data:
        return r.data[0]["id"]
    return None


def get_articles(sb, law_name: str, limit: int = 40):
    lid = get_law_master_id(sb, law_name)
    if not lid:
        return []
    ver = (
        sb.table("law_version")
        .select("id")
        .eq("law_id", lid)
        .eq("is_current", True)
        .limit(1)
        .execute()
    )
    if not ver.data:
        return []
    vid = ver.data[0]["id"]
    arts = (
        sb.table("law_article")
        .select("id,article_no,article_title,article_text")
        .eq("law_version_id", vid)
        .limit(limit)
        .execute()
    )
    rows = arts.data or []
    for a in rows:
        paras = (
            sb.table("law_paragraph")
            .select("paragraph_no,paragraph_text")
            .eq("article_id", a["id"])
            .execute()
        )
        a["paragraphs"] = paras.data or []
    return rows


def convert_to_rules(client: openai.OpenAI, law_name: str, sector: str, articles: list) -> list:
    text = f"법령명: {law_name}\n\n"
    for a in articles:
        no = a.get("article_no") or ""
        title = a.get("article_title") or ""
        body = (a.get("article_text") or "")[:1200]
        text += f"[제{no}조 {title}]\n{body}\n"
        for p in a.get("paragraphs") or []:
            pt = (p.get("paragraph_text") or "")[:500]
            if pt.strip():
                text += f"  (항) {pt}\n"
        text += "\n"

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"섹터: {sector}\n\n{text}"},
            ],
            max_tokens=2000,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        rules = json.loads(raw)
        return rules if isinstance(rules, list) else []
    except Exception as e:
        print(f"  GPT 오류: {e}")
        return []


def _normalize_condition_code(cc: str | None) -> str | None:
    if not cc:
        return None
    s = str(cc).strip()
    aliases = {
        "worker_count": "employee_count",
        "electric_capacity_kw": "electrical_capacity_kw",
    }
    return aliases.get(s, s)


def normalize_row(r: dict, default_law_name: str, default_sector: str) -> dict | None:
    rid = r.get("rule_id") or r.get("rule_code")
    if not rid:
        return None
    sec = r.get("sector") or default_sector
    row = {
        "rule_code": str(rid),
        "rule_id": str(rid),
        "rule_name": (r.get("obligation_summary") or "")[:500] or str(rid),
        "law_name": r.get("law_name") or default_law_name,
        "law_article": r.get("law_article") or "",
        "condition_code": _normalize_condition_code(r.get("condition_code")),
        "condition_operator_code": r.get("condition_operator_code") or "gte",
        "condition_value": r.get("condition_value"),
        "rule_type_code": r.get("rule_type_code"),
        "rule_type": _map_rule_type_code(r.get("rule_type_code")),
        "appointment_required": bool(r.get("appointment_required")),
        "appointment_target_code": r.get("appointment_target_code"),
        "inspection_required": bool(r.get("inspection_required")),
        "report_required": bool(r.get("report_required")),
        "action_required": bool(r.get("action_required")),
        "obligation_summary": r.get("obligation_summary"),
        "penalty_summary": r.get("penalty_summary"),
        "sector": _sector_to_db(sec),
        "diagnosis_stage": int(r.get("diagnosis_stage") or 1),
        "is_active": True,
    }
    return {k: v for k, v in row.items() if v is not None}


def insert_rules(sb, rules: list) -> int:
    inserted = 0
    for r in rules:
        if not r.get("rule_code"):
            continue
        try:
            sb.table("master_building_legal_rules").upsert(
                r, on_conflict="rule_code"
            ).execute()
            inserted += 1
        except Exception as e:
            try:
                sb.table("master_building_legal_rules").insert(r).execute()
                inserted += 1
            except Exception as e2:
                print(f"  DB 오류 ({r.get('rule_code')}): {e} / {e2}")
    return inserted


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] SUPABASE_URL 및 SUPABASE_KEY(또는 ANON/SERVICE) 필요")
        sys.exit(1)
    if not OPENAI_KEY:
        print("[ERROR] OPENAI_API_KEY 환경변수 필요")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    client = openai.OpenAI(api_key=OPENAI_KEY)

    total = 0
    batch_size = 10

    for sector, laws in TARGET_LAWS.items():
        print(f"\n=== {sector} ===")
        for law_name in laws:
            arts = get_articles(sb, law_name, limit=40)
            if not arts:
                print(f"  {law_name}: 조문 없음 (스킵)")
                continue
            print(f"  {law_name}: {len(arts)}개 조문 (배치 {batch_size}개씩 GPT 변환)")
            law_total = 0
            for i in range(0, len(arts), batch_size):
                chunk = arts[i : i + batch_size]
                rules_raw = convert_to_rules(client, law_name, sector, chunk)
                mapped = []
                for x in rules_raw:
                    row = normalize_row(x, law_name, sector)
                    if row:
                        mapped.append(row)
                n = insert_rules(sb, mapped)
                law_total += n
                time.sleep(1)
            print(f"  → {law_total}개 룰 적재")
            total += law_total

    print(f"\n✅ 전체 완료: {total}개 룰 적재")


if __name__ == "__main__":
    main()
