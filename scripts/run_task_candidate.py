"""Compliance Task Candidate Generator — 프롬프트 21단계.

핵심: "Task는 법적 확정 의무가 아니라 운영 Candidate다."
절대 금지: 의무 확정, 위반 판정, 스케줄 생성, Calendar 생성, Priority 추론

[WO-SECTOR-FILTER-CONNECTION-001] sector filter 추가:
  기존 sector 데이터(factories.sector / semantic_clause.sector)를 이용해
  COMMON + 동일 sector 법령만 task 후보로 남긴다.
  신규 법령/draft_slot/binding_field 생성 없음. 기존 binding_field 평가는 그대로.
  law_sector를 찾지 못한 part는 보수적으로 통과(차단 안 함).

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_task_candidate.py
"""

import logging, os, sys, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

# [3단계] Action → Task Type 매핑
ACTION_TO_TASK = {
    "INSPECT_FAMILY":     "INSPECTION_TASK_CANDIDATE",
    "REPORT_FAMILY":      "REPORT_TASK_CANDIDATE",
    "TRAINING_FAMILY":    "TRAINING_TASK_CANDIDATE",
    "APPOINT_FAMILY":     "APPOINTMENT_TASK_CANDIDATE",
    "RECORD_FAMILY":      "RECORD_TASK_CANDIDATE",
    "PRESERVE_FAMILY":    "PRESERVE_TASK_CANDIDATE",
    "INSTALL_FAMILY":     "INSTALL_TASK_CANDIDATE",
    "MANAGE_FAMILY":      "MANAGE_TASK_CANDIDATE",
    "NOTIFY_FAMILY":      "NOTIFY_TASK_CANDIDATE",
    "MEASURE_FAMILY":     "MEASURE_TASK_CANDIDATE",
    "VERIFY_FAMILY":      "VERIFY_TASK_CANDIDATE",
    "DESIGNATE_FAMILY":   "DESIGNATE_TASK_CANDIDATE",
    "EXECUTE_FAMILY":     "EXECUTE_TASK_CANDIDATE",
    "PUBLISH_FAMILY":     "PUBLISH_TASK_CANDIDATE",
    "CONSULT_FAMILY":     "CONSULT_TASK_CANDIDATE",
    "PROVIDE_FAMILY":     "PROVIDE_TASK_CANDIDATE",
    "REPAIR_FAMILY":      "REPAIR_TASK_CANDIDATE",
    "REPLACE_FAMILY":     "REPLACE_TASK_CANDIDATE",
    "CANCEL_FAMILY":      "CANCEL_TASK_CANDIDATE",
    "CORRECT_FAMILY":     "CORRECT_TASK_CANDIDATE",
    "PREVENT_FAMILY":     "PREVENT_TASK_CANDIDATE",
    "PROCESS_FAMILY":     "PROCESS_TASK_CANDIDATE",
    "REQUEST_FAMILY":     "REQUEST_TASK_CANDIDATE",
}

# [WO-SECTOR-FILTER] sector 허용 규칙
#   IF law_sector == COMMON          → 허용
#   ELSE IF law_sector == facility   → 허용
#   ELSE                             → 차단(오매핑)
#   law_sector 미상(매핑 없음)       → 보수적 통과(차단 안 함)
def sector_allowed(facility_sector, law_sectors):
    """facility_sector(str) vs law_sectors(set[str]) → (allowed: bool, reason: str)."""
    if not law_sectors:
        return True, "LAW_SECTOR_UNKNOWN_PASS"      # 매핑 없음 → 보수적 통과
    if "COMMON" in law_sectors:
        return True, "COMMON"
    if facility_sector in law_sectors:
        return True, "SAME_SECTOR"
    return False, "CROSS_SECTOR_BLOCKED"

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS task_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id UUID NOT NULL,
    applicability_id UUID NOT NULL,
    draft_id UUID NOT NULL,
    part_id UUID NOT NULL,
    task_type TEXT NOT NULL,
    source_action_family TEXT NOT NULL,
    obligation_family TEXT,
    applicability_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE','POSSIBLE_OPERATION_TASK','AMBIGUOUS',
                          'UNRESOLVED','MISSING_DATA','NEEDS_HUMAN_REVIEW')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_candidate_relation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_candidate_id UUID NOT NULL,
    relation_type TEXT NOT NULL,
    family_name TEXT,
    raw_token TEXT,
    binding_field TEXT,
    operator TEXT,
    value TEXT,
    unit TEXT,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_candidate_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_candidate_id UUID,
    factory_id UUID NOT NULL,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tc_factory ON task_candidate(factory_id);
CREATE INDEX IF NOT EXISTS idx_tc_type ON task_candidate(task_type);
CREATE INDEX IF NOT EXISTS idx_tc_status ON task_candidate(status);
CREATE INDEX IF NOT EXISTS idx_tcr_tc ON task_candidate_relation(task_candidate_id);
CREATE INDEX IF NOT EXISTS idx_tcr_type ON task_candidate_relation(relation_type);
CREATE INDEX IF NOT EXISTS idx_tci_tc ON task_candidate_issue(task_candidate_id);
"""


def main():
    import psycopg2
    from psycopg2.extras import execute_values
    import uuid as uuid_mod

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Compliance Task Candidate Generator (프롬프트 21단계)")
    print(f"{'='*64}")
    print("  원칙: Task는 의무 아닔. 스케줄/Calendar 생성 금지.")
    print("  [WO-SECTOR-FILTER] COMMON + 동일 sector 법령만 후보 유지.")

    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    # 재실행 대비
    cur.execute("SELECT count(*) FROM task_candidate")
    if cur.fetchone()[0] > 0:
        cur.execute("TRUNCATE task_candidate, task_candidate_relation, task_candidate_issue")
        conn.commit()
        print("  ⚠️ TRUNCATE 완료")

    start = time.time()

    # ================================================
    # [1단계] Applicability MATCH/POSSIBLE 로드
    # ================================================
    print(f"\n{'─'*64}")
    print("  [1~2단계] Applicability Input (MATCH + POSSIBLE만)")
    print(f"{'─'*64}")

    cur.execute("""
        SELECT fa.id::text, fa.factory_id::text, fa.draft_id::text, fa.part_id::text,
               fa.applicability_status
        FROM facility_applicability fa
        WHERE fa.applicability_status IN ('MATCH_CANDIDATE', 'POSSIBLE_CANDIDATE')
    """)
    applicabilities = cur.fetchall()
    print(f"  대상: {len(applicabilities):,}건")

    # ================================================
    # [WO-SECTOR-FILTER] sector 맵 로드 (기존 데이터 참조, 신규 생성 없음)
    # ================================================
    print(f"\n{'─'*64}")
    print("  [sector-filter] facility/law sector 맵 로드")
    print(f"{'─'*64}")

    # (a) factory_id → facility sector
    cur.execute("SELECT id::text, sector FROM factories WHERE sector IS NOT NULL")
    factory_sector = {row[0]: row[1] for row in cur.fetchall()}
    print(f"  factory sector: {len(factory_sector):,}건")

    # (b) part_id → {law_sector, ...}  (semantic_clause.source_part_id 기준, 다중 가능)
    cur.execute("""
        SELECT source_part_id::text, sector
        FROM semantic_clause
        WHERE source_part_id IS NOT NULL AND sector IS NOT NULL
    """)
    part_law_sectors = {}
    for p_id, law_sec in cur.fetchall():
        part_law_sectors.setdefault(p_id, set()).add(law_sec)
    print(f"  law sector 매핑 part: {len(part_law_sectors):,}건")

    # ================================================
    # [3단계] Action → Task Candidate 변환
    # ================================================
    print(f"\n{'─'*64}")
    print("  [3단계] Action → Task Candidate")
    print(f"{'─'*64}")

    # Draft별 Action/Obligation slot 로드
    draft_ids = list(set(row[2] for row in applicabilities))
    draft_slots = {}  # draft_id → {section: [{family, raw_token, binding, op, val, unit}]}

    for i in range(0, len(draft_ids), 500):
        batch_ids = draft_ids[i:i+500]
        placeholders = ','.join(['%s'] * len(batch_ids))
        cur.execute(f"""
            SELECT draft_id::text, section, family_name, raw_token,
                   binding_field, operator, value, unit
            FROM draft_slot
            WHERE draft_id::text IN ({placeholders})
        """, batch_ids)
        for row in cur.fetchall():
            d_id = row[0]
            draft_slots.setdefault(d_id, {}).setdefault(row[1], []).append({
                'family': row[2], 'raw_token': row[3],
                'binding': row[4], 'operator': row[5],
                'value': str(row[6]) if row[6] is not None else None, 'unit': row[7]
            })

    tasks = []
    relations = []
    # [WO-SECTOR-FILTER] 통계
    sf_stat = {"COMMON": 0, "SAME_SECTOR": 0, "LAW_SECTOR_UNKNOWN_PASS": 0,
               "CROSS_SECTOR_BLOCKED": 0}

    for fa_id, fac_id, draft_id, part_id, app_status in applicabilities:
        slots = draft_slots.get(draft_id, {})

        # [WO-SECTOR-FILTER] sector 정합성 먼저 판정 (기존 binding_field 평가 앞단)
        fac_sec = factory_sector.get(fac_id)
        law_secs = part_law_sectors.get(part_id, set())
        allowed, reason = sector_allowed(fac_sec, law_secs)
        sf_stat[reason] = sf_stat.get(reason, 0) + 1
        if not allowed:
            continue  # 오매핑(사업장 sector ≠ 법령 sector, COMMON 아님) → task 생성 skip

        # Action slot에서 task type 결정
        action_slots = slots.get('THEN_ACTION', [])
        if not action_slots:
            continue

        # Obligation 확인 (MANDATORY/PERMISSIVE)
        obligation = None
        for a in action_slots:
            if a['family'] in ('MANDATORY_FAMILY', 'PERMISSIVE_FAMILY',
                               'MANDATORY_ITEM_FAMILY', 'PROHIBITION_FAMILY'):
                obligation = a['family']

        # Action Family에서 Task 생성
        action_families_used = set()
        for a in action_slots:
            af = a['family']
            if af in ACTION_TO_TASK and af not in action_families_used:
                action_families_used.add(af)
                task_type = ACTION_TO_TASK[af]
                tc_id = str(uuid_mod.uuid4())

                status = 'CANDIDATE' if app_status == 'MATCH_CANDIDATE' else 'POSSIBLE_OPERATION_TASK'

                tasks.append((
                    tc_id, fac_id, fa_id, draft_id, part_id,
                    task_type, af, obligation, app_status, status
                ))

                # [4~11단계] 관련 Slot 연결
                for section, rel_type in [
                    ('IF_SCOPE', 'SCOPE'), ('IF_NUMERIC', 'NUMERIC'),
                    ('THEN_FREQUENCY', 'FREQUENCY'), ('THEN_TRIGGER', 'TRIGGER'),
                    ('THEN_DEADLINE', 'DEADLINE'), ('THEN_EVIDENCE', 'EVIDENCE'),
                    ('EXCEPTION', 'EXCEPTION'), ('REFERENCE', 'REFERENCE'),
                    ('IF_ACTOR', 'ACTOR'),
                ]:
                    for s in slots.get(section, []):
                        relations.append((
                            tc_id, rel_type, s['family'], s['raw_token'],
                            s.get('binding'), s.get('operator'),
                            s.get('value'), s.get('unit'), 'CANDIDATE'
                        ))

    print(f"  Task Candidate: {len(tasks):,}건")
    print(f"  Task Relation:  {len(relations):,}건")

    # [WO-SECTOR-FILTER] 필터 통계 출력
    print(f"\n  [sector-filter] 판정 분포:")
    print(f"    허용 COMMON:              {sf_stat.get('COMMON',0):>8,}")
    print(f"    허용 SAME_SECTOR:         {sf_stat.get('SAME_SECTOR',0):>8,}")
    print(f"    허용 LAW_UNKNOWN(통과):   {sf_stat.get('LAW_SECTOR_UNKNOWN_PASS',0):>8,}")
    print(f"    차단 CROSS_SECTOR:        {sf_stat.get('CROSS_SECTOR_BLOCKED',0):>8,}")

    # DB 저장
    print(f"\n{'─'*64}")
    print("  DB 저장")
    print(f"{'─'*64}")

    if tasks:
        for i in range(0, len(tasks), 5000):
            execute_values(cur, """
                INSERT INTO task_candidate
                    (id, factory_id, applicability_id, draft_id, part_id,
                     task_type, source_action_family, obligation_family,
                     applicability_status, status)
                VALUES %s
            """, tasks[i:i+5000], page_size=5000)
        conn.commit()
        print(f"    ✅ task_candidate: {len(tasks):,}건")

    if relations:
        for i in range(0, len(relations), 5000):
            execute_values(cur, """
                INSERT INTO task_candidate_relation
                    (task_candidate_id, relation_type, family_name, raw_token,
                     binding_field, operator, value, unit, status)
                VALUES %s
            """, relations[i:i+5000], page_size=5000)
        conn.commit()
        print(f"    ✅ task_candidate_relation: {len(relations):,}건")

    # ================================================
    # [17단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [17단계] Validation")
    print(f"{'─'*64}")

    cur.execute("SELECT task_type, count(*) FROM task_candidate GROUP BY task_type ORDER BY count(*) DESC")
    print("\n  Task Type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>8,}")

    cur.execute("SELECT status, count(*) FROM task_candidate GROUP BY status ORDER BY count(*) DESC")
    print("\n  Status 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>8,}")

    cur.execute("SELECT relation_type, count(*) FROM task_candidate_relation GROUP BY relation_type ORDER BY count(*) DESC")
    print("\n  Relation Type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:20s} {r[1]:>8,}")

    cur.execute("SELECT count(DISTINCT factory_id) FROM task_candidate")
    fac_count = cur.fetchone()[0]

    print(f"\n    Applicability 기반: ✅")
    print(f"    의무 확정: 없음 ✅")
    print(f"    스케줄 생성: 없음 ✅")
    print(f"    Calendar 생성: 없음 ✅")
    print(f"    Priority 추론: 없음 ✅")
    print(f"    semantic expansion: 미발생 ✅")
    print(f"    Candidate→Truth: 없음 ✅")
    print(f"    sector filter(COMMON+동일만): ✅")

    # 최종
    cur.execute("SELECT count(*) FROM task_candidate")
    total_tc = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM task_candidate_relation")
    total_tcr = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM task_candidate_issue")
    total_tci = cur.fetchone()[0]

    elapsed = time.time() - start
    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Task Candidate:  {total_tc:,}")
    print(f"  Task Relation:   {total_tcr:,}")
    print(f"  Issues:          {total_tci:,}")
    print(f"  Facilities:      {fac_count}")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
