---
wo: WO-VERIFY-004
class: records
type: verification
scope: canonical
project: test-universe
title: Context Role Separation Verification
version: 1
status: active
owner: taiwang
---

# CONTEXT ROLE SEPARATION VERIFICATION (FROZEN) — WO-VERIFY-004

> fp03_context_matrix_v2.csv에서 규율대상==시설 동시 기록 항목의 역할을 원문으로 검증. Role Separation만 — 번역표·sector·해석·신규 추출 없음. 억지 판정 금지.
> Input: fp03_context_matrix_v2.csv, fp03_source.csv(523 원문).

## 판정: PASSED

## STEP 1 — Duplicate Inventory
- **규율대상==시설 동시 존재: 14건, 누락 0.** 전부 근거조문까지 동일(CHG-008 복제 확인).
- 대상: 건설기계 규칙 7(건설기계·건축물·도로·설비·자재·제품·항만)·수도용자재 2(제품·학교)·어린이놀이시설 1(놀이시설)·제품안전기본법 2(의료기관·제품)·제품안전 시행령 2(제품·철도).

## STEP 2-3 — 원문 정독 + Role 판정
```text
값        Role                    근거조문   원문 근거(발췌)
건설기계   REGULATED_OBJECT_ONLY   2;5       "건설기계"란 정의·이 규칙은 건설기계에 적용
건축물     FACILITY_ONLY           125       건축물의 벽체에 지지
도로       FACILITY_ONLY           136;170   도로교통법 제2조에 따른 도로
설비       REGULATED_OBJECT_ONLY   91;94     구명 설비(건설기계 구조 일부)
자재       REGULATED_OBJECT_ONLY   45;125    자재 또는 이물질이 부착
제품(건설) REGULATED_OBJECT_ONLY   125;150   한국산업규격 제품·인증받은 제품
항만       FACILITY_ONLY           35        항만 등 특수한 장소에서 사용
제품(수도) REGULATED_OBJECT_ONLY   8;16      수도용 자재와 제품이 위생안전기준에 맞는
학교       UNRESOLVED              3         학교·연구기관 등의 범위(기관 열거)
놀이시설   FACILITY_ONLY           23        어린이놀이시설의 안전관리
의료기관   FACILITY_ONLY           15        의료법 제3조에 따른 의료기관
제품(제안) REGULATED_OBJECT_ONLY   3;7;9     "제품"이란 소비자가 최종 사용하는
제품(영)   REGULATED_OBJECT_ONLY   4;5;8     제품의 위해성 시험·검사
철도       FACILITY_ONLY           14        선박·철도·항공기 등의 운전
```

## STEP 3 — 판정 분포
```text
REGULATED_OBJECT_ONLY : 7  (건설기계·설비·자재·제품(건설)·제품(수도)·제품(제안)·제품(영))
FACILITY_ONLY         : 6  (건축물·도로·항만·놀이시설·의료기관·철도)
BOTH_VALID            : 0
UNRESOLVED            : 1  (수도용자재 학교 — 기관 열거, 역할 불명)
```

## 근거조문 정정 기록
- 수도용자재 "제품": 초기 근거를 제2조로 적었으나 실제 근거조문은 제8·16조. 원문 재확인(제8조 "인증심의 결과 수도용 자재와 제품이 위생안전기준에 맞는", 제16조의2 "수도용 자재나 제품의 수거") → 인증·규율 대상 확정, REGULATED 유지·근거조문 정정.

## STEP 4 — Evidence Sheet
- role_verification.csv (14행, long format: 법령·값·Role·근거조문·원문발췌·판정). 모든 행 원문 근거 보유.

## STEP 5 — Independent Replay
- 동일 근거로 재판정: **Role 변경 0.** 판정 규칙(정의/적용/인증대상→REGULATED, 장소/구조물/기관→FACILITY, 단순 열거 불명→UNRESOLVED)이 재적용 시 동일 결과.

## STEP 6 — Independent Audit
```text
근거조문 존재  : 14/14 (STEP1 확인)
원문 일치      : 발췌 전부 원문 실재
추론          : 없음 (원문 문형·정의만 사용)
sector 언급   : 없음
번역표 언급   : 없음
금지표현      : 0 (따라서/즉/일반적으로/보통/SPECIAL/BUILDING/INDUSTRIAL/CONSTRUCTION/sector 미출현)
```

## STEP 7 — Freeze
```text
Duplicate 대상 수 : 14
BOTH_VALID        : 0
REGULATED_OBJECT_ONLY : 7
FACILITY_ONLY     : 6
UNRESOLVED        : 1
Replay            : Role 변경 0
Audit             : PASS (금지표현 0)
Limitations       : 판정은 근거조문 원문 문형에 의거. UNRESOLVED 1건(학교)은 억지 판정 회피. 다의어(제품이 여러 법령서 반복)는 법령별 개별 판정.
```

## 결론
- 14건 중 13건 원문으로 역할 분리 확정(REGULATED 7·FACILITY 6), 1건(학교) UNRESOLVED로 정직 보류.
- **규율대상/시설 복제(CHG-008)가 원문상 서로 다른 역할이었음이 확인** — 건설기계=규율대상, 건축물/도로/항만/놀이시설/의료기관/철도=시설. 두 필드가 동일 값이었으나 실제 역할은 분리됨.
- sector·번역표·해석 0. 이 Role 정보는 이후 CTX 분석·Mapping의 검증된 기반.
- **주의:** 이 WO는 "규율대상이냐 시설이냐"만 판정. "그래서 어느 sector냐"는 여전히 다음 단계(sector 함의 분석)의 몫.

## Exit Criteria 점검
```text
[v] Duplicate Inventory 완료 (14, 누락 0)
[v] 원문 정독 완료
[v] Role 판정 완료 (REGULATED 7·FACILITY 6·UNRESOLVED 1)
[v] Replay 동일 (변경 0)
[v] Audit PASS
[v] 신규 추론 0
[v] Sector 언급 0
[v] 번역표 생성 0
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
㉑ FP-03 Context Reconstruction ✓ WO-CTX-001
㉒ Context Matrix Normalization ✓ WO-CTX-002 (조문번호 보존)
㉓ Context Role Separation      ✓ WO-VERIFY-004 (REGULATED 7·FACILITY 6·UNRESOLVED 1) ← 현재
㉔ FP-03 sector 함의 분석        ← 다음 (검증된 Role 기반)
㉕ Replay → Review → Mapping
```
