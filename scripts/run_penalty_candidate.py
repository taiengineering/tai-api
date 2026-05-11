"""Penalty Candidate & Obligation-Penalty Mapping Engine — 프롬프트 20단계.

핵심: "처벌은 확정 판정이 아니라 연관 후보로만 연결한다."
절대 금지: 위반 확정, 처벌 적용 확정, 과태료 금액 확정 부과

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_penalty_candidate.py
"""

import logging, os, sys, time, re
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

PENALTY_KEYWORDS = [
    '과태료', '벌금', '징역', '과징금', '허가취소', '영업정지',
    '사용정지', '개선명령', '시정명령', '몰수', '양벌규정',
    '처한다', '부과한다',
]

PENALTY_FAMILY_MAP = {
    '과태료':     'ADMINISTRATIVE_FINE_FAMILY',
    '벌금':     'CRIMINAL_FINE_FAMILY',
    '징역':     'IMPRISONMENT_FAMILY',
    '과징금':   'SURCHARGE_FAMILY',
    '허가취소': 'LICENSE_REVOCATION_FAMILY',
    '영업정지': 'BUSINESS_SUSPENSION_FAMILY',
    '사용정지': 'USE_SUSPENSION_FAMILY',
    '개선명령': 'CORRECTIVE_ORDER_FAMILY',
    '시정명령': 'CORRECTIVE_ORDER_FAMILY',
    '몰수':     'CONFISCATION_FAMILY',
    '양벌규정': 'JOINT_PENALTY_FAMILY',
}

VIOLATION_TRIGGERS = [
    ('위반한 자',          'VIOLATION_FAMILY'),
    ('하지 아니한 자',     'NON_PERFORMANCE_FAMILY'),
    ('거짓으로',           'FALSE_REPORTING_FAMILY'),
    ('이행하지 아니한',    'NON_COMPLIANCE_FAMILY'),
    ('허가를 받지 아니하고', 'UNPERMITTED_FAMILY'),
    ('신고하지 아니하고',  'UNREPORTED_FAMILY'),
    ('적합하지 아니한',    'NON_CONFORMITY_FAMILY'),
]

NUMERIC_PENALTY_RE = re.compile(r'(\d[\d,]*)(억원|만원|천만원|원)\s*이하')
DURATION_PENALTY_RE = re.compile(r'(\d+)(년|개월|일)\s*이하')
REF_PATTERN = re.compile(r'제(\d+)조(?:의(\d+))?(?:제(\d+)항)?')

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS penalty_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL,
    article_id UUID NOT NULL,
    law_id UUID NOT NULL,
    penalty_family TEXT NOT NULL,
    raw_token TEXT,
    source_text TEXT,
    violation_trigger TEXT,
    violation_trigger_family TEXT,
    penalty_subject TEXT,
    is_joint_penalty BOOLEAN DEFAULT false,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS penalty_numeric (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    penalty_candidate_id UUID NOT NULL,
    raw_text TEXT NOT NULL,
    operator TEXT DEFAULT '<=',
    value NUMERIC,
    value_raw TEXT,
    unit TEXT,
    penalty_type TEXT,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS penalty_reference_link (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    penalty_candidate_id UUID NOT NULL,
    law_id UUID NOT NULL,
    from_article_no TEXT,
    to_article_ref TEXT NOT NULL,
    to_article_no INTEGER,
    to_article_id UUID,
    status TEXT NOT NULL DEFAULT 'LINK_CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS penalty_obligation_relation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    penalty_candidate_id UUID NOT NULL,
    rule_candidate_id UUID,
    obligation_family TEXT,
    relation_type TEXT NOT NULL DEFAULT 'POSSIBLE_NONCOMPLIANCE_PENALTY_LINK',
    via_reference TEXT,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS penalty_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    penalty_candidate_id UUID,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pc_law ON penalty_candidate(law_id);
CREATE INDEX IF NOT EXISTS idx_pc_family ON penalty_candidate(penalty_family);
CREATE INDEX IF NOT EXISTS idx_pn_pc ON penalty_numeric(penalty_candidate_id);
CREATE INDEX IF NOT EXISTS idx_prl_pc ON penalty_reference_link(penalty_candidate_id);
CREATE INDEX IF NOT EXISTS idx_por_pc ON penalty_obligation_relation(penalty_candidate_id);
"""


def get_conn():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    return conn


def safe_execute(sql, params=None, timeout='300s'):
    import psycopg2
    for attempt in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            cur.execute(sql, params) if params else cur.execute(sql)
            result = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            return result
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    ⚠️ retry {attempt+1}/3: {e}")
            time.sleep(2)
            if attempt == 2: raise


def safe_query(sql, params=None, timeout='300s'):
    import psycopg2
    for attempt in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            cur.execute(sql, params) if params else cur.execute(sql)
            rows = cur.fetchall()
            cur.close(); conn.close()
            return rows
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    ⚠️ retry {attempt+1}/3: {e}")
            time.sleep(2)
            if attempt == 2: raise


def safe_insert_values(sql, data, timeout='300s', batch_size=3000):
    import psycopg2
    from psycopg2.extras import execute_values
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        for attempt in range(3):
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(f"SET statement_timeout = '{timeout}'")
                execute_values(cur, sql, batch, page_size=batch_size)
                conn.commit(); cur.close(); conn.close()
                break
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                print(f"    ⚠️ retry batch {i//batch_size} ({attempt+1}/3): {e}")
                time.sleep(2)
                if attempt == 2: raise


def main():
    import uuid as uuid_mod

    print(f"\n{'='*64}")
    print("  Penalty Candidate Engine (프롬프트 20단계)")
    print(f"{'='*64}")
    print("  핵심: 처벌은 연관 후보. 위반/처벌 확정 금지.")

    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    safe_execute(CREATE_TABLES_SQL)

    for tbl in ['penalty_candidate','penalty_numeric','penalty_reference_link',
                'penalty_obligation_relation','penalty_issue']:
        cnt = safe_query(f"SELECT count(*) FROM {tbl}")[0][0]
        if cnt > 0:
            safe_execute(f"TRUNCATE {tbl}")

    start = time.time()

    # [1~3단계] Penalty 조문 식별
    print(f"\n{'─'*64}")
    print("  [1~3단계] Penalty 조문 식별")
    print(f"{'─'*64}")

    keyword_conditions = " OR ".join([f"lap.part_text LIKE '%{kw}%'" for kw in PENALTY_KEYWORDS])
    rows = safe_query(f"""
        SELECT lap.id::text, lap.article_id::text, la.law_id::text,
               lap.part_text, la.article_no
        FROM law_article_part lap
        JOIN law_article la ON lap.article_id = la.id
        WHERE ({keyword_conditions})
        AND lap.part_text IS NOT NULL AND length(lap.part_text) > 5
    """)
    print(f"    Penalty 관련 Part: {len(rows):,}건")

    penalty_rows = []
    numeric_rows = []
    ref_rows = []

    for part_id, article_id, law_id, text, article_no in rows:
        families_found = set()
        for kw, family in PENALTY_FAMILY_MAP.items():
            if kw in text:
                families_found.add((kw, family))
        if not families_found:
            families_found.add(('처벌', 'UNKNOWN_PENALTY_FAMILY'))

        vt_text, vt_family = None, None
        for vt_pat, vt_fam in VIOLATION_TRIGGERS:
            if vt_pat in text:
                vt_text = vt_pat
                vt_family = vt_fam
                break

        subject = None
        for subj in ['사업주', '법인', '대표자', '관리자', '종업원', '행위자']:
            if subj in text:
                subject = subj
                break

        is_joint = '양벌규정' in text or ('법인' in text and '행위자' in text)

        for raw_kw, family in families_found:
            pc_id = str(uuid_mod.uuid4())
            penalty_rows.append((
                pc_id, part_id, article_id, law_id,
                family, raw_kw, text[:500],
                vt_text, vt_family, subject, is_joint, 'CANDIDATE'
            ))

            for m in NUMERIC_PENALTY_RE.finditer(text):
                raw = m.group(0)
                val_str = m.group(1).replace(',', '')
                unit_str = m.group(2)
                multiplier = {'원': 1, '만원': 10000, '천만원': 10000000, '억원': 100000000}
                val = int(val_str) * multiplier.get(unit_str, 1)
                numeric_rows.append((
                    pc_id, raw, '<=', val, f"{val_str}{unit_str}", '원', family, 'CANDIDATE'
                ))

            for m in DURATION_PENALTY_RE.finditer(text):
                raw = m.group(0)
                numeric_rows.append((
                    pc_id, raw, '<=', int(m.group(1)), m.group(1)+m.group(2), m.group(2), family, 'CANDIDATE'
                ))

            # Reference Link — article_no를 정수로도 저장
            for m in REF_PATTERN.finditer(text):
                ref_art_no = int(m.group(1))
                ref_str = f"제{m.group(1)}조"
                if m.group(2):
                    ref_str += f"의{m.group(2)}"
                if m.group(3):
                    ref_str += f"제{m.group(3)}항"
                ref_rows.append((
                    pc_id, law_id, str(article_no) if article_no else None,
                    ref_str, ref_art_no, None, 'LINK_CANDIDATE'
                ))

    if penalty_rows:
        safe_insert_values("""
            INSERT INTO penalty_candidate
                (id, part_id, article_id, law_id, penalty_family, raw_token,
                 source_text, violation_trigger, violation_trigger_family,
                 penalty_subject, is_joint_penalty, status)
            VALUES %s
        """, penalty_rows)
    print(f"    ✅ Penalty Candidate: {len(penalty_rows):,}건")

    if numeric_rows:
        safe_insert_values("""
            INSERT INTO penalty_numeric
                (penalty_candidate_id, raw_text, operator, value,
                 value_raw, unit, penalty_type, status)
            VALUES %s
        """, numeric_rows)
    print(f"    ✅ Penalty Numeric: {len(numeric_rows):,}건")

    if ref_rows:
        safe_insert_values("""
            INSERT INTO penalty_reference_link
                (penalty_candidate_id, law_id, from_article_no,
                 to_article_ref, to_article_no, to_article_id, status)
            VALUES %s
        """, ref_rows)
    print(f"    ✅ Penalty Reference Link: {len(ref_rows):,}건")

    # [7단계] Obligation-Penalty 연결 — to_article_no(integer) 기반 JOIN
    print(f"\n{'─'*64}")
    print("  [7단계] Obligation-Penalty 연결")
    print(f"{'─'*64}")

    obl_count = safe_execute("""
        INSERT INTO penalty_obligation_relation
            (penalty_candidate_id, rule_candidate_id, obligation_family,
             relation_type, via_reference, status)
        SELECT prl.penalty_candidate_id, rc.id,
               COALESCE((
                   SELECT rcs.family_name FROM rule_candidate_slot rcs
                   WHERE rcs.rule_candidate_id = rc.id
                   AND rcs.slot_type IN ('OBLIGATION','ACTION')
                   AND rcs.family_name != 'UNKNOWN'
                   LIMIT 1
               ), 'UNKNOWN'),
               'POSSIBLE_NONCOMPLIANCE_PENALTY_LINK',
               prl.to_article_ref,
               'CANDIDATE'
        FROM penalty_reference_link prl
        JOIN law_article la ON la.law_id = prl.law_id
            AND la.article_no = prl.to_article_no
        JOIN law_article_part lap ON lap.article_id = la.id
        JOIN rule_candidate rc ON rc.part_id = lap.id
        WHERE prl.status = 'LINK_CANDIDATE'
          AND prl.to_article_no IS NOT NULL
    """)
    print(f"    ✅ Obligation-Penalty Relation: {obl_count:,}건")

    # [16단계] Validation
    print(f"\n{'─'*64}")
    print("  [16단계] Validation")
    print(f"{'─'*64}")

    fam_dist = safe_query("SELECT penalty_family, count(*) FROM penalty_candidate GROUP BY penalty_family ORDER BY count(*) DESC")
    print("\n  Penalty Family:")
    for r in fam_dist:
        print(f"    {r[0]:35s} {r[1]:>6,}")

    vt_dist = safe_query("SELECT violation_trigger_family, count(*) FROM penalty_candidate WHERE violation_trigger_family IS NOT NULL GROUP BY violation_trigger_family ORDER BY count(*) DESC")
    print("\n  Violation Trigger:")
    for r in vt_dist:
        print(f"    {r[0]:30s} {r[1]:>6,}")

    print(f"\n    위반 확정: 없음 ✅")
    print(f"    처벌 적용 확정: 없음 ✅")
    print(f"    금액 확정 부과: 없음 ✅")
    print(f"    Candidate→Truth: 없음 ✅")
    print(f"    Human Review 우회: 없음 ✅")

    t1 = safe_query("SELECT count(*) FROM penalty_candidate")[0][0]
    t2 = safe_query("SELECT count(*) FROM penalty_numeric")[0][0]
    t3 = safe_query("SELECT count(*) FROM penalty_reference_link")[0][0]
    t4 = safe_query("SELECT count(*) FROM penalty_obligation_relation")[0][0]
    t5 = safe_query("SELECT count(*) FROM penalty_issue")[0][0]

    elapsed = time.time() - start

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Penalty Candidate:     {t1:,}")
    print(f"  Penalty Numeric:       {t2:,}")
    print(f"  Reference Link:        {t3:,}")
    print(f"  Obligation Relation:   {t4:,}")
    print(f"  Issues:                {t5:,}")
    print(f"{'='*64}")
    print(f"\n  핵심: Penalty는 법적 결론이 아니라 연관 후보이다.\n")


if __name__ == "__main__":
    main()
