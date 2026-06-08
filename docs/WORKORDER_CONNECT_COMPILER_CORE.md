# 작업지시서: Compiler Core ↔ 소비자 진단 연결

> 레포: taiengineering/tai-api  
> 원칙: 배치 평가 로직 서비스화 + 후보 조회 DRY + factory_id 시 compiler_core 부착  
> merge 금지 — Draft PR만

---

## 조사 결과 (구현 전)

### 1. `scripts/run_facility_applicability.py` — 서비스 추출 가능성

| 구분 | 내용 |
|------|------|
| **추출 가능 (순수 로직)** | `FIELD_MAP`, `compare_numeric`, facility×draft 평가 루프, overall status 집계 |
| **스크립트에 잔류 (I/O)** | psycopg2 DDL/TRUNCATE, factories/draft_slot 로드, bulk INSERT |
| **판단** | **추출 가능** → `services/facility_applicability_eval.py` |

평가는 `draft_slot` (section=`IF_NUMERIC` / `IF_SCOPE`)을 읽으며, `numeric_constraint`는 **직접 조회하지 않음** (executable_draft 빌드 시 이미 draft_slot에 operator/value/unit 복사됨).

### 2. `DiagnosisService.evaluate` 출력 포맷

```python
{
  "diagnosis_id": "<session uuid>",
  "facility_id": "<factory uuid>",
  "diagnosis_status": "COMPLETED_WITH_CANDIDATES" | "COMPLETED_CLEAN" | "NEEDS_HUMAN_REVIEW",
  "applicability_candidates": [...],      # facility_applicability MATCH/POSSIBLE
  "obligation_candidates": [...],         # diagnosis_candidate insert 결과
  "prohibition_candidates": [],
  "penalty_candidates": [...],
  "schedule_candidate_hints": [...],
  "missing_data": ["employee_count", ...],
  "residuals": [...],                     # compliance_review_queue
  "human_review_queue": [...],
  "validation": {"status": "PASS"|"AMBIGUOUS"|"UNRESOLVED", "issues": []},
}
```

입력 `input_data`로 **직접 조건 비교하지 않음**. `factory_id`로 **이미 materialize된** runtime 테이블을 읽음.

### 3. `draft_condition_graph` + `numeric_constraint` 구조

```
law_article_part
  → numeric_constraint (operator, value, unit, span)     [run_numeric_full.py]
  → rule_candidate_slot.numeric_constraint_id
  → draft_slot IF_NUMERIC (operator/value/unit 복사)   [run_executable_draft.py UPDATE]
  → draft_condition_graph (if_families[], then_families[])  ← 메타만, 런타임 평가 미사용
  → run_facility_applicability: draft_slot vs factories 컬럼 비교
  → facility_applicability (MATCH_CANDIDATE / …)
```

| 테이블 | 런타임 평가 역할 |
|--------|------------------|
| `numeric_constraint` | 조문에서 수치 추출 **저장** (배치) |
| `draft_slot` IF_NUMERIC | 비교에 쓰이는 operator/value |
| `draft_condition_graph` | if/then family **목록** (그래프 시각화·IR, 비교 없음) |
| `facility_applicability` | facility×draft **평가 결과** |

비교 함수: `compare_numeric(operator, draft_value, facility_column_value)` → `MATCH_CANDIDATE` / `NOT_MATCHED` / `MISSING_DATA` / `AMBIGUOUS`.

---

## 구현 범위 (본 PR)

1. `services/facility_applicability_eval.py` — 순수 평가 로직 추출
2. `services/compiler_core_svc.py` — `fetch_compiler_candidates()` 공유
3. `diagnosis_service.py`, `compiler_core.py` — 공유 fetch 사용 (DRY)
4. `diagnosis_runtime_step1.py` — `factory_id` 있을 때 `result_data.compiler_core` 부착
5. `scripts/run_facility_applicability.py` — 서비스 함수 호출로 슬림화
6. 단위 테스트 2건

## 비범위 (후속 PR)

- 익명 진단(`factory_id=None`)을 compiler core로 **대체** (현재는 runtime_metadata 유지)
- `draft_condition_graph`를 이용한 then-action 평가
- on-demand applicability 재계산 API (배치 없이 evaluate 호출)

## 검증

```bash
pytest tests/test_facility_applicability_eval.py tests/test_compiler_core_svc.py -q
```
