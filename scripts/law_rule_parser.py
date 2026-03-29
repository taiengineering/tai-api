#!/usr/bin/env python3
"""
GPT 없는 법령 원문 키워드 파싱 → master_building_legal_rules 적재

로직:
1. 선임의무 키워드("두어야", "선임하여a" 등) 포함 조문 필터
2. 수치 패턴 정규식으로 조건값 추출 (N명, N억원, N㎡ 등)
3. 대상 조문 제목에서 appointment_target_code 유추
4. DB upsert
"""
import os, re, sys, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

from supabase import create_client
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────
# 콜린 사전
# ─────────────────────────────────────────

# 조리의무 키워드
APPOINT_KW = [
    "두어야 한다", "선임하여야", "선임해야",
    "지정하여야", "지정해야", "위하여야",
    "두어야한다", "선임하여야한다"
]
INSPECT_KW = [
    "점검하여야", "점검해야", "검사하여야",
    "검사를 받아야", "검사를받아야"
]
REPORT_KW = [
    "신고하여야", "신고해야", "제출하여야",
    "제출해야", "배치하여야"
]

# 조문 제목 → appointment_target_code 매핑
TITLE_TO_TARGET = {
    "안전관리자":       "safety_manager",
    "보건관리자":       "health_manager",
    "안전보건관리담당자": "safety_health_manager",
    "안전보건관리책임자": "safety_health_manager",
    "소방안전관리자":   "fire_safety_manager",
    "전기안전관리자":   "electric_safety_manager",
    "가스안전관리자":   "gas_safety_manager",
    "위험물안전관리자": "hazmat_manager",
    "에너지관리자":     "energy_manager",
    "승강기안전관리자": "elevator_safety_manager",
    "기계설비안전관리자": "machine_safety_manager",
    "지도사":               "supervisor",
}

# 조건코드 키워드 매핑
COND_MAP = [
    (r"(상시\s*)?\ub974\ub85c\uc790\s*(\d+)\s*명",    "employee_count",        "매업하는 팀""),
    (r"(상시\s*)?\uadfc\ub85c\uc790\s*(\d+)\s*명",    "employee_count",        ""),
    (r"연면\s*적\s*(\d[\d,]*)\s*(?:㎡|㎓|목)",  "building_area",         ""),
    (r"수\uc804\s*용\ub7c9\s*(\d[\d,]*)\s*(?:kW|kw|KW|kVA)", "electrical_capacity_kw",""),
    (r"공\uc0ac\s*금\ub7c9\s*(\d[\d]*)\s*억",       "contract_amount",       ""),
    (r"공\uc0ac\s*도\uc2dc\s*금\ub7c9\s*(\d[\d]*)\s*억",  "contract_amount",       ""),
    (r"병\uc0c1\s*(\d[\d]*)\s*개",              "hospital_beds",         ""),
    (r"학\uc0dd\s*(\d[\d]*)\s*명",              "student_count",         ""),
]

# 제조업 대상 법령
TARGET_LAWS = {
    "MANUFACTURING": [
        ("OSH",  "산업안전보건법"),
        ("OSHR", "산업안전보건법 시행령"),
        ("WCI",  "산업재해보상보험법"),
        ("HAZ",  "위험물안전관리법"),
        ("HAZR", "위험물안전관리법 시행령"),
        ("CHM",  "화학물질관리법"),
        ("CHMR", "화학물질관리법 시행령"),
        ("GAS",  "고압가스 안전관리법"),
        ("GASR", "고압가스 안전관리법 시행령"),
        ("ENE",  "에너지이용 합리화법"),
        ("ENER", "에너지이용 합리화법 시행령"),
        ("ELC",  "전기안전관리법"),
        ("ELCR", "전기안전관리법 시행령"),
    ],
    "CONSTRUCTION": [
        ("CST",  "건설산업기본법"),
        ("CSTR", "건설산업기본법 시행령"),
        ("CTR",  "건설기술 진흥법"),
        ("CTRR", "건설기술 진흥법 시행령"),
        ("OSH",  "산업안전보건법"),
        ("OSHR", "산업안전보건법 시행령"),
        ("MCA",  "중대재해 처벌 등에 관한 법률"),
        ("MCAR", "중대재해 처벌 등에 관한 법률 시행령"),
        ("ELC",  "전기안전관리법"),
    ],
    "SPECIAL_FACILITY": [
        ("MED",  "의료법"),
        ("MEDR", "의료법 시행령"),
        ("MUI",  "다중이용업소의 안전관리에 관한 특병법"),
        ("MUIR", "다중이용업소의 안전관리에 관한 특병법 시행령"),
        ("WEL",  "사회복지사업법"),
        ("WELR", "사회복지사업법 시행됹"),
        ("ELD",  "노인복지법"),
        ("ELDR", "노인복지법 시행령"),
        ("CHI",  "어린이놀이시설 안전관리법"),
        ("CHIR", "어린이놀이시설 안전관리법 시행령"),
        ("SCH",  "학교안전사고 예방 및 보상에 관한 법률"),
        ("SCHR", "학교안전사고 예방 및 보상에 관한 법률 시행령"),
    ],
}

# 단위 변환 (condition_value)
UNIT_CONV = {
    "억": 100_000_000,  # 공사금액 억 → 원
}

# 벌칙 키워드
PENALTY_MAP = [
    (r"(만원|억원)\s*이하\s*벤금",  "벌금"),
    (r"(만원|억원)\s*이하\s*과태료", "과태료"),
    (r"년\s*이하\s*징역",              "징역"),
]

# ─────────────────────────────────────────
# 도우미 함수
# ─────────────────────────────────────────

def has_keyword(text, kw_list):
    return any(kw in text for kw in kw_list)

def infer_target(title):
    for kw, code in TITLE_TO_TARGET.items():
        if kw in title:
            return code
    return None

def extract_condition(text):
    """텍스트에서 조건코드+값 추출. 여러 개 반환."""
    results = []
    for pattern, cond_code, _ in COND_MAP:
        m = re.search(pattern, text)
        if m:
            # 값 추출
            try:
                num_str = m.group(1).replace(",", "")
                val = int(num_str)
            except (IndexError, ValueError):
                val = None
            # 공사금액 단위 변환
            if cond_code == "contract_amount" and val:
                val = val * 100_000_000
            results.append((cond_code, val))
    return results

def get_law_articles(law_name):
    """법령명으로 조문+항 목록 반환."""
    # 정확 일치
    law = sb.table("law_master").select("id").eq("law_name", law_name).execute()
    if not law.data:
        # ilike 검색
        law = sb.table("law_master").select("id").ilike("law_name", f"%{law_name}%").limit(1).execute()
    if not law.data:
        return []
    lid = law.data[0]["id"]

    ver = sb.table("law_version").select("id").eq("law_id", lid).eq("is_current", True).execute()
    if not ver.data:
        ver = sb.table("law_version").select("id").eq("law_id", lid).order("created_at", desc=True).limit(1).execute()
    if not ver.data:
        return []
    vid = ver.data[0]["id"]

    # 조문 전체 조회
    arts = sb.table("law_article").select(
        "id, article_no, article_title, article_text"
    ).eq("law_version_id", vid).execute()

    result = []
    for a in (arts.data or []):
        # 항 조회
        paras = sb.table("law_paragraph").select(
            "paragraph_no, paragraph_text"
        ).eq("article_id", a["id"]).order("paragraph_no_sort").execute()
        result.append({
            "id":     a["id"],
            "no":     a["article_no"],
            "title":  a["article_title"] or "",
            "text":   a["article_text"] or "",
            "paras":  paras.data or [],
        })
    return result

def article_full_text(art):
    """조문 제목+본문+항 전체를 하나의 문자열로."""
    parts = [art["text"]]
    for p in art["paras"]:
        parts.append(p["paragraph_text"] or "")
    return "\n".join(parts)

def parse_articles(law_name, prefix, sector, articles):
    """조문 목록 → 룰 리스트."""
    rules = []
    seq = 1
    for art in articles:
        full = article_full_text(art)
        title = art["title"]

        # 선임/점검/신고 판단
        is_appoint = has_keyword(full, APPOINT_KW)
        is_inspect = has_keyword(full, INSPECT_KW) and not is_appoint
        is_report  = has_keyword(full, REPORT_KW)  and not is_appoint

        if not (is_appoint or is_inspect or is_report):
            continue

        # 조건 추출 (없으면 기본 1명 이상)
        conditions = extract_condition(full)
        if not conditions:
            conditions = [("employee_count", 1)]

        target = infer_target(title)

        # 벌칙 요약
        penalty = ""
        for pat, label in PENALTY_MAP:
            m = re.search(pat, full)
            if m:
                penalty = m.group(0)
                break

        for cond_code, cond_val in conditions:
            rule_id = f"{prefix}-{sector[:3]}-{art['no']:03d}-{seq:02d}"
            obligation = f"{art['no']}조 {title}: "
            if is_appoint and target:
                obligation += f"{TITLE_TO_TARGET.get(title, target).replace('_', ' ')} 선임 의무"
            elif is_inspect:
                obligation += "점검 의무"
            elif is_report:
                obligation += "신고 의무"

            rule = {
                "rule_id":                    rule_id,
                "law_name":                   law_name,
                "law_article":                f"제{art['no']}조",
                "condition_code":             cond_code,
                "condition_operator_code":    "gte",
                "condition_value":            cond_val,
                "rule_type_code":             "001" if is_appoint else ("002" if is_inspect else "003"),
                "appointment_required":       is_appoint,
                "appointment_target_code":    target,
                "inspection_required":        is_inspect,
                "report_required":            is_report,
                "action_required":            False,
                "obligation_summary":         obligation,
                "penalty_summary":            penalty,
                "sector":                     sector,
                "diagnosis_stage":            1,
                "is_active":                  True,
            }
            rules.append(rule)
            seq += 1

    return rules

def upsert_rules(rules):
    inserted = 0
    for r in rules:
        try:
            sb.table("master_building_legal_rules").upsert(
                r, on_conflict="rule_id"
            ).execute()
            inserted += 1
        except Exception as e:
            print(f"  ⚠️  DB 오류 ({r.get('rule_id')}): {e}")
    return inserted

# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────

total = 0

for sector, law_list in TARGET_LAWS.items():
    print(f"\n=== {sector} ===")
    for prefix, law_name in law_list:
        arts = get_law_articles(law_name)
        if not arts:
            print(f"  {law_name}: 조문 없음 (스킵)")
            continue
        print(f"  {law_name}: {len(arts)}개 조문 파싱 중...")
        rules = parse_articles(law_name, prefix, sector, arts)
        if not rules:
            print(f"  → 해당 조문 없음")
            continue
        n = upsert_rules(rules)
        print(f"  → {n}개 룰 적재")
        total += n

print(f"\n✅ 전체 완료: {total}개 룰 적재")

# 최종 확인
print("\n[섹터별 룰 현황]")
for s in ["MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY"]:
    r = sb.table("master_building_legal_rules") \
        .select("id", count="exact") \
        .eq("sector", s) \
        .eq("diagnosis_stage", 1) \
        .eq("is_active", True) \
        .execute()
    print(f"  {s}: {r.count}개")
