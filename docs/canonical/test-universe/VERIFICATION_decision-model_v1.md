---
wo: WO-MODEL-002
class: records
type: verification
scope: canonical
project: test-universe
title: Decision Model Verification
version: 1
status: active
owner: taiwang
---

# DECISION MODEL VERIFICATION (FROZEN) — WO-MODEL-002

> WO-MODEL-001 Decision Model을 이미 검증된 기존 393 매핑에 적용해 재현되는지 검증. Model 수정·sector 결정·Policy 승인 없음.
> Input: Decision Model(56c55a4a), 기존 매핑 393(정답지), 적용대상 원문(model2_mapped_evidence).

## 판정: KEEP WITH CORRECTION
- Model 구조는 타당(F1 269가 Missing Input으로 설명됨). 그러나 WO-MODEL-001의 '높은 설명력' 결론은 **반증**(현 상태 자동 설명력 4.3%). 정정 필요.

## STEP 1 — Feature Completeness
- 입력 누락: 없음. F1 269건이 시설/업종 단서를 원문에 가짐 → facility/industry Feature는 존재. 빠진 것은 Feature가 아니라 **번역표(Missing Input ①②)**.
- 중복 입력: 없음(11 Feature 역할 구분).
- 미사용: law_type/purpose 등 보조 정보는 sector 결정에 직접 미사용(보조 분류, 정상).

## STEP 2 — Existing Mapping 393 Replay (정답지 대조)
```text
Model 결정가능 경로(scope 직접명시)로 설명 : 17 / 393 (4.3%)
  예측 정확(실제 sectors 포함)             : 15
  예측 불일치                             : 2  (건설공사→CONSTRUCTION 예측이 실제와 다름 = 단일키워드 반례)
Model로 설명 불가                         : 376 / 393 (95.7%)
```
- **핵심: 이미 사람이 검증한 393 매핑의 95.7%를 Model의 자동 경로가 설명하지 못함.** 실제 매핑은 원문 scope가 아닌 다른 근거(도메인 판단)로 이뤄졌음.

## STEP 3 — Counter Example (설명 불가 376 분류)
```text
F1 Feature 부족 : 269  시설/업종 단서는 원문에 있으나 sector 번역표 없어 결정 불가
F3 Policy 필요  : 107  원문에 sector 단서 자체 없음(순수 도메인 판단)
F2 Flow 부족   :   0  (Flow 자체 결함 아님)
F4 데이터 오류  :   2  (예측 불일치 = 건설공사 단일키워드가 항상 CONSTRUCTION 아님)
```
- F1 예시: 건설기계관리법 시행규칙→{CONSTRUCTION}(시설·사업장 단서), 건축기본법→{BUILDING}(건축물·시설 단서), 건설폐기물법→{CONSTRUCTION}(건축물·시설).
- **F1 269건은 Missing Input(시설→sector, 업종→sector 번역표)이 채워지면 설명 가능** → Model이 지목한 ①②가 실제 열쇠임을 정답지가 확증.

## STEP 4 — Coverage Measurement
```text
Model 현재 상태로 설명 가능(자동)  :  17 (4.3%)   scope 직접명시
Missing Input 채우면 설명 가능     : 269 (68.4%)  F1, 번역표 필요
순수 Policy 필요                  : 107 (27.2%)  F3, 원문 단서 없음
Data Error(예측 불일치)           :   2 (0.5%)
```

## STEP 5 — Independent Review
- 불필요 복잡?: 아니오(Flow 단순).
- 빠진 Feature?: 아니오 — 빠진 것은 Feature가 아니라 번역표(Missing Input).
- Feature 충돌?: 있음 — 건설기계관리법이 도로+시설+사업장 복수 단서 → 단일 sector 번역 시 충돌(MULTI와 연결 필요). 기록만.

## STEP 6 — Independent Audit
```text
Feature        : PASS (11 유효, 미사용은 보조로 정당)
Flow           : PASS (4.3%만 자동은 Flow 결함 아니라 Missing Input 미충족 결과)
Coverage       : 측정 완료 (4.3 / 68.4 / 27.2)
Counter Example: 376 확보, F1 269 / F3 107 / F4 2
```

## STEP 7 — Freeze
```text
Coverage 결과   : 자동 4.3% / 번역표 충족 시 72.7%(17+269) / 순수 Policy 27.2%
Counter Example : 376 (F1 269 · F3 107 · F4 2)
Remaining Gap   : Missing Input ①②(시설/업종→sector 번역표) — 이게 Model의 작동 전제
Review          : PASS (구조 타당, Feature 충돌 1건 기록)
Audit           : PASS
```

## 결론 (WO-MODEL-001 정정)
- **Model 구조 = 타당.** F1 269건이 Missing Input으로 설명 가능 → Model이 식별한 핵심 Missing(①시설→sector ②업종→sector)이 실제 393 매핑의 68%를 여는 열쇠임을 정답지가 확증.
- **'높은 설명력·사람이 3개만 정하면 됨' = 반증/정정.** 현 Model의 자동 경로(scope 직접명시)는 4.3%만 설명. 3개 Missing은 '선택적 보완'이 아니라 **Model 작동의 전제 조건**. 번역표가 채워져야 68%가 설명되고, 그래도 27%는 순수 Policy로 남음.
- **F4 2건**: '건설공사'조차 항상 CONSTRUCTION 아님 → A의 유일 기준도 예외 존재(AUDIT-002 BS-1과 연결). 번역표 수립 시 반영 필요.
- **정책 단계 진입 판단:** Model이 393의 72.7%(번역표 충족 시)를 설명하므로 구조는 신뢰 가능. 단 번역표(①②) 수립이 정책 단계의 실제 작업이며, 27% 순수 Policy는 개별 판단 불가피.

## Exit Criteria 점검
```text
[v] Existing Mapping Replay 완료 (393/393)
[v] Counter Example 확보 (376, F1/F3/F4)
[v] Coverage 측정 완료 (4.3/68.4/27.2)
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑪ Decision Model(입력 구조)     ✓ WO-MODEL-001
⑫ Model Verification            ✓ WO-MODEL-002 (KEEP WITH CORRECTION, 자동 4.3%/번역표충족 72.7%) ← 현재
⑬ 번역표 ①② 수립(도메인 판단)   ← WO-MAPPING-004 (사람이 정의, F1 269 해소)
⑭ 순수 Policy 107 개별 판단      ← 사람
⑮ DB 반영 CHG + Verify          ← WO-CHG-005
```
