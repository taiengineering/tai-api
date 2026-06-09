# KSIC 실입력 E2E 테스트 결과 (2026-06-09)

> 목적: 사용자가 입력한 KSIC 코드가 진단 결과 끝까지 반영되는지 검증
> 결과: Prod 스키마 갭 + 엔진 scope_check 한계 확인 (코드 수정 없음)

## 입력 스키마

- AnonymousDiagnosisCreate는 site_kind + scale + workers만 받음
- KSIC 필드 없음 — manufacturing 분기에서 ksic_major="" 하드코딩

## Prod API (사용자 경로)

| Case | KSIC 입력 | applicable | input_data ksic | 결과 |
|------|-----------|-----------|-----------------|------|
| C | 미입력 | 115 | 없음 | 기준 |
| A | ksic/ksic_code/ksic_major 시도 | 115 | 없음 | 동일 |

→ Case 2 — 원인 (a) 입력 유실 (API 스키마에 KSIC 없음)

## Compiler 경로 (DiagnoseStep1Body.ksic_major + prod DB)

| Case | ksic | factory 저장 | applicable | C26 vs C20 차이 |
|------|------|-------------|-----------|----------------|
| A | C26 | ksic_code=C26 | 261 | 0건 |
| B | C20 | ksic_code=C20 | 261 | 0건 |
| C | 빈값 | null | 115 | — |

- KSIC 유무: applicable 115 → 261 (+146 POSSIBLE, process_type IF_SCOPE 존재검사)
- KSIC 값(C26 vs C20): rule 집합 완전 동일, 유해/화학 법령도 동일 4건
- ksic_process_map(6,957건): facility_applicability 평가에 미연결

→ Case 2 — 원인 (b)+(c): 저장은 되나 코드값 비교·공정매핑 없음

## 판정 요약

```
Prod anonymous API:  KSIC 끝까지 반영 ❌ (스키마 갭)
Compiler 내부 경로:   저장 ✅ / 유무 반영 △ (POSSIBLE만) / C26≠C20 ❌
화학(C20) 특화 법령:  ❌ (현 설계로 불가 — 테스트로 확인)
```

## scope_check 패턴 일치

```
KSIC(process_type)는 facility_type과 동일한 구조:
  evaluate_scope_check가 "존재하면 POSSIBLE, 값 비교 안 함"
  → KSIC 넣으면 POSSIBLE 후보 증가 (115→261)
  → 그러나 C26/C20 구분 못 함
  → 단위 정합과 같은 엔진 설계 한계
```

## 분류 (다음 작업)

```
연결 작업 (엔진 안 건드림, 지금 가능):
  anonymous API 스키마에 KSIC 입력 필드 추가
  → 사용자가 KSIC 입력 가능
  → POSSIBLE 후보 반영 (115→261)

엔진 v2 과제 (엔진 설계 변경, 지금 불가):
  ksic_process_map 연동 또는 process_type 값 비교
  → C26 vs C20 구분, 화학 특화 법령
  → scope_check 값 비교 = 엔진 평가 로직 수정 = 재개발 위험
  → 단위 정합(Layer 2→3)과 동일 분류
```

## 엔진 v2 과제 목록 (누적)

```
1. 단위 정합 매칭 (monetary/voltage/storage)
   - draft_slot 단위 정규화 + compare 로직
2. facility_type 정밀 매칭
   - scope_check 값 비교
3. process_type(KSIC) 정밀 매칭  ← 이번 추가
   - ksic_process_map 연동 + 값 비교

→ 공통: 모두 evaluate_scope_check / compare 단위 처리 = 엔진 평가 로직
→ 엔진 v2에서 일괄 재설계 (draft_slot 정규화 선행)
```
