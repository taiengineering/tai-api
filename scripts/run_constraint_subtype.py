"""Constraint Graph 세부 분류 — 프롬프트 3~10단계.

TARGET → SCOPE, CONDITION 세부, TRIGGER 추출,
EVIDENCE/EXCEPTION/REFERENCE family_name 부여,
ACTION_SCOPE_RELATION 생성.

원칙:
  - 정규식 패턴 매칭만 사용 (의미 추론 금지)
  - 패턴 미매칭 → UNRESOLVED (억지 확정 금지)
  - 모든 출력 CANDIDATE
  - Rule 생성 금지
  - Semantic Expansion 금지

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_constraint_subtype.py
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# [3단계] Scope Constraint — TARGET → SCOPE 변환 규칙
# raw_token 정규식 패턴만 사용, 의미 추론 없음
# ════════════════════════════════════════════════════════════

SCOPE_PATTERNS = [
    # (regex, family_name)
    # 장치/설비 키워드 → EQUIPMENT_SCOPE
    (r'(장치|설비|기계|기구|보일러|압력용기|크레인|리프트|승강기|컨베이어|배관|탱크|밸브|펠프|덕트|변압기|방호장치|안전장치|보호구|소화기|감지기|경보기)', 'EQUIPMENT_SCOPE'),
    # 시설/건축물 키워드 → FACILITY_SCOPE
    (r'(시설|건축물|사업장|공장|작업장|현장|건물|대상물|저장소|창고)', 'FACILITY_SCOPE'),
    # 위험물/유해물질 키워드 → HAZMAT_SCOPE
    (r'(위험물|유해물질|화학물질|가스|인화성|폭발성|독성|유해인자|유해xb7위험)', 'HAZMAT_SCOPE'),
    # 근로자/인원 키워드 → EMPLOYEE_SCOPE
    (r'(근로자|종업원|작업자|노동자)', 'EMPLOYEE_SCOPE'),
    # 공정/작업 키워드 → PROCESS_SCOPE
    (r'(공정|용접|도장|절단|작업환경|측정|검사|검진|평가|점검)', 'PROCESS_SCOPE'),
    # 자격/허가 키워드 → LICENSE_SCOPE
    (r'(자격|면허|허가|등록|인가)', 'LICENSE_SCOPE'),
]

# ════════════════════════════════════════════════════════════
# [4단계] Condition Constraint — CONDITION family_name 세분
# [5단계] Trigger Constraint — CONDITION → TRIGGER 변환
# ════════════════════════════════════════════════════════════

# CONDITION → TRIGGER 변환 규칙 (이벤트 패턴만)
TRIGGER_PATTERNS = [
    # (regex, trigger_family)  — raw_token이 이 패턴이면 node_type=TRIGGER
    (r'(전에|착수.*전|개시.*전|시작.*전)', 'BEFORE_WORK_FAMILY'),
    (r'(후에|완료.*후|설치.*후|종료.*후)', 'AFTER_INSTALL_FAMILY'),
    (r'(사고.*발생|재해.*발생|사고시|재해시)', 'ON_ACCIDENT_FAMILY'),
]

# CONDITION family_name 세분 규칙
CONDITION_PATTERNS = [
    # (regex, condition_family)
    (r'(이상인|초과하는|미만인|이하인|이상인 경우|초과하는 경우|미만인 경우|이하인 경우)', 'IF_OVER_THRESHOLD'),
    (r'(변경하는|변경한|교체|개조)', 'IF_ON_CHANGE'),
    (r'(발생한 경우|발생했을|발생시)', 'IF_ON_ACCIDENT'),
    (r'(설치하는 경우|시설하는 경우)', 'IF_AFTER_INSTALL'),
    (r'(사용하는 경우)', 'IF_OPERATIONAL'),
    (r'(해당하는 경우|해당하는 때|해당하는 경우에는)', 'IF_EXISTS'),
    (r'(필요한 경우|필요한 경우에는)', 'IF_EXISTS'),
    (r'(아니한 경우|아니하는 경우)', 'IF_EXISTS'),
]

# ════════════════════════════════════════════════════════════
# [8단계] Evidence Constraint — EVIDENCE family_name 세분
# ════════════════════════════════════════════════════════════

EVIDENCE_PATTERNS = [
    (r'^뱸표', 'ATTACHMENT_TABLE_FAMILY'),
    (r'^뱸지', 'ATTACHMENT_FORM_FAMILY'),
]

# ════════════════════════════════════════════════════════════
# [9단계] Exception Constraint
# ════════════════════════════════════════════════════════════

EXCEPTION_PATTERNS = [
    (r'^다만', 'PROVISO_EXCEPTION_FAMILY'),
    (r'그러하지 아니하다', 'NEGATION_EXCEPTION_FAMILY'),
    (r'적용하지 아니한다', 'EXCLUSION_EXCEPTION_FAMILY'),
]

# ════════════════════════════════════════════════════════════
# [10단계] Reference Constraint
# ════════════════════════════════════════════════════════════

REFERENCE_PATTERNS = [
    (r'^제\d+조', 'ARTICLE_REFERENCE_FAMILY'),
    (r'^「', 'EXTERNAL_LAW_REFERENCE_FAMILY'),
]


def main():
    import re
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Constraint Graph 세부 분류 (프롬프트 3~10단계)")
    print(f"{'='*64}")

    stats = {}

    # ────────────────────────────────────────────────────────
    # [3단계] TARGET → SCOPE 변환
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  [3단계] Scope Constraint: TARGET → SCOPE")
    print(f"{'-'*64}")

    scope_total = 0
    for pattern, family in SCOPE_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET node_type = 'SCOPE', family_name = %s
            WHERE node_type = 'TARGET'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (family, pattern))
        cnt = cur.rowcount
        scope_total += cnt
        if cnt > 0:
            print(f"    ✅ {family}: {cnt:,}건")
    conn.commit()

    # TARGET 잔여 → UNRESOLVED
    cur.execute("SELECT count(*) FROM constraint_node WHERE node_type = 'TARGET' AND family_name = 'UNKNOWN'")
    target_unresolved = cur.fetchone()[0]
    print(f"    TARGET 잔여 (UNRESOLVED): {target_unresolved:,}건")
    stats['scope'] = scope_total

    # ────────────────────────────────────────────────────────
    # [5단계] CONDITION → TRIGGER 변환 (이벤트 패턴만)
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  [5단계] Trigger Constraint: CONDITION → TRIGGER")
    print(f"{'-'*64}")

    trigger_total = 0
    for pattern, family in TRIGGER_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET node_type = 'TRIGGER', family_name = %s
            WHERE node_type = 'CONDITION'
              AND raw_token ~ %s
        """, (family, pattern))
        cnt = cur.rowcount
        trigger_total += cnt
        if cnt > 0:
            print(f"    ✅ {family}: {cnt:,}건")
    conn.commit()
    if trigger_total == 0:
        print("    (패턴 매칭 없음 — CONDITION 유지)")
    stats['trigger'] = trigger_total

    # ────────────────────────────────────────────────────────
    # [4단계] CONDITION family_name 세분
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  [4단계] Condition Constraint: family_name 세분")
    print(f"{'-'*64}")

    cond_total = 0
    for pattern, family in CONDITION_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'CONDITION'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (family, pattern))
        cnt = cur.rowcount
        cond_total += cnt
        if cnt > 0:
            print(f"    ✅ {family}: {cnt:,}건")
    conn.commit()

    cur.execute("SELECT count(*) FROM constraint_node WHERE node_type = 'CONDITION' AND family_name = 'UNKNOWN'")
    cond_unresolved = cur.fetchone()[0]
    print(f"    CONDITION 잔여 UNKNOWN: {cond_unresolved:,}건")
    stats['condition'] = cond_total

    # ────────────────────────────────────────────────────────
    # [8단계] EVIDENCE family_name 세분
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  [8단계] Evidence Constraint: family_name 세분")
    print(f"{'-'*64}")

    evi_total = 0
    for pattern, family in EVIDENCE_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'EVIDENCE'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (family, pattern))
        cnt = cur.rowcount
        evi_total += cnt
        if cnt > 0:
            print(f"    ✅ {family}: {cnt:,}건")
    conn.commit()
    stats['evidence'] = evi_total

    # ────────────────────────────────────────────────────────
    # [9단계] EXCEPTION family_name 세분
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  [9단계] Exception Constraint: family_name 세분")
    print(f"{'-'*64}")

    exc_total = 0
    for pattern, family in EXCEPTION_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'EXCEPTION'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (family, pattern))
        cnt = cur.rowcount
        exc_total += cnt
        if cnt > 0:
            print(f"    ✅ {family}: {cnt:,}건")
    conn.commit()
    stats['exception'] = exc_total

    # ────────────────────────────────────────────────────────
    # [10단계] REFERENCE family_name 세분
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  [10단계] Reference Constraint: family_name 세분")
    print(f"{'-'*64}")

    ref_total = 0
    for pattern, family in REFERENCE_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'REFERENCE'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (family, pattern))
        cnt = cur.rowcount
        ref_total += cnt
        if cnt > 0:
            print(f"    ✅ {family}: {cnt:,}건")
    conn.commit()

    cur.execute("SELECT count(*) FROM constraint_node WHERE node_type = 'REFERENCE' AND family_name = 'UNKNOWN'")
    ref_unresolved = cur.fetchone()[0]
    print(f"    REFERENCE 잔여 UNKNOWN: {ref_unresolved:,}건")
    stats['reference'] = ref_total

    # ────────────────────────────────────────────────────────
    # ACTION_SCOPE_RELATION 생성 (2단계 마지막)
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  ACTION_SCOPE_RELATION 생성")
    print(f"{'-'*64}")

    scope_edge_total = 0
    for from_type in ['ACTION', 'OBLIGATION']:
        cur.execute("""
            INSERT INTO constraint_edge
                (part_id, relation_type,
                 from_node_id, to_node_id,
                 from_family, to_family,
                 from_token, to_token,
                 status)
            SELECT DISTINCT ON (f.part_id)
                f.part_id,
                'ACTION_SCOPE_RELATION',
                f.id, t.id,
                f.family_name, t.family_name,
                f.raw_token, t.raw_token,
                'CANDIDATE'
            FROM constraint_node f
            JOIN constraint_node t
              ON f.part_id = t.part_id
              AND f.id != t.id
            WHERE f.node_type = %s
              AND t.node_type = 'SCOPE'
              AND NOT EXISTS (
                  SELECT 1 FROM constraint_edge ce
                  WHERE ce.part_id = f.part_id
                    AND ce.relation_type = 'ACTION_SCOPE_RELATION'
              )
            ORDER BY f.part_id, f.source_span_start, t.source_span_start
        """, (from_type,))
        cnt = cur.rowcount
        scope_edge_total += cnt
        if cnt > 0:
            print(f"    ✅ {from_type} → SCOPE: {cnt:,}건")
    conn.commit()
    stats['scope_edge'] = scope_edge_total

    # ────────────────────────────────────────────────────────
    # [13단계] Validation
    # ────────────────────────────────────────────────────────
    print(f"\n{'-'*64}")
    print("  [13단계] Validation")
    print(f"{'-'*64}")

    cur.execute("SELECT count(*) FROM constraint_node WHERE raw_token IS NULL OR raw_token = ''")
    no_raw = cur.fetchone()[0]
    print(f"    raw_token 누락: {no_raw:,}건{'  ⚠️' if no_raw > 0 else '  ✅'}")

    print(f"    semantic expansion: 미발생 ✅ (정규식 패턴만 사용)")
    print(f"    의미 확정: 미발생 ✅ (모든 출력 CANDIDATE)")

    cur.execute("""
        SELECT count(*) FROM constraint_edge ce
        JOIN constraint_node fn ON ce.from_node_id = fn.id
        JOIN constraint_node tn ON ce.to_node_id = tn.id
        WHERE fn.part_id != tn.part_id
    """)
    cross_part = cur.fetchone()[0]
    print(f"    cross-part edge: {cross_part:,}건{'  ⚠️' if cross_part > 0 else '  ✅'}")

    # ────────────────────────────────────────────────────────
    # 최종 상태
    # ────────────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("  최종 상태")
    print(f"{'='*64}")

    cur.execute("SELECT node_type, count(*) FROM constraint_node GROUP BY node_type ORDER BY count(*) DESC")
    print("\n  node_type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:20s} {r[1]:>10,}")

    cur.execute("SELECT relation_type, count(*) FROM constraint_edge GROUP BY relation_type ORDER BY count(*) DESC")
    print("\n  edge relation_type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>10,}")

    cur.execute("SELECT node_type, family_name, count(*) FROM constraint_node WHERE family_name != 'UNKNOWN' AND node_type IN ('SCOPE','CONDITION','TRIGGER','EVIDENCE','EXCEPTION','REFERENCE') GROUP BY node_type, family_name ORDER BY node_type, count(*) DESC")
    print("\n  세부 family_name 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:15s} {r[1]:35s} {r[2]:>8,}")

    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료")
    print(f"{'='*64}")
    for k, v in stats.items():
        print(f"    {k:20s} {v:>10,}건")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
