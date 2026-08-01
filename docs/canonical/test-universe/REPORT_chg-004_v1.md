---
wo: WO-CHG-004
class: records
type: report
scope: canonical
project: test-universe
title: Obs-004 Metadata Coverage (STEP2까지, 매핑값 보류)
version: 1
status: active
owner: taiwang
---

# REPORT — WO-CHG-004 Obs-004 Metadata Coverage (law_sector_mapping)

> law_sector_mapping Metadata만 보완. 코드·엔진 무수정. 결과: STEP2(Unmapped Inventory)까지 완료, STEP3(매핑 값 결정)은 귀속 근거 부재로 보류.
> Input: REPORT_analysis-obs004(db424158), Observation Inventory(6be576e4), Stable Baseline(before_clean), after_obs002.

## STEP 1 — Root Cause 재확인
db424158: law_sector_mapping 미완성(활성 768 중 375 미매핑, 48.8%). 엔진은 미매핑 법령을 전 sector 통과(문서화된 정책). 다른 Root Cause 탐색 없음.

## STEP 2 — Unmapped Law Inventory
- 미매핑 375개 전량 추출(law_id·law_name·domain_code·law_type_code·ministry_name). 산출물: unmapped_law_inventory.csv.
- domain_code 분포: ELECTRIC 106 · FIRE 80 · CHEMICAL 42 · BUILDING 36 · ENVIRONMENT 24 · INDUSTRIAL_SAFETY 21 · GAS 21 · (빈값) 16 · ENERGY 15 · DISASTER 10 · CONSTRUCTION 4.

## STEP 3 — 보류 (귀속 근거 부재)
STEP3 진입 전제 = 매핑 값의 검증 가능한 귀속 근거 확보. domain_code가 근거가 되는지 검증한 결과 **부적격**:
- 매핑된 법령에서 domain_code → sectors가 1:1 규칙을 이루지 않음. 예:
  - BUILDING domain → {SPECIAL_FACILITY} 78 · {BUILDING} 42 · {BUILDING,INDUSTRIAL} 15 · {BUILDING,CONSTRUCTION} 14 · {INDUSTRIAL} 5 · {B,I,C} 3 (6가지, 최다가 SPECIAL_FACILITY).
  - ELECTRIC → 6가지 분산. ENVIRONMENT → 7가지 분산.
- 즉 domain_code로 미매핑을 채우면 기존 매핑 패턴과 어긋나는 **근거 없는 임의 귀속**이 된다(Goal 금지 사항).
- 결론: 매핑 값 결정은 **법령별 도메인 판단**이 필요하며 측정으로 도출되지 않는다. STEP3~8(수정·after·Semantic·Regression)은 진행하지 않음.

## STEP 4~8 — 미수행 (STEP3 보류로 인해)
- law_sector_mapping 수정 0건. after_obs004 미생성. Regression 없음. 엔진 무변경.

## 판정
- **CHG 보류 (BOUNDED — Inventory 완료, 매핑 값 도메인 판단 대기).**
- Obs-004 상태 유지: ANALYZED(Root Cause 확정) + Unmapped Inventory 확보. 실제 매핑 보완은 도메인 귀속 기준이 정해진 뒤 별도 진행.

## 근거 없는 임의 귀속을 피한 이유
- 엔진 docstring 경고: 미매핑을 잘못 빼면(잘못 매핑하면) 의무 누락 위험. 잘못된 sector 귀속은 해당 sector에서 의무를 사라지게 하거나 타 sector에 오적용시킨다.
- domain_code 규칙이 성립하지 않는 상태에서 임의 채움은 그 위험을 실현한다. 따라서 근거 확보 전까지 채우지 않는 것이 안전하고 규율에 부합.

## 다음 (기록만, 본 WO 실행 아님)
- 매핑 값 결정 기준 후보: (a) 운영자/도메인 전문가의 sector 귀속 기준표, (b) 매핑된 법령의 (domain_code + law_name 패턴) 학습, (c) 법령 소관 부처(ministry)·법종(law_type) 조합 규칙. 어느 것도 본 WO 범위 밖 — 별도 커버리지 프로젝트에서 근거를 세운 뒤 STEP3~8 재개.

## 상태
```text
Obs-003 : RESOLVED
Obs-001 : RESOLVED
Obs-002 : RESOLVED
Obs-004 : ANALYZED + Unmapped Inventory 확보 → 매핑 값 도메인 판단 대기(보류)
Obs-005 : ANALYZED (정상)
Obs-006 : ANALYZED (정상)
```
