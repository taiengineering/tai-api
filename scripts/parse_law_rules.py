"""
법령 원문 키워드 파싱 → master_building_legal_rules 자동 적재
GPT 없이 동작 — 법령 article_text / paragraph_text 에서 패턴 추출

실행: python3 scripts/parse_law_rules.py
      또는 railway run python3 scripts/parse_law_rules.py
"""

import os, re, uuid
from pathlib import Path
from supabase import create_client

# ── 환경변수 로드 ─────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════════════════════
# 1. 파싱 패턴 정의
# ══════════════════════════════════════════════════════

# 선임 관련 키워드 → appointment_target_code
APPOINTMENT_KEYWORDS = {
    "안전관리자":          "safety_manager",
    "보건관리자":          "health_manager",
    "안전보건관리책임자":  "safety_health_manager",
    "안전보건관리담당자":  "safety_health_manager",
    "소방안전관리자":      "fire_safety_manager",
    "전기안전관리자":      "electric_safety_manager",
    "가스안전관리자":      "gas_safety_manager",
    "도시가스안전관리자":  "city_gas_manager",
    "위험물안전관리자":    "hazmat_manager",
    "에너지관리자":        "energy_manager",
    "승강기안전관리자":    "elevator_safety_manager",
    "기계설비유지관리자":  "building_manager",
    "안전관리전문기관":    "safety_manager",
    "건설안전전문가":      "construction_safety_judge",
}

# 조건 수치 패턴: (정규식, condition_code, 단위)
CONDITION_PATTERNS = [
    # 근로자 수
    (r"상시근로자\s*(\d[\d,]*)\s*명\s*이상",    "employee_count",       "gte"),
    (r"상시근로자\s*(\d[\d,]*)\s*명\s*미만",    "employee_count",       "lt"),
    (r"근로자\s*(\d[\d,]*)\s*명\s*이상",        "employee_count",       "gte"),
    # 공사금액
    (r"(\d[\d,]*)\s*억\s*원?\s*이상",           "contract_amount",      "gte"),
    (r"(\d[\d,]*)\s*억\s*원?\s*미만",           "contract_amount",      "lt"),
    # 연면적
    (r"연면적\s*(\d[\d,]*)\s*㎡?\s*이상",       "building_area",        "gte"),
    (r"연면적\s*(\d[\d,]*)\s*㎡?\s*미만",       "building_area",        "lt"),
    # 수전용량
    (r"수전용량\s*(\d[\d,]*)\s*킬로와트\s*이상", "electrical_capacity_kw", "gte"),
    (r"(\d[\d,]*)\s*킬로와트\s*이상",           "electrical_capacity_kw", "gte"),
    (r"(\d[\d,]*)\s*kW\s*이상",                "electrical_capacity_kw", "gte"),
    # 병상
    (r"병상\s*(\d[\d,]*)\s*개?\s*이상",         "hospital_beds",        "gte"),
    # 학생
    (r"학생\s*(\d[\d,]*)\s*명\s*이상",          "student_count",        "gte"),
]

# 벌칙 패턴
PENALTY_PATTERNS = [
    (r"(\d+)\s*억\s*원?\s*이하의?\s*벌금",   lambda m: f"{m.group(1)}억원 이하 벌금"),
    (r"(\d+)\s*천\s*만\s*원?\s*이하의?\s*벌금", lambda m: f"{m.group(1)}천만원 이하 벌금"),
    (r"(\d+)\s*만\s*원?\s*이하의?\s*과태료", lambda m: f"{m.group(1)}만원 이하 과태료"),
    (r"(\d+)\s*년?\s*이하의?\s*징역",        lambda m: f"{m.group(1)}년 이하 징역"),
]

# 의무 행위 키워드
OBLIGATION_KEYWORDS = {
    "두어야": "선임 의무",
    "선임하여야": "선임 의무",
    "선임하거나": "선임 의무",
    "위탁하여야": "선임(외탁) 의무",
    "등록하여야": "등록 의무",
    "신고하여야": "신고 의무",
    "보고하여야": "보고 의무",
    "실시하여야": "실시 의무",
    "교육을 받아야": "교육 의무",
    "점검을 해야": "점검 의무",
    "점검하여야": "점검 의무",
    "안전검사를": "안전검사 의무",
    "유해위험방지계획서": "유해위험방지계획서 제출",
    "산업안전보건관리비": "산업안전보건관리비 계상",
}

# 섹터별 대상 법령
TARGET_LAWS = {
    "MANUFACTURING": [
        ("산업안전보건법",            "OSH-MFG",  True),
        ("산업안전보건법 시행령",     "OSH-MFG-D", True),
        ("위험물안전관리법",          "HAZ-MFG",  True),
        ("위험물안전관리법 시행령",   "HAZ-MFG-D", True),
        ("고압가스 안전관리법",       "GAS-MFG",  True),
        ("화학물질관리법",            "CHM-MFG",  True),
        ("에너지이용 합리화법",       "ENE-MFG",  True),
        ("전기안전관리법",            "ELC-MFG",  True),
        ("전기안전관리법 시행령",     "ELC-MFG-D", True),
    ],
    "CONSTRUCTION": [
        ("산업안전보건법",            "OSH-CON",  True),
        ("산업안전보건법 시행령",     "OSH-CON-D", True),
        ("건설산업기본법",            "CON-CON",  True),
        ("건설산업기본법 시행령",     "CON-CON-D", True),
        ("건설기술 진흥법",           "CTL-CON",  True),
        ("건설기계관리법",            "CMC-CON",  True),
        ("중대재해 처벌 등에 관한 법률", "CSP-CON", True),
        ("중대재해 처벌 등에 관한 법률 시행령", "CSP-CON-D", True),
    ],
    "SPECIAL_FACILITY": [
        ("의료법",                    "MED-SF",   True),
        ("의료법 시행령",             "MED-SF-D", True),
        ("다중이용업소의 안전관리에 관한 특별법", "MUL-SF", True),
        ("다중이용업소의 안전관리에 관한 특별법 시행령", "MUL-SF-D", True),
        ("노인복지법",                "ELD-SF",   True),
        ("사회복지사업법",            "SOC-SF",   True),
        ("어린이놀이시설 안전관리법", "PLY-SF",   True),
        ("학교안전사고 예방 및 보상에 관한 법률", "SCH-SF", True),
    ]
}


# ══════════════════════════════════════════════════════
# 2. 파싱 함수
# ══════════════════════════════════════════════════════

def clean_num(s: str) -> float:
    """'1,000' → 1000.0"""
    return float(s.replace(",", ""))

def extract_penalty(text: str) -> str:
    for pat, fmt in PENALTY_PATTERNS:
        m = re.search(pat, text)
        if m:
            return fmt(m)
    return ""

def extract_appointment_target(text: str):
    for kw, code in APPOINTMENT_KEYWORDS.items():
        if kw in text:
            return kw, code
    return None, None

def extract_condition(text: str):
    """조건 코드, 연산자, 값 추출 (첫 번째 매칭)"""
    for pat, cond_code, op in CONDITION_PATTERNS:
        m = re.search(pat, text)
        if m:
            try:
                val = clean_num(m.group(1))
                # 억원 → 원 변환
                if cond_code == "contract_amount":
                    val = val * 100_000_000
                return cond_code, op, val
            except Exception:
                continue
    return None, None, None

def get_obligation_type(text: str):
    for kw, label in OBLIGATION_KEYWORDS.items():
        if kw in text:
            return label
    return None

def is_appointment_article(text: str) -> bool:
    return any(kw in text for kw in ["두어야", "선임하여야", "선임하거나", "위탁하여야"])

def is_inspection_article(text: str) -> bool:
    return any(kw in text for kw in ["점검을", "점검하여야", "안전검사", "정기검사"])

def is_report_article(text: str) -> bool:
    return any(kw in text for kw in ["신고하여야", "보고하여야", "유해위험방지계획서", "산업안전보건관리비"])


# ══════════════════════════════════════════════════════
# 3. DB 조회
# ══════════════════════════════════════════════════════

def get_law_articles(law_name: str):
    """법령명으로 조문 + 항 전체 조회"""
    # 정확 일치 먼저
    law = sb.table("law_master").select("id").eq("law_name", law_name).execute()
    if not law.data:
        # ilike 검색
        law = sb.table("law_master").select("id").ilike("law_name", f"%{law_name}%").limit(1).execute()
    if not law.data:
        return []

    lid = law.data[0]["id"]
    ver = sb.table("law_version").select("id").eq("law_id", lid).eq("is_current", True).execute()
    if not ver.data:
        return []

    vid = ver.data[0]["id"]

    # 조문 조회
    arts = sb.table("law_article").select(
        "id,article_no,article_title,article_text"
    ).eq("law_version_id", vid).order("article_no_sort").execute()

    result = []
    for art in (arts.data or []):
        # 항 조회
        paras = sb.table("law_paragraph").select(
            "paragraph_no,paragraph_text"
        ).eq("article_id", art["id"]).order("paragraph_no_sort").execute()

        result.append({
            "article_no":    art.get("article_no"),
            "article_title": art.get("article_title", ""),
            "article_text":  art.get("article_text", "") or "",
            "paragraphs":    paras.data or [],
        })
    return result


# ══════════════════════════════════════════════════════
# 4. 룰 생성
# ══════════════════════════════════════════════════════

def parse_rules_from_law(law_name: str, prefix: str, sector: str):
    articles = get_law_articles(law_name)
    if not articles:
        print(f"  {law_name}: 조문 없음 → 스킵")
        return []

    rules = []
    rule_seq = 1

    for art in articles:
        title = art["article_title"]
        art_text = art["article_text"]
        art_no = art["article_no"]
        article_ref = f"제{art_no}조"

        # 전체 텍스트 (조문 + 모든 항 합산)
        full_text = art_text
        for p in art["paragraphs"]:
            full_text += " " + (p.get("paragraph_text") or "")

        # 선임 의무 조문인지 확인
        is_appt    = is_appointment_article(full_text)
        is_insp    = is_inspection_article(full_text)
        is_rpt     = is_report_article(full_text)

        if not (is_appt or is_insp or is_rpt):
            continue

        # 선임 대상 추출
        kw_name, target_code = extract_appointment_target(full_text)

        # 조건 추출 — 항별로 먼저 시도
        cond_code, op, val = None, None, None
        for p in art["paragraphs"]:
            pt = p.get("paragraph_text", "") or ""
            cond_code, op, val = extract_condition(pt)
            if cond_code:
                break
        if not cond_code:
            cond_code, op, val = extract_condition(full_text)

        # 조건 없는 선임의무도 포함 (위험물 등)
        if not cond_code and is_appt and target_code:
            # 위험물/화학물질/가스 = boolean 조건
            bool_map = {
                "hazmat_manager":        ("has_hazardous_material", "eq", 1),
                "gas_safety_manager":    ("has_high_pressure_gas",  "eq", 1),
                "city_gas_manager":      ("has_city_gas",           "eq", 1),
                "energy_manager":        ("has_boiler",             "eq", 1),
                "electric_safety_manager": ("electrical_capacity_kw", "gte", 75),
                "elevator_safety_manager": ("elevator_count",        "gte", 1),
            }
            if target_code in bool_map:
                cond_code, op, val = bool_map[target_code]

        # 벌칙 추출
        penalty = extract_penalty(full_text)

        # 의무 요약 생성
        oblig_label = get_obligation_type(full_text) or ("선임 의무" if is_appt else "점검·신고 의무")
        if kw_name and cond_code and val:
            val_disp = int(val) if val == int(val) else val
            if cond_code == "contract_amount":
                val_disp = f"{int(val // 100_000_000)}억원"
            elif cond_code == "employee_count":
                val_disp = f"{int(val)}명"
            elif cond_code in ("electrical_capacity_kw",):
                val_disp = f"{int(val)}kW"
            else:
                val_disp = str(int(val))
            summary = f"{val_disp} 이상 → {kw_name} {oblig_label}"
        elif kw_name:
            summary = f"{kw_name} {oblig_label}"
        else:
            summary = f"{title} — {oblig_label}"

        rule_id = f"{prefix}-{rule_seq:03d}"
        rule_seq += 1

        rule = {
            "rule_id":                   rule_id,
            "law_name":                  law_name,
            "law_article":               article_ref,
            "condition_code":            cond_code,
            "condition_operator_code":   op,
            "condition_value":           val,
            "rule_type_code":            "001" if is_appt else ("002" if is_insp else "003"),
            "appointment_required":      is_appt,
            "appointment_target_code":   target_code,
            "inspection_required":       is_insp and not is_appt,
            "report_required":           is_rpt and not is_appt and not is_insp,
            "action_required":           False,
            "obligation_summary":        summary,
            "penalty_summary":           penalty or "",
            "sector":                    sector,
            "diagnosis_stage":           1,
            "is_active":                 True,
        }
        rules.append(rule)

    return rules


# ══════════════════════════════════════════════════════
# 5. DB 적재
# ══════════════════════════════════════════════════════

def upsert_rules(rules):
    inserted = 0
    skipped  = 0
    for r in rules:
        try:
            sb.table("master_building_legal_rules").upsert(
                r, on_conflict="rule_id"
            ).execute()
            inserted += 1
        except Exception as e:
            print(f"    ⚠ upsert 실패 ({r.get('rule_id')}): {e}")
            skipped += 1
    return inserted, skipped


# ══════════════════════════════════════════════════════
# 6. 메인 실행
# ══════════════════════════════════════════════════════

def main():
    grand_total = 0
    for sector, law_list in TARGET_LAWS.items():
        print(f"\n{'='*50}")
        print(f"섹터: {sector}")
        print(f"{'='*50}")
        sector_total = 0
        for law_name, prefix, _ in law_list:
            print(f"\n  [{law_name}]")
            rules = parse_rules_from_law(law_name, prefix, sector)
            if not rules:
                print(f"  → 룰 없음")
                continue
            ins, skp = upsert_rules(rules)
            print(f"  → 파싱 {len(rules)}개 / 적재 {ins}개 / 스킵 {skp}개")
            sector_total += ins
        grand_total += sector_total
        print(f"\n  [{sector}] 소계: {sector_total}개")

    print(f"\n{'='*50}")
    print(f"전체 완료: {grand_total}개 룰 적재")
    print(f"{'='*50}\n")

    # 최종 확인
    print("현재 룰 현황:")
    for sector in ["MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "BUILDING"]:
        r = sb.table("master_building_legal_rules").select(
            "id", count="exact"
        ).eq("sector", sector).eq("diagnosis_stage", 1).eq("is_active", True).execute()
        print(f"  {sector}: {r.count}개")


if __name__ == "__main__":
    main()
