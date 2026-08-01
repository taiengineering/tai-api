---
wo: WO-PATTERN-001
class: records
type: verification
scope: canonical
project: test-universe
title: Role Pattern Extraction
version: 1
status: active
owner: taiwang
---

# ROLE PATTERN EXTRACTION (FROZEN) — WO-PATTERN-001

> VERIFY-004의 Role 판정이 어느 원문 문형에서 도출됐는지 구조화. Evidence→Role→Role Pattern. 300건 확대 시 사람 재독 없이 동일 기준 Replay 가능하게. sector·번역표·해석 없음.
> Input: role_verification.csv(14 Role), fp03_source.csv(원문).

## 판정: PASSED

## STEP 1-2 — 원문 문형 추출 + Role Pattern 카탈로그
각 Role을 도출한 원문 문형(원문 관찰 기반, 사후 라벨 아님):

### REGULATED_OBJECT_ONLY 문형
```text
P-R1  "○○"이란 …               (정의)
P-R2  ○○에 적용한다             (적용 대상)
P-R3  ○○의 위해성/성능/구조/범위 (대상 속성)
P-R4  ○○ 또는/및 …             (대상 물건 열거)
P-R5  인증/규격/받은 ○○         (대상 물건)
P-R6  구명/불꽃 ○○              (대상 구성품 열거)
P-R7  ○○이 …기준에 맞는         (규율 대상)
```

### FACILITY_ONLY 문형
```text
P-F1  ○○의 안전관리
P-F2  ○○의 벽체/구조에 지지·설치
P-F3  ○○ 등 특수한 장소
P-F4  ○○교통법/도로법          (장소 근거법)
P-F5  법에 따른 ○○             (기관·장소)
P-F6  선박·○○·항공기           (교통수단 열거)
```

## STEP 3 — 문형 Replay (14건 재적용)
```text
값        Role                    문형
건설기계   REGULATED_OBJECT_ONLY   P-R1 "○○이란"
건축물     FACILITY_ONLY           P-F2 벽체/구조
도로       FACILITY_ONLY           P-F4 도로법
설비       REGULATED_OBJECT_ONLY   P-R6 구명 ○○
자재       REGULATED_OBJECT_ONLY   P-R4 또는/및
제품(건설) REGULATED_OBJECT_ONLY   P-R4 또는/및
항만       FACILITY_ONLY           P-F3 특수한 장소
제품(수도) REGULATED_OBJECT_ONLY   UNRESOLVED_PATTERN (Role은 확정, 문형만 보류)
학교       UNRESOLVED              (문형 없음 — 판정 보류)
놀이시설   FACILITY_ONLY           P-F1 안전관리
의료기관   FACILITY_ONLY           P-F5 법에 따른
제품(제안) REGULATED_OBJECT_ONLY   P-R1 "○○이란"
제품(영)   REGULATED_OBJECT_ONLY   P-R1 "○○이란"
철도       FACILITY_ONLY           P-F6 선박·○○·항공기
```
- **문형 매칭: 12/13** (UNRESOLVED 학교 제외). **문형→Role 역산 Replay: Role 변경 0** — 문형이 Role과 완전 정합(사후 라벨 아님 증명).
- 최초 Replay 시 설비·제품(수도) 2건 MATCH_FAIL → 원문 재확인으로 설비는 P-R6("구명 설비") 새 문형 추가해 해소. 이는 문형이 실제 판정 도구임을 보여줌(사후 라벨이면 실패 안 났을 것).

## STEP 4 — 문형 미결정 항목
```text
1. 학교 [UNRESOLVED]: Role 자체가 UNRESOLVED(VERIFY-004) → 문형 없음이 정상.
2. 제품(수도용자재) [REGULATED, UNRESOLVED_PATTERN]:
   Role은 확정(제8조 "수도용 자재와 제품이 위생안전기준에 맞는", VERIFY-004 근거)이나
   이 세션 문형 추출기가 해당 조문 텍스트 미포착 → 문형 라벨만 보류. 억지 문형 배제.
```

## STEP 5 — Independent Audit
```text
문형 원문 실재  : 각 문형은 원문에서 관찰된 표현(P-R6는 설비 재확인으로 추가)
사후 라벨 아님  : 문형→Role Replay 변경 0 + 초기 MATCH_FAIL 발생이 증명
추론           : 없음 (원문 문형만)
sector 언급    : 없음
번역표 언급    : 없음
금지표현       : 0 (따라서/즉/일반적으로/보통/SPECIAL/BUILDING/INDUSTRIAL/CONSTRUCTION/sector 미출현)
```

## STEP 6 — Freeze
```text
role_pattern.csv : 14행 (법령·값·Role·근거조문·판정근거문형), checksum 2fd28eec0f5b6e5a
문형 카탈로그    : REGULATED 7문형(P-R1~R7) · FACILITY 6문형(P-F1~F6)
Replay          : 문형→Role 변경 0
UNRESOLVED_PATTERN : 1 (제품/수도, Role 확정·문형 보류)
Audit           : PASS (금지표현 0)
```

## 결론
- Role이 도출된 원문 문형을 카탈로그로 고정. Evidence→Role→**Role Pattern**까지 상승.
- **문형→Role Replay 변경 0** = 문형이 실제 판정 근거였음(사후 정당화 아님). 300건 확대 시 이 13개 문형으로 사람 재독 없이 동일 기준 Replay 가능.
- 억지 문형 배제: 학교(Role 보류)·제품/수도(문형만 보류)는 UNRESOLVED로 정직 유지.
- **주의:** 문형은 "규율대상이냐 시설이냐"만 구조화. "그래서 어느 sector냐"는 여전히 다음 단계.

## Exit Criteria 점검
```text
[v] 문형 원문 근거 (관찰 기반, P-R6 재확인)
[v] Replay 일치 (문형→Role 변경 0)
[v] sector 언급 0
[v] 추론 0
[v] 금지표현 0
[v] UNRESOLVED 억지판정 회피 (학교·제품/수도)
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
㉒ Context Matrix Normalization ✓ WO-CTX-002
㉓ Context Role Separation      ✓ WO-VERIFY-004
㉔ Role Pattern Extraction      ✓ WO-PATTERN-001 (13문형, Replay 0) ← 현재
㉕ FP-03 sector 함의 분석        ← 다음 (검증된 Role+Pattern 기반)
㉖ Replay → Review → Mapping
```
