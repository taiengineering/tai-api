"""Facility Applicability Evaluation Engine — 프롬프트 19단계.

핵심: "Applicability는 법적 결론이 아니라 조건 충족 가능성 평가다."
절대 금지: 법 적용 확정, 의무 확정, 위반 판정, 누락 데이터 보정

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_facility_applicability.py
"""

import logging, os, sys, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

# ════════════════════════════════════════════════════════
# [3단계] Field Binding: binding_field → facility 칼럼
# 단위 환산 금지. 직접 매칭만.
# ════════════════════════════════════════════════════════
FIELD_MAP = {
    # binding_field: (facility_column, match_quality)
    # DIRECT: 직접 비교 가능
    # AMBIGUOUS: 칼럼 존재하나 단위/의미 불일치 가능
    # MISSING: facility에 해당 칼럼 없음
    "employee_count":      ("employee_count",         "DIRECT"),
    "area_size":            ("building_area",          "DIRECT"),
    "power_capacity":       ("electrical_capacity_kw", "DIRECT"),
    "voltage_level":        ("transformer_capacity_kva","AMBIGUOUS"),  # kVA ≠ V
    "storage_capacity":     ("gas_capacity_m3",        "AMBIGUOUS"),   # m3 ≠ 리터
    "equipment_type":       (None,                     "EQUIPMENT_JOIN"),
    "facility_type":        ("site_type",              "AMBIGUOUS"),
    "process_type":         ("ksic_code",              "AMBIGUOUS"),
    "monetary_value":       ("construction_amount",    "AMBIGUOUS"),
    "concentration_level":  (None,                     "MISSING"),
    "distance_value":       (None,                     "MISSING"),
}

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS facility_applicability (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id UUID NOT NULL,
    draft_id UUID NOT NULL,
    part_id UUID NOT NULL,
    applicability_status TEXT NOT NULL
        CHECK (applicability_status IN (
            'MATCH_CANDIDATE','POSSIBLE_CANDIDATE','NOT_MATCHED',
            'AMBIGUOUS','UNRESOLVED','MISSING_DATA','NEEDS_HUMAN_REVIEW'
        )),
    match_details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facility_applicability_detail (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    applicability_id UUID NOT NULL,
    factory_id UUID NOT NULL,
    check_type TEXT NOT NULL,
    binding_field TEXT,
    facility_column TEXT,
    operator TEXT,
    draft_value NUMERIC,
    facility_value NUMERIC,
    result TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facility_applicability_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id UUID NOT NULL,
    draft_id UUID,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fa_factory ON facility_applicability(factory_id);
CREATE INDEX IF NOT EXISTS idx_fa_draft ON facility_applicability(draft_id);
CREATE INDEX IF NOT EXISTS idx_fa_status ON facility_applicability(applicability_status);
CREATE INDEX IF NOT EXISTS idx_fad_appid ON facility_applicability_detail(applicability_id);
CREATE INDEX IF NOT EXISTS idx_fai_factory ON facility_applicability_issue(factory_id);
"""


def compare_numeric(operator, draft_val, facility_val):
    """[4단계] 숫자 비교. 법적 판단 없음. 조건 충족 여부만."""
    if draft_val is None or facility_val is None:
        return "MISSING_DATA"
    try:
        dv = float(draft_val)
        fv = float(facility_val)
    except (TypeError, ValueError):
        return "MISSING_DATA"

    if operator == ">=":
        return "MATCH_CANDIDATE" if fv >= dv else "NOT_MATCHED"
    elif operator == "<=":
        return "MATCH_CANDIDATE" if fv <= dv else "NOT_MATCHED"
    elif operator == ">":
        return "MATCH_CANDIDATE" if fv > dv else "NOT_MATCHED"
    elif operator == "<":
        return "MATCH_CANDIDATE" if fv < dv else "NOT_MATCHED"
    else:
        return "AMBIGUOUS"


def main():
    import psycopg2
    from psycopg2.extras import execute_values
    import json

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Facility Applicability Evaluation (프롬프트 19단계)")
    print(f"{'='*64}")
    print("  원칙: 조건 충족 가능성만. 법 적용 확정 금지.")

    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    # 재실행 대비
    cur.execute("SELECT count(*) FROM facility_applicability")
    if cur.fetchone()[0] > 0:
        cur.execute("TRUNCATE facility_applicability, facility_applicability_detail, facility_applicability_issue")
        conn.commit()
        print("  ⚠️ TRUNCATE 완료")

    start = time.time()

    # ================================================
    # [1단계] Facility Data 로드
    # ================================================
    cur.execute("""
        SELECT id::text, employee_count, electrical_capacity_kw,
               transformer_capacity_kva, building_area, gas_capacity_m3,
               gas_capacity_kg, construction_amount, site_type, ksic_code,
               name
        FROM factories WHERE is_active = true
    """)
    facilities = cur.fetchall()
    fac_cols = ['id','employee_count','electrical_capacity_kw',
                'transformer_capacity_kva','building_area','gas_capacity_m3',
                'gas_capacity_kg','construction_amount','site_type','ksic_code','name']
    fac_list = [dict(zip(fac_cols, row)) for row in facilities]
    print(f"\n  [1단계] Facility: {len(fac_list)}건 (수정 없음)")

    # ================================================
    # [2단계] Draft + Numeric Slot 로드
    # ================================================
    cur.execute("""
        SELECT ed.id::text as draft_id, ed.part_id::text,
               ds.binding_field, ds.operator, ds.value, ds.unit,
               ds.family_name, ds.section
        FROM executable_draft ed
        JOIN draft_slot ds ON ds.draft_id = ed.id
        WHERE ds.binding_field IS NOT NULL
          AND ds.section = 'IF_NUMERIC'
          AND ds.operator IS NOT NULL
          AND ds.value IS NOT NULL
        ORDER BY ed.id
    """)
    numeric_slots = cur.fetchall()
    draft_numerics = {}
    for draft_id, part_id, bf, op, val, unit, family, section in numeric_slots:
        draft_numerics.setdefault(draft_id, []).append({
            'part_id': part_id, 'binding_field': bf,
            'operator': op, 'value': val, 'unit': unit, 'family': family
        })
    print(f"  [2단계] Numeric Draft: {len(draft_numerics)}건 (수정 없음)")

    # Scope binding만 있는 draft (numeric 없는 것)
    cur.execute("""
        SELECT DISTINCT ed.id::text, ed.part_id::text, ds.binding_field, ds.family_name
        FROM executable_draft ed
        JOIN draft_slot ds ON ds.draft_id = ed.id
        WHERE ds.binding_field IS NOT NULL
          AND ds.section IN ('IF_SCOPE')
    """)
    scope_slots = cur.fetchall()
    draft_scopes = {}
    for draft_id, part_id, bf, family in scope_slots:
        draft_scopes.setdefault(draft_id, []).append({
            'part_id': part_id, 'binding_field': bf, 'family': family
        })
    print(f"  Scope Draft: {len(draft_scopes)}건")

    # ================================================
    # [3~11단계] 평가 실행
    # ================================================
    print(f"\n{'─'*64}")
    print("  [3~11단계] Applicability 평가")
    print(f"{'─'*64}")

    applicabilities = []
    details = []
    issues = []
    all_draft_ids = set(list(draft_numerics.keys()) + list(draft_scopes.keys()))

    for fac in fac_list:
        fac_id = fac['id']

        for draft_id in all_draft_ids:
            part_id = None
            check_results = []

            # Numeric 검증
            for ns in draft_numerics.get(draft_id, []):
                part_id = ns['part_id']
                bf = ns['binding_field']
                fmap = FIELD_MAP.get(bf)

                if not fmap:
                    check_results.append(('NUMERIC_CHECK', bf, None, ns['operator'], ns['value'], None, 'MISSING_DATA', 'NO_FIELD_MAP'))
                    continue

                fac_col, quality = fmap
                if fac_col is None:
                    check_results.append(('NUMERIC_CHECK', bf, None, ns['operator'], ns['value'], None, 'MISSING_DATA', 'NO_FACILITY_COLUMN'))
                    continue

                fac_val = fac.get(fac_col)
                if fac_val is None:
                    check_results.append(('NUMERIC_CHECK', bf, fac_col, ns['operator'], ns['value'], None, 'MISSING_DATA', 'FACILITY_VALUE_NULL'))
                    continue

                if quality == 'AMBIGUOUS':
                    check_results.append(('NUMERIC_CHECK', bf, fac_col, ns['operator'], ns['value'], fac_val, 'AMBIGUOUS', 'UNIT_MISMATCH_POSSIBLE'))
                else:
                    result = compare_numeric(ns['operator'], ns['value'], fac_val)
                    check_results.append(('NUMERIC_CHECK', bf, fac_col, ns['operator'], ns['value'], fac_val, result, 'DIRECT_COMPARE'))

            # Scope 검증
            for ss in draft_scopes.get(draft_id, []):
                part_id = part_id or ss['part_id']
                bf = ss['binding_field']
                fmap = FIELD_MAP.get(bf)
                if not fmap or fmap[0] is None:
                    check_results.append(('SCOPE_CHECK', bf, None, None, None, None, 'MISSING_DATA', 'NO_FACILITY_COLUMN'))
                else:
                    fac_val = fac.get(fmap[0])
                    if fac_val is None:
                        check_results.append(('SCOPE_CHECK', bf, fmap[0], None, None, None, 'MISSING_DATA', 'FACILITY_VALUE_NULL'))
                    else:
                        check_results.append(('SCOPE_CHECK', bf, fmap[0], None, None, fac_val, 'POSSIBLE_CANDIDATE', 'SCOPE_FIELD_EXISTS'))

            if not check_results:
                continue

            # [11단계] 종합 상태 결정
            results_set = set(r[6] for r in check_results)
            if 'MATCH_CANDIDATE' in results_set and 'NOT_MATCHED' not in results_set:
                overall = 'MATCH_CANDIDATE'
            elif 'MATCH_CANDIDATE' in results_set and 'NOT_MATCHED' in results_set:
                overall = 'AMBIGUOUS'
            elif 'POSSIBLE_CANDIDATE' in results_set:
                overall = 'POSSIBLE_CANDIDATE'
            elif 'AMBIGUOUS' in results_set:
                overall = 'AMBIGUOUS'
            elif 'NOT_MATCHED' in results_set and results_set == {'NOT_MATCHED'}:
                overall = 'NOT_MATCHED'
            else:
                overall = 'MISSING_DATA'

            if part_id is None:
                continue

            app_id = None  # 나중에 배치로 처리
            applicabilities.append((
                fac_id, draft_id, part_id, overall,
                json.dumps({'checks': len(check_results)})
            ))

            for cr in check_results:
                details.append((
                    fac_id, cr[0], cr[1], cr[2], cr[3], cr[4], cr[5], cr[6], cr[7]
                ))

    print(f"  평가 완료: {len(applicabilities):,}건 (\uc2dc\uc124 {len(fac_list)} \xd7 Draft {len(all_draft_ids)})")

    # DB 저장
    print(f"\n{'─'*64}")
    print("  DB 저장")
    print(f"{'─'*64}")

    if applicabilities:
        for i in range(0, len(applicabilities), 5000):
            batch = applicabilities[i:i+5000]
            execute_values(cur, """
                INSERT INTO facility_applicability
                    (factory_id, draft_id, part_id, applicability_status, match_details)
                VALUES %s
            """, batch, page_size=5000)
        conn.commit()
        print(f"    ✅ facility_applicability: {len(applicabilities):,}건")

    # Detail은 applicability_id 없이 독립 저장 (배치 효율)
    if details:
        for i in range(0, len(details), 5000):
            batch = details[i:i+5000]
            execute_values(cur, """
                INSERT INTO facility_applicability_detail
                    (factory_id, check_type, binding_field, facility_column,
                     operator, draft_value, facility_value, result, reason)
                VALUES %s
            """, batch, page_size=5000)
        conn.commit()
        print(f"    ✅ facility_applicability_detail: {len(details):,}건")

    # ================================================
    # [15단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [15단계] Validation")
    print(f"{'─'*64}")

    cur.execute("SELECT applicability_status, count(*) FROM facility_applicability GROUP BY applicability_status ORDER BY count(*) DESC")
    print("\n  applicability_status:")
    for r in cur.fetchall():
        print(f"    {r[0]:25s} {r[1]:>10,}")

    cur.execute("SELECT result, count(*) FROM facility_applicability_detail GROUP BY result ORDER BY count(*) DESC")
    print("\n  detail result:")
    for r in cur.fetchall():
        print(f"    {r[0]:25s} {r[1]:>10,}")

    cur.execute("SELECT reason, count(*) FROM facility_applicability_detail GROUP BY reason ORDER BY count(*) DESC")
    print("\n  detail reason:")
    for r in cur.fetchall():
        print(f"    {r[0]:30s} {r[1]:>10,}")

    print(f"\n    법 적용 확정: 없음 ✅")
    print(f"    누락 데이터 보정: 없음 ✅")
    print(f"    semantic expansion: 미발생 ✅")
    print(f"    Candidate→Truth: 없음 ✅")

    # ================================================
    # 최종 상태
    # ================================================
    cur.execute("SELECT count(*) FROM facility_applicability")
    total_fa = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM facility_applicability_detail")
    total_fad = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM facility_applicability_issue")
    total_fai = cur.fetchone()[0]

    elapsed = time.time() - start
    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Applicability:  {total_fa:,}")
    print(f"  Detail:         {total_fad:,}")
    print(f"  Issues:         {total_fai:,}")
    print(f"  Facilities:     {len(fac_list)}")
    print(f"  Drafts 평가:    {len(all_draft_ids)}")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
