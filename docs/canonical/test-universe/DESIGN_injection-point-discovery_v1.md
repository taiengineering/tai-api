---
wo: WO-WIRING-003
class: plans
type: design
scope: canonical
project: test-universe
title: Injection Point Discovery
version: 1
status: active
owner: taiwang
---

# INJECTION POINT DISCOVERY — WO-WIRING-003

> 계약(law_id→sectors[]) 유지 상태에서 pattern_dictionary·role_mapping이 어디에 연결될 수 있는지 **후보만 식별.** 최적안 선택·Role→Sector 구현·코드 수정 **없음.** "가능한 연결 지점의 지도."
> 엔진 코드 taiengineering/tai-api.

## 판정: DESIGN_BLOCKED

## STEP 1 — Contract Boundary
```text
Producer  : law_sector_mapping (law_id→sectors[]) [public] + _load_sector_allowed_draft_ids
Consumer  : _load_draft_slot_groups → evaluate_draft_for_facility → compiler → 응답
Input     : sector_value → to_mapping_sector → key
Output    : allowed_draft_ids (Set[draft_id])
Ownership : law_sector_mapping = public(법령분류 표준)
            sector 표준 원천 = public.sector_standard (constants/sectors.py DB화, reload 가능)
```

## STEP 2 — Injection Candidate Inventory (적합성 평가 보류)
```text
C1 anonymous_factory_service._load_sector_allowed_draft_ids
   입력 sector_value → 출력 allowed_draft_ids | law_sector_mapping으로 draft 필터
C2 (DB) public.law_sector_mapping
   입력 law_id → 출력 sectors[] | 법령→sector 배열 매핑(계약 Producer 데이터)
C3 _load_sector_allowed_draft_ids STEP(4) 통과판정
   입력 law_sectors[law_id] → 출력 allowed 여부 | key ∈ sectors 판정
C4 (DB) public.sector_standard
   입력 sector_code → 출력 VALID_SECTORS/legacy | sector 표준값 원천
C5 legal_engine_policy.sieve_clause / legal_sieve_rule
   입력 clause_sector → 출력 KEEP/DROP | 의미절 거름망(현 진단경로 미연결)
```

## STEP 3 — Impact Surface (코드 근거)
```text
후보  law_sector_mapping   compiler   draft        API           Renderer
C1    직접 SELECT          간접       draft 필터   응답 법령집합  간접
C2    자기 자신            간접       통과여부     응답 법령집합  간접
C3    읽음(판정)           간접       통과여부     응답          간접
C4    간접(key 표준)       직접없음   간접         직접없음      없음
C5    참조/현경로 미연결   현경로 0   현경로 0     현경로 0      현경로 0
```

## STEP 4 — Contract Compatibility (코드 근거)
```text
C1 PARTIAL      계약 지점이나 Role→sectors 변환 전제. 함수는 law_id→sectors[] 기대,
                우리 자산은 law→Role. 변환 미정의 → 부분.
C2 COMPATIBLE   law_sector_mapping 자체가 계약 형식(law_id→sectors[]).
                Role을 sectors로 변환해 반영하면 계약 그대로 소비. 코드변경 0(데이터 계약).
C3 PARTIAL      key ∈ sectors 판정. Role 기반 판정 삽입 시 로직 변경 → 계약 코드 수정 유발.
C4 UNVERIFIED   sector_standard는 sector 표준값 원천이지 법령→sector 매핑 아님. 층위 다름.
C5 INCOMPATIBLE 현 진단경로에서 미호출(WO-WIRING-001). 이 경로 계약에 개입 불가.
```

## STEP 5 — Dependency Graph
```text
C1: evaluate_single_factory → _load_sector_allowed_draft_ids → _load_draft_slot_groups → allowed_draft_ids
C2: _load_sector_allowed_draft_ids(SELECT) → law_sector_mapping 행 → key∈sectors 판정 → 계약 유지
C3: _load_sector_allowed_draft_ids STEP(4) → 판정 → allowed.add → allowed_draft_ids
C4: constants.sectors._load_sector_standard_from_db → sector_standard → VALID_SECTORS (법령매핑 아님)
C5: (현 경로 caller 없음) → sieve_clause → 미연결
```

## STEP 6 — Risk Review (후보별)
```text
C1 Regression HIGH(핵심 필터 수정)·Contract Break 가능·Perf 연산↑·Rollback 코드배포
C2 Regression LOW(데이터만)·Contract Break 없음(형식 유지)·Transaction upsert·Rollback 행삭제 즉시
C3 Regression HIGH(판정 로직)·Contract Break 위험·Rollback 코드배포
C4 Regression MED(표준 전역)·Contract Break 없음(다른 층)·주의: 법령매핑 무관
C5 현 경로 영향 0(미연결)·연결하려면 별도 배선=범위 밖
```

## STEP 7 — 판정: DESIGN_BLOCKED
```text
지도는 완성: C2가 계약 호환 지점(COMPATIBLE, 코드변경 0, Regression LOW).
그러나 가장 유력한 C2조차 'Role → sectors[] 변환'이 전제:
  - C2는 law_sector_mapping 계약 형식(law_id→sectors[])과 일치.
  - 우리 자산은 law→Role(규율대상/시설). Role→sectors 변환 규칙 부재(R-01).
  - 변환 없이 C2에 넣을 sectors 값이 없음 → 후보 식별됐으나 구현 진입 불가.

'어디에 연결 가능한가'(이 WO) = 답함: C2.
'무엇을 흘려보낼까'(Role→sectors) = 미정 → 다음 WO 선행 필요.
READY_FOR_IMPLEMENTATION 아님.
```

## 산출물
```text
injection_candidate_inventory.csv · contract_compatibility.md · dependency_graph.md
runtime_impact_matrix.csv · wiring_candidate_report.md
```

## 규율 준수
- 최적안 선택 안 함(C2가 유력이나 '선택'이 아니라 '호환 판정') · Role→Sector 알고리즘 미구현 · Pattern 미생성 · 코드/SQL/law_sector_mapping 수정 0.

## 상태 (WIRING 진행)
```text
STEP1 무엇을 읽는가       ✓ WO-WIRING-001 STEP1
STEP2 무엇을 기대하는가   ✓ WO-WIRING-002 (Contract Complete)
STEP3 어디에 연결 가능한가 ✓ WO-WIRING-003 (C2 COMPATIBLE, 판정 DESIGN_BLOCKED) ← 현재
다음(선행 필요)          : Role→Sector 변환 정의 (R-01) → 그 후 IMPLEMENT
```
