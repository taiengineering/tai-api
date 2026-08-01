---
wo: WO-MAPPING-004
class: records
type: taxonomy
scope: canonical
project: test-universe
title: Exception Taxonomy Freeze
version: 1
status: active
owner: taiwang
---

# EXCEPTION TAXONOMY (FROZEN) — WO-MAPPING-004

> 번역표를 만들기 전에, 번역표를 깨뜨리는 예외를 전량 구조화. 번역표 작성·sector 결정·DB 수정 없음. 이 Taxonomy는 이후 번역표의 제약조건.
> Input: 기존 393 매핑(정답지), WO-EVIDENCE-001(어휘 오탐 = 대상 특수성).

## 판정: PASSED

## STEP 1,3 — Exception Inventory + Frequency
```text
EX-01 대상 특수성 → SPECIAL_FACILITY : 113 (28.8%)  영향도 HIGH
EX-02 MULTI (복수 sector)            : 166 (42.2%)  영향도 HIGH
EX-03 시설 어휘 있으나 SPECIAL        :  61          (EX-01 부분집합)
EX-04 업종 어휘 있으나 SPECIAL        :  11          (EX-01 부분집합)
EX-05 Replay FAIL (어휘=실제 모순)    :   8          영향도 MEDIUM
```

## STEP 2 — Root Cause (Evidence만)
- **EX-01:** SPECIAL_FACILITY 113건의 대상 키워드 분포 — 장애인 42·의료 31·노인 13·전기 10·임산부 3·학교 3·어린이 1. 원문에 '건축물/사업장' 어휘가 있어도 대상이 이 특수 계층이면 SPECIAL. **결정 근거가 어휘가 아니라 대상 성격.**
- **EX-02:** 실제 sectors가 2개 이상인 매핑 166건. 한 법령이 복수 sector에 정당하게 적용(WO-MAPPING-001 소방 다패턴과 정합).
- **EX-03/04:** 시설(61)·업종(11) 어휘를 가진 SPECIAL 매핑 = EX-01이 어휘 규칙과 충돌하는 발현 형태.
- **EX-05:** 직접명시 어휘 예측이 실제와 모순 8건(의료기기법·장애인고용촉진법 등, WO-EVIDENCE-001 오탐과 동일).

## STEP 4 — Exclusiveness
- EX-01 ⊇ EX-03 + EX-04 + (EX-05 일부): EX-03/04/05는 **EX-01의 부분집합/발현 형태**, 독립 아님.
- EX-02(MULTI)는 EX-01과 대개 독립(SPECIAL 단독은 MULTI 아님), 부분 겹침 가능.
- **근본 예외 = 2종: EX-01(대상 우선) + EX-02(MULTI).** 나머지 3개는 EX-01의 발현.

## STEP 5 — Priority (sector 결정 아님, 처리 순서만)
```text
[먼저 처리] EX-01 대상 특수성 → SPECIAL_FACILITY
   113건(29%). 어휘 규칙보다 우선 적용. 대상 목록(장애인·의료·노인·임산부·어린이·전기설비)이
   판단 기준 — 목록 확정 자체는 Policy(도메인 판단).
[먼저 처리] EX-02 MULTI
   166건(42%). 단일 sector 강제 금지. MULTI 허용 규칙 자체는 규칙화 가능, 조합은 개별.
[나중 처리] EX-03/04 (EX-01에 흡수)
   72건. EX-01 대상 우선 규칙이 서면 자동 해소, 별도 처리 불필요.
[Policy 필요] EX-05 Replay FAIL
   8건. 어휘로 설명 안 되는 순수 대상 판단, 개별 확인 불가피.
```

## STEP 6 — Independent Review
- 예외 종류: 근본 2종(EX-01, EX-02) + EX-01 발현 3종.
- 충돌: EX-01과 EX-02가 한 법령에 동시 가능(장애인 관련 + 복수 sector). **우선순위 규칙: EX-01(대상 우선) 먼저 판정 → 그 후 MULTI 여부.**

## STEP 7 — Independent Audit
```text
Inventory     : PASS (EX-01~05 전량, 새 유형 0)
Frequency     : PASS (113/166/61/11/8, 대상 키워드 분포 확인)
Exclusiveness : PASS (EX-01 포함관계·EX-02 독립 확인)
Priority      : PASS (먼저 2·나중 1·Policy 1, sector 미결정)
```

## STEP 8 — Freeze
```text
Exception Inventory : EX-01 대상우선 113 · EX-02 MULTI 166 · EX-03 61 · EX-04 11 · EX-05 8
Frequency Report    : EX-01 29%·EX-02 42% (합쳐 대다수), 대상 키워드=장애인/의료/노인/전기/임산부
Priority Matrix     : EX-01·EX-02 먼저 / EX-03·04 흡수 / EX-05 Policy
Review              : PASS (근본 2종, 우선순위 EX-01→EX-02)
Audit               : PASS
```

## 결론 — 번역표의 제약조건 확정
- 번역표는 **이중 구조 + 우선순위**여야 한다(정답지가 강제):
  1. **EX-01 우선:** 대상이 특수 계층(장애인·의료·노인·임산부·어린이·전기설비 등)이면 → SPECIAL_FACILITY. **어휘 규칙보다 먼저.**
  2. **EX-02:** 복수 sector 허용(단일 강제 금지).
  3. 그 다음에야 어휘 규칙(시설명·업종명 → sector).
- EX-01 대상 목록 확정과 EX-05 8건은 Policy(도메인 판단)로 남음 — 본 WO는 결정 안 함.
- 이 Taxonomy를 무시한 일반 규칙(건축물→BUILDING 등 단순 번역)은 113건(29%)을 기존 판단과 반대로 매핑하므로 금지.

## Exit Criteria 점검
```text
[v] Exception 전량 분류 (EX-01~05)
[v] Root Cause 완료 (대상 키워드 분포)
[v] Frequency 완료
[v] Priority 완료
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑪ Decision Model             ✓ WO-MODEL-001
⑫ Model Verification         ✓ WO-MODEL-002
⑬ Evidence Reconstruction    ✓ WO-EVIDENCE-001
⑭ Exception Taxonomy         ✓ WO-MAPPING-004 (EX-01 대상우선 113·EX-02 MULTI 166) ← 현재
⑮ 번역표 수립(EX 제약 하)     ← 다음 (EX-01 대상목록 Policy 확정 후)
⑯ DB 반영 CHG + Verify       ← WO-CHG-005
```
