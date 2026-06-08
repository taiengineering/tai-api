# 세션 요약: 법령진단 근본 원인 → Compiler Core 연결 → 입력 표준화 (2026-06-08)

> 14번째 재개발 끝에 만들어진 엔진이 소비자 경로와 연결되지 않았던 문제를
> 추적·수정하고, 입력 경계를 표준화한 세션.

## 1. 근본 원인 발견

소비자 진단이 Compiler Core(완성된 엔진)가 아니라
카탈로그 테이블(runtime_metadata_resolution)을 읽고 있었음.

```
runtime_metadata_resolution: 3,395건, condition 7건(0.2%) ← 카탈로그
master_building_legal_rules_legacy_contaminated: 2,002건, 조건 78% ← 구 소스
master_rule_v2: 0건 ← 차세대 (비어있음)

Compiler Core (facility_applicability 등): 완성+데이터 있음, 미연결
```

기획(SESSION_2026_05_11)은 POST /diagnosis-engine/evaluate → Compiler Core를
의도했으나, 실제 소비자 경로(/anonymous-diagnosis)는 카탈로그를 읽음.

## 2. Compiler Core 연결 (PR #105)

```
변경 전: 소비자 → runtime_metadata_resolution (조건 0.2%) → 전부 applicable
변경 후: 소비자 → 임시 factory → facility_applicability 평가 → 조건 매칭

검증: BUILDING 8명→98건 / 200명→114건 (인원별 차등)
      INDUSTRIAL 45명→106 / 280명→114
      CONSTRUCTION 소규모→105 / 78억→224
      기존 무차별 ~3,395건 → 98~224건 조건 매칭
```

격리: diagnosis_runtime_step1.py, legal_runtime_fetch.py,
      rule_candidate_projection.py → [ISOLATED]

## 3. 전체 엔진 감사

9개 엔진 연결 감사 (ENGINE_CONNECTION_AUDIT.md):
- CONNECTED: Runtime, SaaS
- PARTIAL/DISCONNECTED: Check, Document, Equipment, Schedule, Education, Contract, Notification
- 공통 패턴: 새 진입점은 있으나 기존 체인의 마지막 고리 미연결

전체 파이프라인 지도 (ENGINE_PIPELINE_MAP.md):
- 3개 평행 트랙 (Compiler temp / DiagnosisService / SaaS 운영)
- 진단만 작동, 엔진 간 연결 없음

## 4. 6레이어 표준화 (조사 → 문제 → 표준 → 실행 → 검증)

### 조사·문제 (LAYER_SURVEY.md, LAYER_PROBLEMS.md)
19건 문제 발견. CRITICAL: 입력 유실(P-1-01), 익명 task_candidate 부재(P-3-01).

### 표준 정의 (LAYER_STANDARD.md)
엔진이 평가하는 것을 기준으로 6개 레이어 인터페이스 표준 확정.

### 실행 (PR #106 — 입력 경계)
```
STEP 1: 소비자 입력 → factories 저장 (building_use_code, floor_count)
STEP A: normalizer 소비자 경로 연결 (단위 문자열 "800kVA","78억" 방어)
STEP B': sector 어휘 표준 (DB=INDUSTRIAL / 엔진=MANUFACTURING)
        + 세 섹터 입력 필드 표준화
        + normalize_sector_db: MANUFACTURING→INDUSTRIAL 매핑 추가
```

핵심 성과: INDUSTRIAL 진단 factories_sector_check ERROR 해소.
검증: 3섹터 정상, 회귀 없음, 테스트 12/12.
엔진(facility_applicability_eval.py) 미변경.

## 5. 확정된 표준

```
sector 어휘:
  입력/저장/DB: BUILDING / INDUSTRIAL / CONSTRUCTION / SPECIAL_FACILITY
  엔진/룰: BUILDING / MANUFACTURING / CONSTRUCTION / SPECIAL_FACILITY
  변환 지점: 저장 시 normalize_sector_db (단일 경계)

입력 필드: ctx가 만드는 필드는 factories에 모두 저장 (유실 없음)
```

## 6. 관찰 기록 (별도 과제, 이번 범위 밖)

```
단위 정합 매칭:
  draft_slot에 단위 혼재 (억원/만원, kW/W, V/kV/kVA)
  입력만 표준화해도 엔진이 UNIT_MISMATCH → AMBIGUOUS
  → draft_slot 정규화 필요 (엔진/배치 영역)

facility_type 정밀 매칭:
  evaluate_scope_check가 값 비교 안 하고 존재만 봄
  → 엔진 평가 로직 개선 필요 (의도된 설계, 단위 정규화 선행)
```

## 7. 남은 작업 (출력 경계)

```
Layer 3→4 (fallback): task 없을 때 draft에서 law_name 조회
Layer 4→5 (obligations): wrapper → flat items, evidence 표준화
Layer 5→6 (출력): _partial_from_full / _build_partial 통합
```

## 핵심 원칙 (이번 세션에서 재확인)

```
13번째 재개발 실패 교훈: 부분만 보고 엔진을 건드리면 망한다.
→ 전체 흐름을 본 후 판단
→ 엔진 내부는 건드리지 않고 경계만 표준화
→ 조사 → 문제 파악 → 표준 정의 → 실행 → 검증 → 반복
→ 한 STEP씩 검증하며 진행 (폭주 금지)
```

## 관련 PR / 문서

```
PR #105: Compiler Core 연결 (소비자 진단 → 엔진)
PR #106: 입력 표준화 (STEP 1/A/B')

문서:
  docs/LEGAL_DIAGNOSIS_LAYER_STANDARD.md
  docs/LEGAL_DIAGNOSIS_LAYER_SURVEY.md
  docs/LEGAL_DIAGNOSIS_LAYER_PROBLEMS.md
  docs/ENGINE_CONNECTION_AUDIT.md
  docs/ENGINE_PIPELINE_MAP.md
  docs/LEGAL_ENGINE_AUDIT.md
```
