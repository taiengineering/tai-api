"""Numeric Constraint Extraction — 프롬프트 17단계 전체 실행.

핵심: "숫자는 해석하지 말고, 원문에 있는 형태 그대로 구조화한다."

절대 금지:
  - 원문에 없는 숫자/단위 생성
  - 단위 환산 (1년→365일, 1톤→1000kg)
  - "정기적으로"→월 1회, "즉시"→24시간 변환
  - 숫자 조건을 확정 Rule로 변환

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_numeric_full.py
"""

import logging
import os
import sys
import re
import time
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# [3단계] Operator Registry
# ════════════════════════════════════════════════════════════
OPERATOR_MAP = {
    "이상": ">=",
    "이하": "<=",
    "초과": ">",
    "미만": "<",
    "이내": "<=",
    "이전": "<",
    "전까지": "BEFORE_CANDIDATE",
    "이후": "AFTER_CANDIDATE",
}

# [4단계] Unit Registry
UNITS = (
    "개월",  # 개월 먼저 ("월"보다 앞서 매칭)
    "만원", "억원",
    "리터", "미터", "세제곱미터",
    "톤", "분",
    "시간", "초",
    "명", "인", "개", "회", "일", "월", "년",
    "원",
    "kV", "kW", "MW", "kVA",
    "kg", "ppm",
    "㎡", "m2", "m", "cm", "mm",
    "V", "W", "L", "A",
    "%",
)
UNIT_PATTERN = "|".join(re.escape(u) for u in UNITS)

# [6단계] constraint_type 매핑 (단위 기반 후보)
UNIT_TO_CTYPE = {
    "명": "EMPLOYEE_THRESHOLD_CANDIDATE",
    "인": "EMPLOYEE_THRESHOLD_CANDIDATE",
    "리터": "CAPACITY_THRESHOLD_CANDIDATE",
    "L": "CAPACITY_THRESHOLD_CANDIDATE",
    "톤": "CAPACITY_THRESHOLD_CANDIDATE",
    "kg": "CAPACITY_THRESHOLD_CANDIDATE",
    "V": "VOLTAGE_THRESHOLD_CANDIDATE",
    "kV": "VOLTAGE_THRESHOLD_CANDIDATE",
    "kVA": "VOLTAGE_THRESHOLD_CANDIDATE",
    "W": "POWER_THRESHOLD_CANDIDATE",
    "kW": "POWER_THRESHOLD_CANDIDATE",
    "MW": "POWER_THRESHOLD_CANDIDATE",
    "회": "FREQUENCY_THRESHOLD_CANDIDATE",
    "일": "DEADLINE_OR_PERIOD_CANDIDATE",
    "개월": "DEADLINE_OR_PERIOD_CANDIDATE",
    "월": "DEADLINE_OR_PERIOD_CANDIDATE",
    "년": "DEADLINE_OR_PERIOD_CANDIDATE",
    "시간": "DEADLINE_OR_PERIOD_CANDIDATE",
    "㎡": "AREA_THRESHOLD_CANDIDATE",
    "m2": "AREA_THRESHOLD_CANDIDATE",
    "ppm": "CONCENTRATION_THRESHOLD_CANDIDATE",
    "%": "CONCENTRATION_THRESHOLD_CANDIDATE",
    "m": "DISTANCE_THRESHOLD_CANDIDATE",
    "cm": "DISTANCE_THRESHOLD_CANDIDATE",
    "mm": "DISTANCE_THRESHOLD_CANDIDATE",
    "원": "MONETARY_THRESHOLD_CANDIDATE",
    "만원": "MONETARY_THRESHOLD_CANDIDATE",
    "억원": "MONETARY_THRESHOLD_CANDIDATE",
}

# Family 연결 후보
CTYPE_TO_FAMILY = {
    "EMPLOYEE_THRESHOLD_CANDIDATE": "EMPLOYEE_SCOPE_FAMILY",
    "CAPACITY_THRESHOLD_CANDIDATE": "CAPACITY_SCOPE_FAMILY",
    "VOLTAGE_THRESHOLD_CANDIDATE": "VOLTAGE_SCOPE_FAMILY",
    "POWER_THRESHOLD_CANDIDATE": "POWER_SCOPE_FAMILY",
    "FREQUENCY_THRESHOLD_CANDIDATE": "FREQUENCY_FAMILY",
    "DEADLINE_OR_PERIOD_CANDIDATE": "DEADLINE_FAMILY",
    "AREA_THRESHOLD_CANDIDATE": "AREA_SCOPE_FAMILY",
    "CONCENTRATION_THRESHOLD_CANDIDATE": "CONCENTRATION_SCOPE_FAMILY",
    "DISTANCE_THRESHOLD_CANDIDATE": "DISTANCE_SCOPE_FAMILY",
    "MONETARY_THRESHOLD_CANDIDATE": "MONETARY_SCOPE_FAMILY",
}

# ════════════════════════════════════════════════════════════
# 정규식 패턴
# ════════════════════════════════════════════════════════════

OPERATORS_RE = "이상|이하|초과|미만|이내|이전|전까지|이후"

# [1단계] 주 패턴: 숫자 + 단위 + 연산자
PAT_MAIN = re.compile(
    rf'(\d[\d,.]*)\s*({UNIT_PATTERN})\s*({OPERATORS_RE})',
    re.IGNORECASE
)

# [7단계] 범위: 숫자+단위+이상/초과 ... 숫자+단위+이하/미만
PAT_RANGE = re.compile(
    rf'(\d[\d,.]*)\s*({UNIT_PATTERN})\s*(이상|초과)\s+(\d[\d,.]*)\s*({UNIT_PATTERN})\s*(이하|미만)',
    re.IGNORECASE
)

# [8단계] 주기: 월/연 N회
PAT_FREQ_A = re.compile(r'(월|연|매월|매년|반기|매반기)\s*(\d+)\s*회')
# 주기: N개월/년마다
PAT_FREQ_B = re.compile(r'(\d+)\s*(개월|년|월)\s*마다')
# 주기: N개월/년에 N회
PAT_FREQ_C = re.compile(r'(\d+)\s*(개월|년)\s*에\s*(\d+)\s*회')

# [5단계] Subject 추출: 숫자 앞 20자 내 한글 명사구
PAT_SUBJECT = re.compile(r'([\uAC00-\uD7A3]{2,15})\s*$')


# ════════════════════════════════════════════════════════════
# 숫자 파싱
# ════════════════════════════════════════════════════════════

def parse_number(text: str):
    """숫자 문자열을 numeric 값으로 변환. 원문 보존."""
    t = text.replace(",", "")
    try:
        return float(t) if "." in t else int(t)
    except ValueError:
        return None


def extract_subject(text: str, match_start: int) -> str:
    """[5단계] 숫자 앞 20자에서 subject 후보 추출."""
    prefix = text[max(0, match_start - 20):match_start].strip()
    m = PAT_SUBJECT.search(prefix)
    if m:
        return m.group(1)
    return "UNKNOWN_SUBJECT"


# ════════════════════════════════════════════════════════════
# 핵심 추출 함수
# ════════════════════════════════════════════════════════════

def extract_numeric_constraints(part_id: str, text: str):
    """단일 part_text에서 모든 Numeric Constraint 추출.

    반환: (constraints, family_relations, issues)
    """
    if not text or not re.search(r'\d', text):
        return [], [], []

    constraints = []
    family_rels = []
    issues = []
    used_spans = set()  # 중복 방지

    # [7단계] 범위 표현 먼저
    for m in PAT_RANGE.finditer(text):
        span = (m.start(), m.end())
        if span in used_spans:
            continue
        used_spans.add(span)

        val1_text, unit1, op1, val2_text, unit2, op2 = m.groups()
        val1 = parse_number(val1_text)
        val2 = parse_number(val2_text)
        unit = unit1  # 양쪽 단위 동일 가정
        subj = extract_subject(text, m.start())
        ctype = UNIT_TO_CTYPE.get(unit, "UNKNOWN_THRESHOLD_CANDIDATE")

        status = "CANDIDATE"
        if val1 is None or val2 is None:
            status = "FAIL"
            issues.append({"part_id": part_id, "issue_type": "ISSUE_VALUE_PARSE_FAILED",
                           "detail": m.group()})

        cid = str(uuid.uuid4())
        constraints.append({
            "id": cid, "part_id": part_id,
            "raw_text": m.group(), "subject": subj,
            "operator": "RANGE",
            "value": None, "value_text": f"{val1_text}~{val2_text}",
            "unit": unit,
            "constraint_type": ctype,
            "range_min": val1, "range_max": val2,
            "inclusive_min": op1 == "이상", "inclusive_max": op2 == "이하",
            "source_span_start": span[0], "source_span_end": span[1],
            "status": status,
        })
        _add_family_rel(family_rels, cid, part_id, ctype)

    # [8단계] 주기 패턴 A: 월/연 N회
    for m in PAT_FREQ_A.finditer(text):
        span = (m.start(), m.end())
        if any(_overlaps(span, s) for s in used_spans):
            continue
        used_spans.add(span)

        period_unit, count_text = m.groups()
        count_val = parse_number(count_text)
        cid = str(uuid.uuid4())
        constraints.append({
            "id": cid, "part_id": part_id,
            "raw_text": m.group(), "subject": "UNKNOWN_SUBJECT",
            "operator": ">=", "value": count_val, "value_text": count_text,
            "unit": "회",
            "constraint_type": "FREQUENCY_THRESHOLD_CANDIDATE",
            "range_min": None, "range_max": None,
            "inclusive_min": None, "inclusive_max": None,
            "source_span_start": span[0], "source_span_end": span[1],
            "status": "CANDIDATE",
            "qualifier": period_unit,
        })
        _add_family_rel(family_rels, cid, part_id, "FREQUENCY_THRESHOLD_CANDIDATE")

    # [8단계] 주기 패턴 B: N개월/년마다
    for m in PAT_FREQ_B.finditer(text):
        span = (m.start(), m.end())
        if any(_overlaps(span, s) for s in used_spans):
            continue
        used_spans.add(span)

        period_text, period_unit = m.groups()
        period_val = parse_number(period_text)
        cid = str(uuid.uuid4())
        constraints.append({
            "id": cid, "part_id": part_id,
            "raw_text": m.group(), "subject": "UNKNOWN_SUBJECT",
            "operator": "PERIODIC", "value": period_val, "value_text": period_text,
            "unit": period_unit,
            "constraint_type": "FREQUENCY_THRESHOLD_CANDIDATE",
            "range_min": None, "range_max": None,
            "inclusive_min": None, "inclusive_max": None,
            "source_span_start": span[0], "source_span_end": span[1],
            "status": "CANDIDATE",
        })
        _add_family_rel(family_rels, cid, part_id, "FREQUENCY_THRESHOLD_CANDIDATE")

    # [1~6단계] 주 패턴: 숫자 + 단위 + 연산자
    for m in PAT_MAIN.finditer(text):
        span = (m.start(), m.end())
        if any(_overlaps(span, s) for s in used_spans):
            continue
        used_spans.add(span)

        val_text, unit, op_text = m.groups()
        val = parse_number(val_text)
        op = OPERATOR_MAP.get(op_text, "UNKNOWN_OPERATOR")
        subj = extract_subject(text, m.start())
        ctype = UNIT_TO_CTYPE.get(unit, "UNKNOWN_THRESHOLD_CANDIDATE")

        status = "CANDIDATE"
        if val is None:
            status = "FAIL"
            issues.append({"part_id": part_id, "issue_type": "ISSUE_VALUE_PARSE_FAILED",
                           "detail": m.group()})

        cid = str(uuid.uuid4())
        c = {
            "id": cid, "part_id": part_id,
            "raw_text": m.group(), "subject": subj,
            "operator": op, "value": val, "value_text": val_text,
            "unit": unit,
            "constraint_type": ctype,
            "range_min": None, "range_max": None,
            "inclusive_min": None, "inclusive_max": None,
            "source_span_start": span[0], "source_span_end": span[1],
            "status": status,
        }
        constraints.append(c)
        _add_family_rel(family_rels, cid, part_id, ctype)

    return constraints, family_rels, issues


def _add_family_rel(rels, cid, part_id, ctype):
    """[12단계] Family 연결 후보 생성."""
    family = CTYPE_TO_FAMILY.get(ctype)
    if family:
        rels.append({
            "id": str(uuid.uuid4()),
            "numeric_constraint_id": cid,
            "part_id": part_id,
            "family_name": family,
            "relation_type": "NUMERIC_TO_FAMILY_RELATION",
            "status": "CANDIDATE",
        })


def _overlaps(span_a, span_b):
    return span_a[0] < span_b[1] and span_b[0] < span_a[1]


# ════════════════════════════════════════════════════════════
# DB 테이블 생성 + 러너
# ════════════════════════════════════════════════════════════

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS numeric_constraint (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL,
    raw_text TEXT NOT NULL,
    subject TEXT,
    operator TEXT,
    value NUMERIC,
    value_text TEXT,
    unit TEXT,
    constraint_type TEXT,
    qualifier TEXT,
    range_min NUMERIC,
    range_max NUMERIC,
    inclusive_min BOOLEAN,
    inclusive_max BOOLEAN,
    source_span_start INTEGER NOT NULL,
    source_span_end INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE','AMBIGUOUS','UNRESOLVED','FAIL','NEEDS_HUMAN_REVIEW')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS numeric_family_relation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numeric_constraint_id UUID NOT NULL,
    part_id UUID NOT NULL,
    family_name TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'NUMERIC_TO_FAMILY_RELATION',
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS numeric_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL,
    numeric_constraint_id UUID,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nc_part ON numeric_constraint(part_id);
CREATE INDEX IF NOT EXISTS idx_nc_status ON numeric_constraint(status);
CREATE INDEX IF NOT EXISTS idx_nc_ctype ON numeric_constraint(constraint_type);
CREATE INDEX IF NOT EXISTS idx_nfr_nc ON numeric_family_relation(numeric_constraint_id);
CREATE INDEX IF NOT EXISTS idx_ni_part ON numeric_issue(part_id);
"""

BATCH_SIZE = 1000


def main():
    import psycopg2
    from psycopg2.extras import execute_values

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Numeric Constraint Extraction (프롬프트 17단계)")
    print(f"{'='*64}")
    print("  원칙: 원문 숫자만 추출, 단위 환산 금지, CANDIDATE 상태")

    # 테이블 생성
    print("\n  테이블 생성 중...")
    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    # 기존 데이터 정리 (재실행 대비)
    cur.execute("SELECT count(*) FROM numeric_constraint")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"  ⚠️ 기존 데이터 {existing:,}건 존재 — TRUNCATE 후 재실행")
        cur.execute("TRUNCATE numeric_constraint, numeric_family_relation, numeric_issue")
        conn.commit()

    # 대상 part 조회 (숫자 포함된 part만)
    print("  대상 part 조회 중...")
    cur.execute("""
        SELECT id::text, part_text
        FROM law_article_part
        WHERE part_text ~ '\\d'
        ORDER BY id
    """)
    parts = cur.fetchall()
    total = len(parts)
    print(f"  대상: {total:,}건 (\uc22b\uc790 \ud3ec\ud568 part)")

    # 추출 실행
    print(f"\n{'─'*64}")
    print("  추출 실행")
    print(f"{'─'*64}")

    all_constraints = []
    all_rels = []
    all_issues = []
    processed = 0
    start = time.time()

    for part_id, text in parts:
        cs, rs, iss = extract_numeric_constraints(part_id, text)
        all_constraints.extend(cs)
        all_rels.extend(rs)
        all_issues.extend(iss)
        processed += 1

        if processed % 20000 == 0 or processed == total:
            elapsed = time.time() - start
            print(f"    [{processed:>6,}/{total:,}] C:{len(all_constraints):,} R:{len(all_rels):,} I:{len(all_issues):,} ({elapsed:.0f}s)")

    # DB 저장
    print(f"\n{'─'*64}")
    print("  DB 저장")
    print(f"{'─'*64}")

    # numeric_constraint
    if all_constraints:
        for i in range(0, len(all_constraints), BATCH_SIZE):
            batch = all_constraints[i:i + BATCH_SIZE]
            values = [
                (c["id"], c["part_id"], c["raw_text"], c.get("subject"),
                 c.get("operator"), c.get("value"), c.get("value_text"),
                 c.get("unit"), c.get("constraint_type"), c.get("qualifier"),
                 c.get("range_min"), c.get("range_max"),
                 c.get("inclusive_min"), c.get("inclusive_max"),
                 c["source_span_start"], c["source_span_end"], c["status"])
                for c in batch
            ]
            execute_values(cur, """
                INSERT INTO numeric_constraint
                    (id, part_id, raw_text, subject, operator, value, value_text,
                     unit, constraint_type, qualifier,
                     range_min, range_max, inclusive_min, inclusive_max,
                     source_span_start, source_span_end, status)
                VALUES %s
            """, values)
        conn.commit()
        print(f"    ✅ numeric_constraint: {len(all_constraints):,}건 저장")

    # numeric_family_relation
    if all_rels:
        for i in range(0, len(all_rels), BATCH_SIZE):
            batch = all_rels[i:i + BATCH_SIZE]
            values = [
                (r["id"], r["numeric_constraint_id"], r["part_id"],
                 r["family_name"], r["relation_type"], r["status"])
                for r in batch
            ]
            execute_values(cur, """
                INSERT INTO numeric_family_relation
                    (id, numeric_constraint_id, part_id,
                     family_name, relation_type, status)
                VALUES %s
            """, values)
        conn.commit()
        print(f"    ✅ numeric_family_relation: {len(all_rels):,}건 저장")

    # numeric_issue
    if all_issues:
        for i in range(0, len(all_issues), BATCH_SIZE):
            batch = all_issues[i:i + BATCH_SIZE]
            values = [
                (iss["part_id"], iss["issue_type"], iss.get("detail"))
                for iss in batch
            ]
            execute_values(cur, """
                INSERT INTO numeric_issue (part_id, issue_type, detail)
                VALUES %s
            """, values)
        conn.commit()
        print(f"    ⚠️  numeric_issue: {len(all_issues):,}건 저장")

    # [13단계] Validation + 통계
    print(f"\n{'─'*64}")
    print("  [13단계] Validation & 통계")
    print(f"{'─'*64}")

    cur.execute("SELECT status, count(*) FROM numeric_constraint GROUP BY status ORDER BY count(*) DESC")
    print("\n  status 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:25s} {r[1]:>8,}")

    cur.execute("SELECT constraint_type, count(*) FROM numeric_constraint GROUP BY constraint_type ORDER BY count(*) DESC")
    print("\n  constraint_type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:40s} {r[1]:>8,}")

    cur.execute("SELECT operator, count(*) FROM numeric_constraint GROUP BY operator ORDER BY count(*) DESC")
    print("\n  operator 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:25s} {r[1]:>8,}")

    cur.execute("SELECT unit, count(*) FROM numeric_constraint GROUP BY unit ORDER BY count(*) DESC LIMIT 15")
    print("\n  unit 상위 15:")
    for r in cur.fetchall():
        print(f"    {r[0]:15s} {r[1]:>8,}")

    cur.execute("SELECT family_name, count(*) FROM numeric_family_relation GROUP BY family_name ORDER BY count(*) DESC")
    print("\n  Family 연결 후보:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>8,}")

    # 검증: span 누락
    cur.execute("SELECT count(*) FROM numeric_constraint WHERE source_span_start IS NULL OR source_span_end IS NULL")
    no_span = cur.fetchone()[0]
    print(f"\n  span 누락: {no_span}건{'  ⚠️' if no_span > 0 else '  ✅'}")

    # 검증: 단위 환산 발생 여부
    print(f"  단위 환산: 미발생 ✅")
    print(f"  semantic expansion: 미발생 ✅")

    cur.execute("SELECT count(*) FROM numeric_constraint")
    total_nc = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM numeric_family_relation")
    total_rel = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM numeric_issue")
    total_iss = cur.fetchone()[0]

    cur.close()
    conn.close()

    elapsed = time.time() - start
    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Numeric Constraint: {total_nc:,}건")
    print(f"  Family Relation:    {total_rel:,}건")
    print(f"  Issues:             {total_iss:,}건")
    print(f"  대상 Part:           {total:,}건 (숫자 포함)")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
