---
wo: WO-EVIDENCE-001
class: records
type: evidence
scope: canonical
project: test-universe
title: Existing Mapping Evidence Reconstruction
version: 1
status: active
owner: taiwang
---

# EXISTING MAPPING EVIDENCE RECONSTRUCTION (FROZEN) — WO-EVIDENCE-001

> 기존 393 Mapping이 어떤 Evidence로 sector가 결정됐는지 복원. 새 Policy·번역표·sector 결정 없음.
> Input: 기존 매핑 393(정답지) + 적용대상 원문(model2_mapped_evidence). WO-MODEL-002가 scope 직접명시만으론 4.3%만 설명함을 받아, 실제 판단 근거를 역추적.

## 판정: PASSED

## STEP 1-2 — Evidence Classification (393 전량)
```text
E1 원문 적용범위 직접명시  : 109 (정확 49 · 부분집합MULTI 48 · 오탐 12)
E2 시설명                 : 168
E3 업종명                 :  10
E4 법령 목적(단서 약함)     : 106
E5 행정 실무              :   0 (관측 안 됨)
E6 사람 판단              :   0 (별도 분류 없이 오탐이 시사)
E7 확인 불가              :   0
합계                     : 393
```

## STEP 3 — Replay (Evidence만으로 현재 sector 설명)
```text
확실 설명 (E1 정확, 예측=실제)      :  49 (12.5%)
MULTI 정합 (E1 부분집합, 예측⊆실제)  :  48 → 누적 97 (24.7%)
번역표 필요 (E2 168·E3 10·E4 106)   : 284
Replay 불가 (E1 오탐, 어휘=실제 모순): 12
```

## 핵심 발견 — 어휘조차 sector를 확정하지 못함
- **E1 오탐 12건이 결정적:** 원문에 sector 직접명시 어휘가 있는데도 실제 sector가 다름. 전부 SPECIAL_FACILITY 방향:
  - 의료기기법('사업장' 어휘→INDUSTRIAL 예측) 실제 {SPECIAL_FACILITY}
  - 장애인고용촉진법('사업장'→INDUSTRIAL) 실제 {SPECIAL_FACILITY}
  - 장애인 편의증진법('건축물'→BUILDING) 실제 {SPECIAL_FACILITY}
- **의미:** 같은 '사업장/건축물' 어휘가 대상 성격(의료기기·장애인·노인)에 따라 다른 sector가 됨. sector 결정 근거는 원문 '어휘'가 아니라 '대상의 특수성'(=사람 판단)인 경우가 존재.
- WO-MODEL-002의 F4(건설공사 예외)와 같은 구조가 E1 전반에 있음 → 어휘 기반 번역표는 예외를 내장해야 함.

## STEP 4 — Translation Candidate Pattern (번역표 아님, Pattern만)
```text
[적용범위 직접명시 → sector]  건설공사→CONSTRUCTION 등 (정확 49만 신뢰)
[시설명 → sector]            건축물·공동주택 (E2 168, 단 SPECIAL 예외)
[업종명 → sector]            건설업·제조업 (E3 10)
[대상 특수성 → SPECIAL_FACILITY]  의료기기·장애인·노인 (어휘 아닌 대상 성격, 오탐 12가 시사)
```
- 번역표는 작성하지 않음. Pattern만 추출.

## STEP 5 — Coverage Measurement
```text
Evidence Replay 확실 가능  :  49 (E1 정확)
Replay 가능(MULTI 정합)    :  48
번역표 필요               : 284 (E2/E3/E4)
사람 판단(어휘로 설명 불가) :  12 (E1 오탐 = 대상 특수성)
Unknown                  :   0
```
- method 교차: manual_verified 27은 E2 20·E1 7. auto_regex 331은 E1 154·E2 97·E4 74·E3 6. web_search 35는 E2 19·E4 14·E1 2.
- 관측: auto_regex의 E1 154 중 상당수가 부분집합/오탐 → auto_regex도 어휘 기반이라 같은 한계(WO-CHG-004 domain_code 반증과 정합).

## STEP 6 — Independent Review
- 기존 Mapping의 실제 결정 근거: 단일하지 않음. 원문 직접명시(E1 정확 49)는 소수, 대부분은 시설/업종 어휘(E2/E3, 번역표 필요) + 목적 조문(E4) + 대상 특수성(사람 판단).
- 번역표만으론 부족: 오탐 12가 '어휘→sector' 규칙의 반례이므로, 번역표는 '대상 특수성' 예외(→SPECIAL_FACILITY)를 함께 담아야 기존 판단과 일관.

## STEP 7 — Independent Audit
```text
Replay         : PASS (393 전량, 합계 검증)
Evidence       : PASS (E1~E4 분류, E5~E7 관측 안됨 기록)
Classification : PASS (method 교차 검증, auto_regex 한계 확인)
Coverage       : PASS (49/48/284/12/0 = 393)
특기: E1 '직접명시'조차 오탐 12 존재 → 어휘 기반 자동화의 상한을 정답지가 확정.
```

## STEP 8 — Freeze
```text
Evidence Classification : E1 109·E2 168·E3 10·E4 106 (E5/E6/E7 = 0)
Replay Coverage         : 확실 49·MULTI 48·번역표필요 284·사람판단 12
Pattern Catalog         : 적용범위직접명시·시설명·업종명·대상특수성(SPECIAL)
Unknown Cases           : 0
Review                  : PASS
Audit                   : PASS
```

## 결론
- 기존 393의 실제 판단 근거 복원 완료. **번역표의 근거가 드러남**: 시설명(E2 168)·업종명(E3 10)이 최대 후보이나, '대상 특수성→SPECIAL_FACILITY' 예외(오탐 12가 대표)를 반드시 포함해야 기존 판단과 일관.
- WO-MODEL-002 정정 심화: scope 직접명시(4.3%)→어휘 확장(E1 24.7% MULTI 포함)으로 설명력 상승하나, 어휘조차 상한이 있음(오탐 12). 번역표는 '어휘 규칙 + 대상 특수성 예외' 이중 구조여야 함.
- 다음(WO-MAPPING-004 번역표): E2 시설명 168·E3 업종명 10을 도메인 판단으로 sector 귀속하되, SPECIAL_FACILITY 예외(의료·장애인·노인 등 대상) 규칙을 우선 적용.

## Exit Criteria 점검
```text
[v] 393 Evidence Classification 완료
[v] Replay 완료
[v] Replay Coverage 측정
[v] Pattern Catalog 작성
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑪ Decision Model             ✓ WO-MODEL-001
⑫ Model Verification         ✓ WO-MODEL-002 (자동 4.3%)
⑬ Evidence Reconstruction    ✓ WO-EVIDENCE-001 (E1~E4 복원, 어휘 상한·대상특수성 발견) ← 현재
⑭ 번역표 수립(어휘+예외)      ← WO-MAPPING-004 (도메인 판단, SPECIAL 예외 포함)
⑮ DB 반영 CHG + Verify       ← WO-CHG-005
```
