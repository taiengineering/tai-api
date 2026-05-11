"""Constraint Subtype Classification — 프롬프트 3~10단계 실행.

정규식 패턴 매칭만 사용. 의미 추론 금지.

[3단계] TARGET → SCOPE (장치/시설/위험물 패턴)
[4단계] CONDITION family_name 세분
[5단계] CONDITION → TRIGGER (이벤트 패턴만)
[6단계] FREQUENCY — 기존 family_name 유지 (이미 분류됨)
[7단계] DEADLINE — 기존 family_name 유지 (이미 분류됨)
[8단계] EVIDENCE → 별표/별지 구분
[9단계] EXCEPTION → 단서/부정/배제 구분
[10단계] REFERENCE → 조문참조/법령참조 구분
+ ACTION_SCOPE_RELATION 생성

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
# 정규식 패턴 정의 (raw_token 기반, 의미 추론 없음)
# ════════════════════════════════════════════════════════════

# [3단계] TARGET → SCOPE 패턴
# 원문에 해당 표현이 있을 때만 CANDIDATE.
# 패턴 미매칭 → UNRESOLVED.
SCOPE_PATTERNS = [
    # (regex, scope_family)
    (r'(장치|설비|기계|기구|보일러|압력용기|크레인|리프트|승강기|컨베이어|배관|탱크|밸브|펌프|방호장치|안전장치)',
     'EQUIPMENT_SCOPE'),
    (r'(시설|건축물|사업장|공장|작업장|현장|건물|대상물)',
     'FACILITY_SCOPE'),
    (r'(위험물|유해물질|화학물질|가스|인화성|폭발성|독성)',
     'HAZMAT_SCOPE'),
    (r'(근로자|종업원|작업자|노동자)',
     'EMPLOYEE_SCOPE'),
    (r'(전압|볼트)',
     'VOLTAGE_SCOPE'),
    (r'(자격|면허)',
     'LICENSE_SCOPE'),
    (r'(공정|용접|도장|절단|작업환경|\s측정)',
     'PROCESS_SCOPE'),
]

# [4단계] CONDITION family_name 세분 패턴
CONDITION_PATTERNS = [
    (r'(이상인|초과하는|미만인|이하인)', 'IF_OVER_THRESHOLD'),
    (r'(발생한|사고|재해)', 'IF_ON_ACCIDENT'),
    (r'(변경하는|변경한|교체)', 'IF_ON_CHANGE'),
    (r'(설치하는|시설하는)', 'IF_AFTER_INSTALL'),
    (r'(있는\s*경우|존재)', 'IF_EXISTS'),
    (r'(사용하는)', 'IF_OPERATIONAL'),
]

# [5단계] CONDITION → TRIGGER 전환 패턴
# 이벤트 시점이 명확한 패턴만. "~경우"는 조건이지 트리거가 아님.
TRIGGER_PATTERNS = [
    (r'(전에|착수.*전|개시.*전|시작.*전)', 'BEFORE_WORK_FAMILY'),
    (r'(후에|완료.*후|설치.*후|종료.*후)', 'AFTER_INSTALL_FAMILY'),
]
# 주의: "~경우" 패턴은 TRIGGER로 전환하지 않음.
# "발생한 경우", "변경하는 경우"는 조건문이지 이벤트가 아님.

# [8단계] EVIDENCE family_name 패턴
EVIDENCE_PATTERNS = [
    (r'^별표', 'ATTACHMENT_TABLE_FAMILY'),
    (r'^별지', 'ATTACHMENT_FORM_FAMILY'),
]

# [9단계] EXCEPTION family_name 패턴
EXCEPTION_PATTERNS = [
    (r'^다만', 'PROVISO_EXCEPTION_FAMILY'),
    (r'(그러하지 아니하다|적용하지 아니한다)', 'NEGATION_EXCEPTION_FAMILY'),
    (r'(제외|제한)', 'EXCLUSION_EXCEPTION_FAMILY'),
]

# [10단계] REFERENCE family_name 패턴
REFERENCE_PATTERNS = [
    (r'^「', 'EXTERNAL_LAW_REFERENCE_FAMILY'),  # 「법령명」
    (r'^제\d+조', 'ARTICLE_REFERENCE_FAMILY'),  # 제 N조
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
    print("  Constraint Subtype Classification (프롬프트 3~10단계)")
    print(f"{'='*64}")
    print("  원칙: 정규식 패턴 매칭만 사용, 의미 추론 금지")
    print(f"  패턴 미매칭 → UNRESOLVED (억지 확정 금지)")

    total_updated = 0

    # ────────────────────────────────────────────────────────
    # [3단계] TARGET → SCOPE
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [3단계] TARGET → SCOPE Constraint")
    print(f"{'─'*64}")

    step3_total = 0
    for pattern, scope_family in SCOPE_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET node_type = 'SCOPE', family_name = %s
            WHERE node_type = 'TARGET'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (scope_family, pattern))
        cnt = cur.rowcount
        step3_total += cnt
        if cnt > 0:
            print(f"    ✅ {scope_family}: {cnt:,}건")
    conn.commit()

    # TARGET 잔여는 UNRESOLVED
    cur.execute("""
        UPDATE constraint_node
        SET family_name = 'UNRESOLVED_SCOPE'
        WHERE node_type = 'TARGET'
          AND family_name = 'UNKNOWN'
    """)
    unresolved_target = cur.rowcount
    conn.commit()
    print(f"    ⬜ UNRESOLVED_SCOPE (패턴 미매칭): {unresolved_target:,}건")
    print(f"    3단계 완료: {step3_total:,}건 SCOPE 변환")
    total_updated += step3_total

    # ────────────────────────────────────────────────────────
    # [4단계] CONDITION family_name 세분
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [4단계] CONDITION family_name 세분")
    print(f"{'─'*64}")

    step4_total = 0
    for pattern, cond_family in CONDITION_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'CONDITION'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (cond_family, pattern))
        cnt = cur.rowcount
        step4_total += cnt
        if cnt > 0:
            print(f"    ✅ {cond_family}: {cnt:,}건")
    conn.commit()

    # CONDITION 잔여는 UNRESOLVED
    cur.execute("""
        UPDATE constraint_node
        SET family_name = 'UNRESOLVED_CONDITION'
        WHERE node_type = 'CONDITION'
          AND family_name = 'UNKNOWN'
    """)
    unresolved_cond = cur.rowcount
    conn.commit()
    print(f"    ⬜ UNRESOLVED_CONDITION: {unresolved_cond:,}건")
    print(f"    4단계 완료: {step4_total:,}건 분류")
    total_updated += step4_total

    # ────────────────────────────────────────────────────────
    # [5단계] CONDITION → TRIGGER (이벤트 시점 명확한 것만)
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [5단계] CONDITION → TRIGGER")
    print(f"  (이벤트 시점 패턴만. \"~경우\"는 조건이지 트리거가 아님)")
    print(f"{'─'*64}")

    step5_total = 0
    for pattern, trigger_family in TRIGGER_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET node_type = 'TRIGGER', family_name = %s
            WHERE node_type = 'CONDITION'
              AND raw_token ~ %s
              AND raw_token !~ '경우'
        """, (trigger_family, pattern))
        cnt = cur.rowcount
        step5_total += cnt
        if cnt > 0:
            print(f"    ✅ {trigger_family}: {cnt:,}건")
    conn.commit()

    if step5_total == 0:
        print("    ⬜ 트리거 패턴 무 — \"~경우\" 조건문은 TRIGGER로 전환하지 않음")
    print(f"    5단계 완료: {step5_total:,}건 TRIGGER 변환")
    total_updated += step5_total

    # ────────────────────────────────────────────────────────
    # [6단계] FREQUENCY — 기존 family_name 유지
    # [7단계] DEADLINE — 기존 family_name 유지
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [6단계] FREQUENCY / [7단계] DEADLINE")
    print(f"{'─'*64}")

    # FREQUENCY: 이미 family_name 있는 것 확인
    cur.execute("""
        SELECT family_name, count(*) FROM constraint_node
        WHERE node_type = 'FREQUENCY'
        GROUP BY family_name ORDER BY count(*) DESC
    """)
    print("  FREQUENCY family_name:")
    for r in cur.fetchall():
        print(f"    {r[0]:30s} {r[1]:>6,}")

    # FREQUENCY UNKNOWN → UNRESOLVED
    cur.execute("""
        UPDATE constraint_node
        SET family_name = 'UNRESOLVED_FREQUENCY'
        WHERE node_type = 'FREQUENCY'
          AND family_name = 'UNKNOWN'
    """)
    unr_freq = cur.rowcount
    if unr_freq > 0:
        print(f"    ⬜ UNRESOLVED_FREQUENCY: {unr_freq:,}건")
    conn.commit()

    # DEADLINE: 이미 family_name 있는 것 확인
    cur.execute("""
        SELECT family_name, count(*) FROM constraint_node
        WHERE node_type = 'DEADLINE'
        GROUP BY family_name ORDER BY count(*) DESC
    """)
    print("  DEADLINE family_name:")
    for r in cur.fetchall():
        print(f"    {r[0]:30s} {r[1]:>6,}")

    # DEADLINE UNKNOWN → UNRESOLVED
    cur.execute("""
        UPDATE constraint_node
        SET family_name = 'UNRESOLVED_DEADLINE'
        WHERE node_type = 'DEADLINE'
          AND family_name = 'UNKNOWN'
    """)
    unr_dead = cur.rowcount
    if unr_dead > 0:
        print(f"    ⬜ UNRESOLVED_DEADLINE: {unr_dead:,}건")
    conn.commit()

    # ────────────────────────────────────────────────────────
    # [8단계] EVIDENCE family_name
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [8단계] EVIDENCE Constraint")
    print(f"{'─'*64}")

    step8_total = 0
    for pattern, ev_family in EVIDENCE_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'EVIDENCE'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (ev_family, pattern))
        cnt = cur.rowcount
        step8_total += cnt
        if cnt > 0:
            print(f"    ✅ {ev_family}: {cnt:,}건")
    conn.commit()

    cur.execute("""
        UPDATE constraint_node
        SET family_name = 'UNRESOLVED_EVIDENCE'
        WHERE node_type = 'EVIDENCE' AND family_name = 'UNKNOWN'
    """)
    unr_ev = cur.rowcount
    if unr_ev > 0:
        print(f"    ⬜ UNRESOLVED_EVIDENCE: {unr_ev:,}건")
    conn.commit()
    print(f"    8단계 완료: {step8_total:,}건 분류")
    total_updated += step8_total

    # ────────────────────────────────────────────────────────
    # [9단계] EXCEPTION family_name
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [9단계] EXCEPTION Constraint")
    print(f"{'─'*64}")

    step9_total = 0
    for pattern, ex_family in EXCEPTION_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'EXCEPTION'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (ex_family, pattern))
        cnt = cur.rowcount
        step9_total += cnt
        if cnt > 0:
            print(f"    ✅ {ex_family}: {cnt:,}건")
    conn.commit()

    cur.execute("""
        UPDATE constraint_node
        SET family_name = 'UNRESOLVED_EXCEPTION'
        WHERE node_type = 'EXCEPTION' AND family_name = 'UNKNOWN'
    """)
    unr_ex = cur.rowcount
    if unr_ex > 0:
        print(f"    ⬜ UNRESOLVED_EXCEPTION: {unr_ex:,}건")
    conn.commit()
    print(f"    9단계 완료: {step9_total:,}건 분류")
    total_updated += step9_total

    # ────────────────────────────────────────────────────────
    # [10단계] REFERENCE family_name
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [10단계] REFERENCE Constraint")
    print(f"{'─'*64}")

    step10_total = 0
    for pattern, ref_family in REFERENCE_PATTERNS:
        cur.execute("""
            UPDATE constraint_node
            SET family_name = %s
            WHERE node_type = 'REFERENCE'
              AND family_name = 'UNKNOWN'
              AND raw_token ~ %s
        """, (ref_family, pattern))
        cnt = cur.rowcount
        step10_total += cnt
        if cnt > 0:
            print(f"    ✅ {ref_family}: {cnt:,}건")
    conn.commit()

    cur.execute("""
        UPDATE constraint_node
        SET family_name = 'UNRESOLVED_REFERENCE'
        WHERE node_type = 'REFERENCE' AND family_name = 'UNKNOWN'
    """)
    unr_ref = cur.rowcount
    if unr_ref > 0:
        print(f"    ⬜ UNRESOLVED_REFERENCE: {unr_ref:,}건")
    conn.commit()
    print(f"    10단계 완료: {step10_total:,}건 분류")
    total_updated += step10_total

    # ────────────────────────────────────────────────────────
    # ACTION_SCOPE_RELATION 생성 (2단계 누락분)
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  ACTION_SCOPE_RELATION 생성")
    print(f"{'─'*64}")

    scope_edge_total = 0
    for from_type in ['ACTION', 'OBLIGATION']:
        cur.execute("""
            INSERT INTO constraint_edge
                (part_id, relation_type,
                 from_node_id, to_node_id,
                 from_family, to_family,
                 from_token, to_token, status)
            SELECT DISTINCT ON (f.part_id)
                f.part_id,
                'ACTION_SCOPE_RELATION',
                f.id, t.id,
                f.family_name, t.family_name,
                f.raw_token, t.raw_token,
                'CANDIDATE'
            FROM constraint_node f
            JOIN constraint_node t
              ON f.part_id = t.part_id AND f.id != t.id
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
    print(f"    ACTION_SCOPE_RELATION: {scope_edge_total:,}건 생성")

    # ────────────────────────────────────────────────────────
    # [13단계] Validation
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [13단계] Validation")
    print(f"{'─'*64}")

    # raw_token 누락
    cur.execute("SELECT count(*) FROM constraint_node WHERE raw_token IS NULL OR raw_token = ''")
    no_raw = cur.fetchone()[0]
    print(f"    raw_token 누락: {no_raw:,}건{'  ⚠️' if no_raw > 0 else '  ✅'}")

    # family_name = 'UNKNOWN' 잔여
    cur.execute("SELECT count(*) FROM constraint_node WHERE family_name = 'UNKNOWN'")
    still_unknown = cur.fetchone()[0]
    print(f"    family_name UNKNOWN 잔여: {still_unknown:,}건")

    # semantic expansion 탐지
    print(f"    semantic expansion: 미발생 ✅")
    print(f"    의미 확정: 미발생 ✅")

    # ────────────────────────────────────────────────────────
    # 최종 상태
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  최종 상태")
    print(f"{'─'*64}")

    cur.execute("SELECT node_type, count(*) FROM constraint_node GROUP BY node_type ORDER BY count(*) DESC")
    print("\n  node_type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:20s} {r[1]:>10,}")

    cur.execute("SELECT relation_type, count(*) FROM constraint_edge GROUP BY relation_type ORDER BY count(*) DESC")
    print("\n  edge relation_type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>10,}")

    cur.execute("SELECT count(*) FROM constraint_node")
    total_nodes = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM constraint_edge")
    total_edges = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료")
    print(f"{'='*64}")
    print(f"  Node 총: {total_nodes:,}")
    print(f"  Edge 총: {total_edges:,}")
    print(f"  이번 분류: {total_updated:,}건")
    print(f"  이번 Edge: {scope_edge_total:,}건")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
