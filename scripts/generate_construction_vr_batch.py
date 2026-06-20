"""건설 VR 대량 생성 — WO-CONSTRUCTION-MASS-READING-001 STEP-1.

목적: 건설 사업장 입력 5,000건을 다양한 조합으로 생성해 factories에 저장.
      이후 전체 파이프라인을 흘려 결과 문서를 대량 Reading 한다.

식별: remarks = 'VR_CONSTRUCTION_ROUND_001' (기존 실데이터와 구분).
seed 고정(random.seed(42))으로 재현 가능.

신규 컬럼/엔진/법령 생성 없음. 기존 factories 컬럼에만 INSERT.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/generate_construction_vr_batch.py
"""

import os, sys, random, uuid

VR_FLAG = "VR_CONSTRUCTION_ROUND_001"
TARGET_COUNT = 5000
SEED = 42

# 건설 공사 유형 (다양화)
CONSTRUCTION_TYPES = ["건축", "토목", "산업환경설비", "조경", "전문공사"]

# KSIC 건설 업종 코드 (다양화)
KSIC_CONSTRUCTION = ["F41", "F42", "F41110", "F41210", "F42100", "F42200", "F42300"]

# 공정/작업 표현 (다양화) — construction_type 보조 표기에 사용
PROCESS_POOL = [
    "기초공사", "골조공사", "철근콘크리트공사", "강구조공사", "마감공사",
    "토공사", "굴착공사", "흙막이공사", "발파공사", "해체공사",
    "비계공사", "거푸집공사", "방수공사", "전기공사", "설비공사",
]


def build_row(rng):
    """건설 사업장 1건 생성 (입력 조합 다양화)."""
    # 규모 다양화
    employee_count = rng.choice([5, 12, 25, 49, 50, 80, 120, 200, 350, 600])
    construction_amount = rng.choice([
        300_000_000, 800_000_000, 2_000_000_000, 5_000_000_000,
        8_000_000_000, 12_000_000_000, 30_000_000_000, 80_000_000_000,
    ])
    subcontractor_count = rng.choice([0, 1, 3, 5, 8, 12, 20])
    subcontractor_worker_count = subcontractor_count * rng.choice([3, 5, 8, 12])

    # 건설 고유 위험 입력 (조합 다양화 — 독립 확률)
    has_tower_crane = rng.random() < 0.35
    has_confined_space = rng.random() < 0.30
    has_asbestos_demo = rng.random() < 0.20
    has_blasting = rng.random() < 0.15
    has_diving = rng.random() < 0.05

    process_count = rng.randint(2, 6)
    processes = rng.sample(PROCESS_POOL, process_count)

    return {
        "id": str(uuid.uuid4()),
        "name": f"[VR건설] {rng.choice(CONSTRUCTION_TYPES)}현장 {rng.randint(1, 99999)}",
        "sector": "CONSTRUCTION",
        "ksic_code": rng.choice(KSIC_CONSTRUCTION),
        "employee_count": employee_count,
        "construction_amount": construction_amount,
        "construction_type": rng.choice(CONSTRUCTION_TYPES),
        "subcontractor_count": subcontractor_count,
        "subcontractor_worker_count": subcontractor_worker_count,
        "has_tower_crane": has_tower_crane,
        "has_confined_space": has_confined_space,
        "has_asbestos_demo": has_asbestos_demo,
        "has_blasting": has_blasting,
        "has_diving": has_diving,
        "remarks": VR_FLAG + " | " + ",".join(processes),
        "is_active": True,
        "status_code": "ACTIVE",
        "legal_status": "NOT_APPLIED",
    }


def main():
    import psycopg2
    from psycopg2.extras import execute_values

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    rng = random.Random(SEED)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print(f"  건설 VR 대량 생성 — {VR_FLAG}")
    print(f"{'='*64}")
    print(f"  목표: {TARGET_COUNT:,}건 / seed={SEED}")

    # 재실행 대비: 같은 flag 기존분 제거 (VR만, 실데이터 안 건드림)
    cur.execute("SELECT count(*) FROM factories WHERE remarks LIKE %s", (VR_FLAG + "%",))
    existing = cur.fetchone()[0]
    if existing > 0:
        # VR factory의 파이프라인 산출물도 함께 정리되도록 factory만 삭제
        # (자식은 후속 배치 재실행으로 재생성되므로 여기선 factory만)
        cur.execute("DELETE FROM factories WHERE remarks LIKE %s", (VR_FLAG + "%",))
        conn.commit()
        print(f"  ⚠️ 기존 VR {existing:,}건 제거")

    # 생성
    rows = [build_row(rng) for _ in range(TARGET_COUNT)]

    cols = ["id", "name", "sector", "ksic_code", "employee_count",
            "construction_amount", "construction_type", "subcontractor_count",
            "subcontractor_worker_count", "has_tower_crane", "has_confined_space",
            "has_asbestos_demo", "has_blasting", "has_diving", "remarks",
            "is_active", "status_code", "legal_status"]

    values = [tuple(r[c] for c in cols) for r in rows]

    insert_sql = f"INSERT INTO factories ({','.join(cols)}) VALUES %s"
    for i in range(0, len(values), 1000):
        execute_values(cur, insert_sql, values[i:i+1000], page_size=1000)
    conn.commit()

    # 검증
    cur.execute("SELECT count(*) FROM factories WHERE remarks LIKE %s", (VR_FLAG + "%",))
    total = cur.fetchone()[0]

    # 위험 조합 분포 출력
    cur.execute("""
        SELECT
          sum(case when has_tower_crane then 1 else 0 end) AS tower,
          sum(case when has_confined_space then 1 else 0 end) AS confined,
          sum(case when has_asbestos_demo then 1 else 0 end) AS asbestos,
          sum(case when has_blasting then 1 else 0 end) AS blasting,
          sum(case when has_diving then 1 else 0 end) AS diving
        FROM factories WHERE remarks LIKE %s
    """, (VR_FLAG + "%",))
    d = cur.fetchone()

    cur.close(); conn.close()

    print(f"\n{'─'*64}")
    print(f"  ✅ 생성 완료: {total:,}건")
    print(f"  위험 조합 분포:")
    print(f"    타워크레인: {d[0]:,} / 밀폐공간: {d[1]:,} / 석면: {d[2]:,}")
    print(f"    발파: {d[3]:,} / 잠수: {d[4]:,}")
    print(f"{'='*64}")
    print(f"  다음: railway run python3 scripts/run_facility_applicability.py")
    print(f"        → run_task_candidate → schedule → penalty → compliance_package")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
