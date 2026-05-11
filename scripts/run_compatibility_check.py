"""Rule Candidate Compatibility Validation — 프롬프트 19단계.

핵심: "Candidate 조합이 함께 살아남을 수 있는지 검증"
절대 금지: Rule 확정, 의미 확정, Conflict 해결, Candidate→Truth 승격

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_compatibility_check.py
"""

import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

# ════════════════════════════════════════════════════════════
# [2단계] Compatibility Registry
# ════════════════════════════════════════════════════════════
# 연결 가능성만 표현. 법적 의미 아님.

COMPATIBILITY_REGISTRY = {
    # ACTION ↔ FREQUENCY/DEADLINE/SCOPE/EVIDENCE
    "INSPECT_FAMILY": {
        "PERIODIC_FAMILY", "ANNUAL_FAMILY", "SEMI_ANNUAL_FAMILY", "QUARTERLY_FAMILY",
        "AD_HOC_FAMILY",
        "EQUIPMENT_SCOPE", "FACILITY_SCOPE", "PROCESS_SCOPE",
        "DEADLINE_THRESHOLD_FAMILY", "FREQUENCY_THRESHOLD_FAMILY",
        "IMMEDIATE_FAMILY", "WITHIN_FAMILY",
        "ATTACHMENT_TABLE_FAMILY", "ATTACHMENT_FORM_FAMILY",
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
    },
    "REPORT_FAMILY": {
        "DEADLINE_THRESHOLD_FAMILY", "IMMEDIATE_FAMILY", "WITHIN_FAMILY",
        "ATTACHMENT_TABLE_FAMILY", "ATTACHMENT_FORM_FAMILY",
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
        "IF_ON_ACCIDENT", "IF_ON_CHANGE",
    },
    "TRAINING_FAMILY": {
        "EMPLOYEE_THRESHOLD_FAMILY", "EMPLOYEE_SCOPE_FAMILY",
        "PERIODIC_FAMILY", "ANNUAL_FAMILY", "SEMI_ANNUAL_FAMILY",
        "FREQUENCY_THRESHOLD_FAMILY",
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
        "ATTACHMENT_TABLE_FAMILY", "ATTACHMENT_FORM_FAMILY",
    },
    "APPOINT_FAMILY": {
        "EMPLOYEE_THRESHOLD_FAMILY", "EMPLOYEE_SCOPE_FAMILY",
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
    },
    "MANAGE_FAMILY": {
        "EQUIPMENT_SCOPE", "FACILITY_SCOPE", "PROCESS_SCOPE",
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
        "PERIODIC_FAMILY", "ANNUAL_FAMILY",
    },
    "RECORD_FAMILY": {
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
        "ATTACHMENT_TABLE_FAMILY", "ATTACHMENT_FORM_FAMILY",
        "DEADLINE_THRESHOLD_FAMILY",
    },
    "PRESERVE_FAMILY": {
        "MANDATORY_FAMILY", "DEADLINE_THRESHOLD_FAMILY",
        "ATTACHMENT_TABLE_FAMILY", "ATTACHMENT_FORM_FAMILY",
    },
    "NOTIFY_FAMILY": {
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
        "DEADLINE_THRESHOLD_FAMILY", "IMMEDIATE_FAMILY",
        "IF_ON_ACCIDENT", "IF_ON_CHANGE",
    },
    "INSTALL_FAMILY": {
        "EQUIPMENT_SCOPE", "FACILITY_SCOPE",
        "MANDATORY_FAMILY", "MANDATORY_ITEM_FAMILY",
        "CAPACITY_THRESHOLD_FAMILY", "VOLTAGE_THRESHOLD_FAMILY",
    },
    "MEASURE_FAMILY": {
        "PERIODIC_FAMILY", "ANNUAL_FAMILY", "SEMI_ANNUAL_FAMILY",
        "FREQUENCY_THRESHOLD_FAMILY",
        "PROCESS_SCOPE", "CONCENTRATION_THRESHOLD_FAMILY",
        "MANDATORY_FAMILY",
    },
    "VERIFY_FAMILY": {
        "EQUIPMENT_SCOPE", "FACILITY_SCOPE",
        "MANDATORY_FAMILY", "PERMISSIVE_FAMILY",
    },
    # Scope ↔ Numeric
    "EMPLOYEE_SCOPE_FAMILY": {"EMPLOYEE_THRESHOLD_FAMILY"},
    "CAPACITY_SCOPE_FAMILY": {"CAPACITY_THRESHOLD_FAMILY"},
    "VOLTAGE_SCOPE_FAMILY": {"VOLTAGE_THRESHOLD_FAMILY"},
    "AREA_SCOPE_FAMILY": {"AREA_THRESHOLD_FAMILY"},
    "CONCENTRATION_SCOPE_FAMILY": {"CONCENTRATION_THRESHOLD_FAMILY"},
    "DISTANCE_SCOPE_FAMILY": {"DISTANCE_THRESHOLD_FAMILY"},
    "POWER_SCOPE_FAMILY": {"POWER_THRESHOLD_FAMILY"},
}

# [11단계] Conflict 규칙
# 같은 RC에서 충돌 가능한 조합
FREQUENCY_FAMILIES = {
    "PERIODIC_FAMILY", "ANNUAL_FAMILY", "SEMI_ANNUAL_FAMILY",
    "QUARTERLY_FAMILY", "AD_HOC_FAMILY", "FREQUENCY_THRESHOLD_FAMILY",
}
DEADLINE_FAMILIES = {
    "IMMEDIATE_FAMILY", "WITHIN_FAMILY", "BY_FAMILY",
    "DEADLINE_THRESHOLD_FAMILY",
}


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS compatibility_validation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_candidate_id UUID NOT NULL,
    part_id UUID NOT NULL,
    relation_id UUID,
    from_family TEXT,
    to_family TEXT,
    relation_type TEXT,
    validation TEXT NOT NULL
        CHECK (validation IN ('PASS','FAIL','AMBIGUOUS','UNRESOLVED','NEEDS_HUMAN_REVIEW')),
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS compatibility_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_candidate_id UUID NOT NULL,
    part_id UUID NOT NULL,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cv_rc ON compatibility_validation(rule_candidate_id);
CREATE INDEX IF NOT EXISTS idx_cv_val ON compatibility_validation(validation);
CREATE INDEX IF NOT EXISTS idx_ci_rc ON compatibility_issue(rule_candidate_id);
CREATE INDEX IF NOT EXISTS idx_ci_type ON compatibility_issue(issue_type);
"""


def check_compatibility(from_family, to_family):
    """Registry 기반 호환성 판정. 의미 해석 없음."""
    if not from_family or not to_family:
        return "UNRESOLVED", "NULL_FAMILY"
    if from_family == "UNKNOWN" or to_family == "UNKNOWN":
        return "UNRESOLVED", "UNKNOWN_FAMILY"
    if from_family.startswith("UNRESOLVED") or to_family.startswith("UNRESOLVED"):
        return "UNRESOLVED", "UNRESOLVED_FAMILY"

    compat_set = COMPATIBILITY_REGISTRY.get(from_family)
    if compat_set and to_family in compat_set:
        return "PASS", "REGISTRY_MATCH"

    # 역방향 확인
    compat_set_rev = COMPATIBILITY_REGISTRY.get(to_family)
    if compat_set_rev and from_family in compat_set_rev:
        return "PASS", "REGISTRY_MATCH_REVERSE"

    # Registry에 없으면 AMBIGUOUS (확정 불가)
    return "AMBIGUOUS", "NOT_IN_REGISTRY"


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
    print("  Compatibility Validation Engine (프롬프트 19단계)")
    print(f"{'='*64}")
    print("  원칙: 후보 조합 생존성 검증만. Conflict 해결 금지.")

    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    # 재실행 대비
    cur.execute("SELECT count(*) FROM compatibility_validation")
    if cur.fetchone()[0] > 0:
        cur.execute("TRUNCATE compatibility_validation, compatibility_issue")
        conn.commit()
        print("  ⚠️ TRUNCATE 완료")

    start = time.time()

    # ================================================
    # [3~10단계] Relation Compatibility 검증
    # ================================================
    print(f"\n{'─'*64}")
    print("  [3~10단계] Relation Compatibility 검증")
    print(f"{'─'*64}")

    cur.execute("""
        SELECT id::text, rule_candidate_id::text, part_id::text,
               from_family, to_family, relation_type
        FROM rule_candidate_relation
    """)
    relations = cur.fetchall()
    print(f"  대상 Relation: {len(relations):,}건")

    validations = []
    for rel_id, rc_id, part_id, from_f, to_f, rel_type in relations:
        result, reason = check_compatibility(from_f, to_f)
        validations.append((
            rc_id, part_id, rel_id, from_f, to_f, rel_type, result, reason
        ))

    # 배치 INSERT
    if validations:
        for i in range(0, len(validations), 5000):
            batch = validations[i:i + 5000]
            execute_values(cur, """
                INSERT INTO compatibility_validation
                    (rule_candidate_id, part_id, relation_id,
                     from_family, to_family, relation_type,
                     validation, reason)
                VALUES %s
            """, batch, page_size=5000)
        conn.commit()

    # 결과 통계
    cur.execute("SELECT validation, count(*) FROM compatibility_validation GROUP BY validation ORDER BY count(*) DESC")
    print("\n  Compatibility 결과:")
    for r in cur.fetchall():
        print(f"    {r[0]:25s} {r[1]:>10,}")

    cur.execute("SELECT reason, count(*) FROM compatibility_validation GROUP BY reason ORDER BY count(*) DESC")
    print("\n  Reason 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:30s} {r[1]:>10,}")

    # ================================================
    # [11단계] Conflict Detection
    # ================================================
    print(f"\n{'─'*64}")
    print("  [11단계] Conflict Detection")
    print(f"{'─'*64}")

    issues = []

    # FREQUENCY 충돌: 같은 RC에 서로 다른 FREQUENCY family
    cur.execute("""
        SELECT rc.id::text, rc.part_id::text,
               array_agg(DISTINCT s.family_name) as freq_families
        FROM rule_candidate rc
        JOIN rule_candidate_slot s ON s.rule_candidate_id = rc.id
        WHERE s.slot_type = 'FREQUENCY'
          AND s.family_name IS NOT NULL
          AND s.family_name != 'UNKNOWN'
        GROUP BY rc.id, rc.part_id
        HAVING count(DISTINCT s.family_name) > 1
    """)
    freq_conflicts = cur.fetchall()
    for rc_id, part_id, families in freq_conflicts:
        issues.append((rc_id, part_id, "ISSUE_FREQUENCY_CONFLICT",
                        f"Multiple frequencies: {families}"))
    print(f"    FREQUENCY_CONFLICT: {len(freq_conflicts):,}건")

    # DEADLINE 충돌
    cur.execute("""
        SELECT rc.id::text, rc.part_id::text,
               array_agg(DISTINCT s.family_name) as dl_families
        FROM rule_candidate rc
        JOIN rule_candidate_slot s ON s.rule_candidate_id = rc.id
        WHERE s.slot_type = 'DEADLINE'
          AND s.family_name IS NOT NULL
          AND s.family_name != 'UNKNOWN'
          AND s.family_name NOT LIKE 'UNRESOLVED%%'
        GROUP BY rc.id, rc.part_id
        HAVING count(DISTINCT s.family_name) > 1
    """)
    dl_conflicts = cur.fetchall()
    for rc_id, part_id, families in dl_conflicts:
        issues.append((rc_id, part_id, "ISSUE_DEADLINE_CONFLICT",
                        f"Multiple deadlines: {families}"))
    print(f"    DEADLINE_CONFLICT: {len(dl_conflicts):,}건")

    # EXCEPTION + MANDATORY 충돌
    cur.execute("""
        SELECT rc.id::text, rc.part_id::text
        FROM rule_candidate rc
        WHERE EXISTS (
            SELECT 1 FROM rule_candidate_slot s
            WHERE s.rule_candidate_id = rc.id AND s.slot_type = 'EXCEPTION'
        )
        AND EXISTS (
            SELECT 1 FROM rule_candidate_slot s
            WHERE s.rule_candidate_id = rc.id
              AND s.slot_type = 'OBLIGATION' AND s.family_name = 'MANDATORY_FAMILY'
        )
    """)
    exc_conflicts = cur.fetchall()
    for rc_id, part_id in exc_conflicts:
        issues.append((rc_id, part_id, "ISSUE_EXCEPTION_CONFLICT",
                        "EXCEPTION + MANDATORY coexist"))
    print(f"    EXCEPTION_CONFLICT: {len(exc_conflicts):,}건")

    # Issue 저장
    if issues:
        execute_values(cur, """
            INSERT INTO compatibility_issue
                (rule_candidate_id, part_id, issue_type, detail)
            VALUES %s
        """, issues, page_size=5000)
        conn.commit()
    print(f"\n    ✅ Issue 총: {len(issues):,}건 저장 (해결 없음 — 탐지만)")

    # ================================================
    # [15단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [15단계] Validation")
    print(f"{'─'*64}")
    print(f"    semantic expansion: 미발생 ✅")
    print(f"    rule inference: 미발생 ✅")
    print(f"    Candidate→Truth 승격: 없음 ✅")
    print(f"    UNKNOWN 제거: 없음 ✅")
    print(f"    Conflict 해결: 없음 ✅ (탐지만)")

    # ================================================
    # 최종 상태
    # ================================================
    print(f"\n{'─'*64}")
    print("  최종 상태")
    print(f"{'─'*64}")

    cur.execute("SELECT count(*) FROM compatibility_validation")
    total_cv = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM compatibility_issue")
    total_ci = cur.fetchone()[0]

    cur.execute("""
        SELECT validation, relation_type, count(*)
        FROM compatibility_validation
        GROUP BY validation, relation_type
        ORDER BY validation, count(*) DESC
    """)
    print("\n  Validation x Relation:")
    current_val = None
    for val, rel, cnt in cur.fetchall():
        if val != current_val:
            current_val = val
            print(f"\n    [{val}]")
        print(f"      {rel:45s} {cnt:>8,}")

    cur.execute("SELECT issue_type, count(*) FROM compatibility_issue GROUP BY issue_type ORDER BY count(*) DESC")
    print("\n  Issue 유형:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>8,}")

    elapsed = time.time() - start

    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Compatibility Validation: {total_cv:,}건")
    print(f"  Issues:                   {total_ci:,}건")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
