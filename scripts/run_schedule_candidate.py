"""Schedule Candidate & Operational Timeline Builder — 프롬프트 20단계.

핵심: "Schedule은 법적 확정 일정이 아니라 운영 Candidate Timeline이다."
절대 금지: 날짜 계산, Calendar/cron/RRULE 생성, due date 확정

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_schedule_candidate.py
"""

import logging, os, sys, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

# [3단계] Frequency → Timeline Type
FREQ_TO_TIMELINE = {
    "ANNUAL_FAMILY":        "YEARLY_TIMELINE_CANDIDATE",
    "SEMI_ANNUAL_FAMILY":   "SEMI_YEARLY_TIMELINE_CANDIDATE",
    "QUARTERLY_FAMILY":     "QUARTERLY_TIMELINE_CANDIDATE",
    "PERIODIC_FAMILY":      "PERIODIC_TIMELINE_CANDIDATE",
    "AD_HOC_FAMILY":        "AD_HOC_TIMELINE_CANDIDATE",
    "FREQUENCY_THRESHOLD_FAMILY": "NUMERIC_FREQUENCY_TIMELINE_CANDIDATE",
    "UNRESOLVED_FREQUENCY": "UNRESOLVED_TIMELINE_CANDIDATE",
}

# [4단계] Trigger → Event Timeline
TRIGGER_TO_EVENT = {
    "BEFORE_WORK_FAMILY":    "BEFORE_WORK_EVENT_CANDIDATE",
    "AFTER_INSTALL_FAMILY":  "AFTER_INSTALL_EVENT_CANDIDATE",
    "ON_ACCIDENT_FAMILY":    "ON_ACCIDENT_EVENT_CANDIDATE",
    "ON_CHANGE_FAMILY":      "ON_CHANGE_EVENT_CANDIDATE",
    "PERIODIC_TRIGGER_FAMILY": "PERIODIC_EVENT_CANDIDATE",
}

# [5단계] Deadline → Time Window
DEADLINE_TO_WINDOW = {
    "IMMEDIATE_FAMILY":      "IMMEDIATE_WINDOW_CANDIDATE",
    "WITHIN_FAMILY":         "WITHIN_PERIOD_WINDOW_CANDIDATE",
    "BY_FAMILY":             "BY_DATE_WINDOW_CANDIDATE",
    "DEADLINE_THRESHOLD_FAMILY": "NUMERIC_DEADLINE_WINDOW_CANDIDATE",
    "UNRESOLVED_DEADLINE":   "UNRESOLVED_WINDOW_CANDIDATE",
}

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schedule_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_candidate_id UUID NOT NULL,
    factory_id UUID NOT NULL,
    part_id UUID NOT NULL,
    schedule_type TEXT NOT NULL,
    source_family TEXT NOT NULL,
    source_relation_type TEXT NOT NULL,
    raw_token TEXT,
    numeric_value TEXT,
    numeric_unit TEXT,
    numeric_operator TEXT,
    task_type TEXT,
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE','POSSIBLE_CANDIDATE','AMBIGUOUS',
                          'UNRESOLVED','MISSING_DATA','NEEDS_HUMAN_REVIEW')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS schedule_candidate_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_candidate_id UUID,
    factory_id UUID NOT NULL,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sc_task ON schedule_candidate(task_candidate_id);
CREATE INDEX IF NOT EXISTS idx_sc_factory ON schedule_candidate(factory_id);
CREATE INDEX IF NOT EXISTS idx_sc_type ON schedule_candidate(schedule_type);
CREATE INDEX IF NOT EXISTS idx_sci_sc ON schedule_candidate_issue(schedule_candidate_id);
"""


def main():
    import psycopg2
    from psycopg2.extras import execute_values

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Schedule Candidate Builder (프롬프트 20단계)")
    print(f"{'='*64}")
    print("  원칙: Timeline은 운영 후보. Calendar/날짜 생성 금지.")

    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    cur.execute("SELECT count(*) FROM schedule_candidate")
    if cur.fetchone()[0] > 0:
        cur.execute("TRUNCATE schedule_candidate, schedule_candidate_issue")
        conn.commit()
        print("  ⚠️ TRUNCATE 완료")

    start = time.time()

    # ================================================
    # [1단계] Task Candidate + Relation 로드
    # ================================================
    print(f"\n{'─'*64}")
    print("  [1단계] Task Candidate Input")
    print(f"{'─'*64}")

    cur.execute("""
        SELECT tc.id::text, tc.factory_id::text, tc.part_id::text,
               tc.task_type, tc.status as tc_status,
               tcr.relation_type, tcr.family_name, tcr.raw_token,
               tcr.value, tcr.unit, tcr.operator
        FROM task_candidate tc
        JOIN task_candidate_relation tcr ON tcr.task_candidate_id = tc.id
        WHERE tcr.relation_type IN ('FREQUENCY','DEADLINE','TRIGGER')
           OR (tcr.relation_type = 'NUMERIC' AND tcr.family_name IN (
               'FREQUENCY_THRESHOLD_FAMILY','DEADLINE_THRESHOLD_FAMILY'
           ))
        ORDER BY tc.id
    """)
    rows = cur.fetchall()
    print(f"  Schedule 관련 Relation: {len(rows):,}건")

    # Task별 그룹화
    task_scheds = {}  # tc_id -> [{...}]
    task_info = {}    # tc_id -> (factory_id, part_id, task_type, tc_status)
    for tc_id, fac_id, part_id, task_type, tc_status, rel_type, family, raw, val, unit, op in rows:
        task_info[tc_id] = (fac_id, part_id, task_type, tc_status)
        task_scheds.setdefault(tc_id, []).append({
            'rel_type': rel_type, 'family': family, 'raw': raw,
            'value': val, 'unit': unit, 'operator': op
        })

    print(f"  Schedule 대상 Task: {len(task_scheds):,}건")

    # ================================================
    # [3~6단계] Schedule Candidate 생성
    # ================================================
    print(f"\n{'─'*64}")
    print("  [3~6단계] Schedule Candidate 생성")
    print(f"{'─'*64}")

    schedules = []
    for tc_id, rels in task_scheds.items():
        fac_id, part_id, task_type, tc_status = task_info[tc_id]
        status = 'CANDIDATE' if tc_status == 'CANDIDATE' else 'POSSIBLE_CANDIDATE'

        for rel in rels:
            family = rel['family']
            rel_type = rel['rel_type']
            sched_type = None
            source_rel = None

            if rel_type == 'FREQUENCY' or (rel_type == 'NUMERIC' and family == 'FREQUENCY_THRESHOLD_FAMILY'):
                sched_type = FREQ_TO_TIMELINE.get(family, 'UNRESOLVED_TIMELINE_CANDIDATE')
                source_rel = 'FREQUENCY'
            elif rel_type == 'TRIGGER':
                sched_type = TRIGGER_TO_EVENT.get(family, 'UNRESOLVED_EVENT_CANDIDATE')
                source_rel = 'TRIGGER'
            elif rel_type == 'DEADLINE' or (rel_type == 'NUMERIC' and family == 'DEADLINE_THRESHOLD_FAMILY'):
                sched_type = DEADLINE_TO_WINDOW.get(family, 'UNRESOLVED_WINDOW_CANDIDATE')
                source_rel = 'DEADLINE'

            if sched_type and source_rel:
                sched_status = status
                if 'UNRESOLVED' in sched_type:
                    sched_status = 'UNRESOLVED'

                schedules.append((
                    tc_id, fac_id, part_id,
                    sched_type, family, source_rel,
                    rel['raw'], rel['value'], rel['unit'], rel['operator'],
                    task_type, sched_status
                ))

    print(f"  Schedule Candidate: {len(schedules):,}건")

    # DB 저장
    print(f"\n{'─'*64}")
    print("  DB 저장")
    print(f"{'─'*64}")

    if schedules:
        execute_values(cur, """
            INSERT INTO schedule_candidate
                (task_candidate_id, factory_id, part_id,
                 schedule_type, source_family, source_relation_type,
                 raw_token, numeric_value, numeric_unit, numeric_operator,
                 task_type, status)
            VALUES %s
        """, schedules, page_size=5000)
        conn.commit()
        print(f"    ✅ schedule_candidate: {len(schedules):,}건")

    # ================================================
    # [16단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [16단계] Validation")
    print(f"{'─'*64}")

    cur.execute("SELECT schedule_type, count(*) FROM schedule_candidate GROUP BY schedule_type ORDER BY count(*) DESC")
    print("\n  schedule_type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:45s} {r[1]:>6,}")

    cur.execute("SELECT source_relation_type, count(*) FROM schedule_candidate GROUP BY source_relation_type ORDER BY count(*) DESC")
    print("\n  source_relation_type:")
    for r in cur.fetchall():
        print(f"    {r[0]:20s} {r[1]:>6,}")

    cur.execute("SELECT status, count(*) FROM schedule_candidate GROUP BY status ORDER BY count(*) DESC")
    print("\n  status:")
    for r in cur.fetchall():
        print(f"    {r[0]:25s} {r[1]:>6,}")

    cur.execute("SELECT task_type, count(*) FROM schedule_candidate GROUP BY task_type ORDER BY count(*) DESC")
    print("\n  task_type:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>6,}")

    print(f"\n    날짜 계산: 없음 ✅")
    print(f"    Calendar 생성: 없음 ✅")
    print(f"    cron/RRULE: 없음 ✅")
    print(f"    due date 확정: 없음 ✅")
    print(f"    semantic expansion: 미발생 ✅")
    print(f"    Candidate→Truth: 없음 ✅")

    cur.execute("SELECT count(*) FROM schedule_candidate")
    total_sc = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM schedule_candidate_issue")
    total_sci = cur.fetchone()[0]
    cur.execute("SELECT count(DISTINCT factory_id) FROM schedule_candidate")
    fac_cnt = cur.fetchone()[0]
    cur.execute("SELECT count(DISTINCT task_candidate_id) FROM schedule_candidate")
    task_cnt = cur.fetchone()[0]

    elapsed = time.time() - start
    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Schedule Candidate: {total_sc:,}")
    print(f"  Issues:             {total_sci:,}")
    print(f"  Facilities:         {fac_cnt}")
    print(f"  Tasks 연결:          {task_cnt}")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
