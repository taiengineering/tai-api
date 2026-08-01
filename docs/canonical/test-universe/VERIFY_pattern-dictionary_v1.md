---
wo: WO-PATTERN-002
class: records
type: verification
scope: canonical
project: test-universe
title: Pattern Dictionary Normalization
version: 1
status: active
owner: taiwang
---

# PATTERN DICTIONARY NORMALIZATION (FROZEN) — WO-PATTERN-002

> role_pattern.csv 자유텍스트 문형을 정규화 Pattern Dictionary로 분리 + Pattern→Role 유일성(N:1 없음) 검증. 300건 확대 시 Pattern 정의 1회 관리·안정적 Replay. sector·번역표·해석 없음.
> Input: role_pattern.csv(14), fp03_source.csv.

## 판정: PASSED

## STEP 1 — Pattern Dictionary (13 문형 정규화)
```text
Pattern_ID  Pattern_Type          Trigger              Role
P-R1        DEFINITION            "○○"이란             REGULATED_OBJECT_ONLY
P-R2        APPLIES_TO            ○○에 적용             REGULATED_OBJECT_ONLY
P-R3        OBJECT_PROPERTY       ○○의 위해성/성능/구조   REGULATED_OBJECT_ONLY
P-R4        ENUM_OBJECT           ○○ 또는/및            REGULATED_OBJECT_ONLY
P-R5        CERTIFIED_OBJECT      인증/규격/받은 ○○      REGULATED_OBJECT_ONLY
P-R6        COMPONENT_ENUM        구명/불꽃 ○○          REGULATED_OBJECT_ONLY
P-R7        MEETS_STANDARD        ○○이 …기준에 맞는       REGULATED_OBJECT_ONLY
P-F1        FACILITY_MANAGEMENT   ○○의 안전관리          FACILITY_ONLY
P-F2        FACILITY_STRUCTURE    ○○의 벽체/구조         FACILITY_ONLY
P-F3        DESIGNATED_PLACE      ○○ 등 특수한 장소       FACILITY_ONLY
P-F4        PLACE_LAW             ○○교통법/도로법         FACILITY_ONLY
P-F5        INSTITUTION_BY_LAW    법에 따른 ○○           FACILITY_ONLY
P-F6        TRANSPORT_ENUM        선박·○○·항공기         FACILITY_ONLY
```
- P-F3 타입명: 최초 SPECIAL_PLACE로 명명했으나 sector 용어(SPECIAL_FACILITY)와 문자열 충돌 → **DESIGNATED_PLACE로 수정**(sector 오인 방지). Trigger 원문("특수한 장소")은 불변.

## STEP 2 — role_pattern_v2.csv (Pattern_ID 참조 정규화)
```text
법령·값·Role·Pattern_ID·근거조문  (문형 자유텍스트 제거, ID 참조)
건설기계→P-R1 · 건축물→P-F2 · 도로→P-F4 · 설비→P-R6 · 자재→P-R4 · 제품(건설)→P-R4
항만→P-F3 · 제품(수도)→UNRESOLVED_PATTERN · 학교→NO_PATTERN · 놀이시설→P-F1
의료기관→P-F5 · 제품(제안)→P-R1 · 제품(영)→P-R1 · 철도→P-F6
```
- 구조: **Pattern Dictionary → role_pattern_v2 → Replay** (문형 정의 1곳 관리).

## STEP 3 — Pattern → Role 유일성 검증 (핵심 Audit)
```text
Dictionary Pattern_ID → Role 유일성 : 위반 없음
실사용 Pattern_ID → Role 유일성      : 위반 없음 (N:1 = 0)
1:N (한 Role에 여러 Pattern)         : 정상 — REGULATED 7문형·FACILITY 6문형
```
- **하나의 Pattern_ID는 언제나 유일한 Role만 생성** (N:1 없음). 대량 Replay 시 문형→Role이 상황 무관하게 결정됨 = 안정성 확보.

## STEP 4 — 참조 무결성 + 재현성
```text
orphan (Dictionary에 없는 Pattern_ID) : 0
Pattern_ID→Role 정합 불일치           : 0 (Dictionary ↔ role_pattern_v2)
pattern_dictionary checksum          : 05e4e92fa8c47641
role_pattern_v2 checksum             : 0f42e770b27bd314
```

## STEP 5 — Independent Audit
```text
Pattern→Role N:1 위반 : 0 (유일성 PASS)
참조 무결성           : orphan 0 · 불일치 0
금지표현              : 0 (P-F3 타입명 수정 후, SPECIAL/BUILDING/INDUSTRIAL/CONSTRUCTION/sector 미출현)
sector 언급           : 없음
```

## Freeze
```text
pattern_dictionary.csv : 13행 (Pattern_ID·Type·Trigger·Role), checksum 05e4e92fa8c47641
role_pattern_v2.csv    : 14행 (Pattern_ID 참조), checksum 0f42e770b27bd314
Pattern→Role           : N:1 위반 0 (유일)
참조 무결성            : orphan 0 · 불일치 0
UNRESOLVED             : 학교(NO_PATTERN)·제품/수도(UNRESOLVED_PATTERN) 유지
```

## 결론
- 자유텍스트 문형을 정규화 Dictionary로 승격. Evidence→Role→Pattern→**Pattern Dictionary**.
- **Pattern→Role 유일성 확정(N:1 없음)** — 동일 Pattern은 언제나 동일 Role. 300건 확대 시 Dictionary 1회 관리로 사람 문자열 재비교 없이 안정 Replay.
- 1:N(한 Role 여러 문형)은 정상 허용. 참조 무결성·재현성 확보.
- P-F3 타입명 sector 충돌 수정(SPECIAL_PLACE→DESIGNATED_PLACE)으로 이후 sector 단계와 용어 혼선 방지.
- **주의:** Pattern은 Role(규율대상/시설)까지만. sector 함의는 다음 단계.

## Exit Criteria 점검
```text
[v] Pattern Dictionary 분리 (13행)
[v] role_pattern ID 참조 정규화
[v] Pattern_ID→Role 유일 (N:1 = 0)
[v] 참조 무결성 (orphan 0·불일치 0)
[v] sector 언급 0
[v] 금지표현 0
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
㉓ Context Role Separation      ✓ WO-VERIFY-004
㉔ Role Pattern Extraction      ✓ WO-PATTERN-001
㉕ Pattern Dictionary Normalize ✓ WO-PATTERN-002 (Dict 13·N:1 위반 0) ← 현재
㉖ FP-03 sector 함의 분석        ← 다음 (검증된 Role+Pattern Dictionary 기반)
㉗ Replay → Review → Mapping
```
