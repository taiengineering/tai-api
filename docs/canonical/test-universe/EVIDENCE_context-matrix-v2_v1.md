---
wo: WO-CTX-002
class: records
type: evidence
scope: canonical
project: test-universe
title: Context Matrix Normalization
version: 1
status: active
owner: taiwang
---

# CONTEXT MATRIX NORMALIZATION (FROZEN) — WO-CTX-002

> fp03_context_matrix.csv를 조문번호까지 보존한 long format으로 정규화. 규율대상/시설 중복 명시. sector 판단·해석 없음.
> Input: fp03_evidence_sheet_v2.csv(AUDIT-004 KEEP), fp03_context_matrix.csv(CTX-001).

## 판정: PASSED

## 정규화 결과 — long format (법령·필드·값·근거조문·근거횟수)
- 총 83 레코드. wide format(7법령×9컬럼)에서 각 Context 값을 한 행으로 펼치고 **근거 조문번호를 전량 보존**.

### 예시 (조문번호 추적 가능)
```text
법령            필드      값       근거조문                  근거횟수
제품안전기본법   사람     어린이    제4조, 제7조                2
제품안전기본법   사람     장애인    제4조, 제7조                2
제품안전기본법   사람     근로자    제14조, 제17조              2
어린이놀이시설법 사람     설치자    제11,13,15,23조             4
어린이놀이시설법 사람     어린이    제13,15,16조                3
어린이놀이시설법 사람     관리주체  제2,21조                    2
건설기계        규율대상  건설기계  23조문(제2조 등)             23
```

## 확인 1 — 규율대상/시설 중복 (명시)
- **규율대상 == 시설: 7/7 법령에서 값+조문번호까지 완전 동일.**
- 원인: WO-CHG-008이 두 필드에 동일 `token_extract(txt, FACIL)` 적용 → 별개 추출이 아니라 복제.
- **이 WO는 사실만 기록.** "이것이 시설인가 규율대상인가 둘 다인가"의 역할 분리는 CTX 분석(다음 WO)의 몫 — 지금 분리하면 해석이 되어 CTX 범위 초과.

## 확인 2 — 조문번호 보존·검증
- 모든 Context 값에 근거 조문번호 리스트 부착(어린이→제4조,제7조 등).
- **근거조문 원문 존재 검증: 0 오류** (모든 근거조문이 실제 원문 조문에 존재).
- 값 실재 표본: 제품안전기본법 제4조에 '어린이' 실제 등장 확인.
- 효과: CTX 분석/Replay에서 "왜 이 값이 들어갔나"를 원문 전체 재탐색 없이 조문번호로 즉시 추적.

## 확인 3 — 재현성
- 재생성 2회 동일: True. Matrix v2 checksum af8568119940641d. 83 레코드.

## Freeze
```text
fp03_context_matrix_v2.csv : long format (법령·필드·값·근거조문·근거횟수), 83 레코드
규율대상/시설 중복          : 7/7 동일, CHG-008 동일 추출 탓, 역할분리는 CTX 분석 몫(기록)
조문번호 검증              : 근거조문 원문 존재 0 오류
재현성                    : checksum af8568119940641d
```

## 결론
- Context Matrix를 조문번호 보존 long format으로 정규화 완료. 각 Context 값이 어느 조문에서 나왔는지 추적 가능(재검증 비용 대폭 감소).
- 규율대상/시설 중복(동일 추출)은 명시하되 역할 분리는 하지 않음(CTX 분석 몫).
- sector 판단·해석 0. 원문 근거·조문번호만.
- 다음: 이 정규화된 Matrix v2를 근거로 FP-03 Context 분석/분류(규율대상 vs 시설 역할 분리 포함) — 검증·추적 가능한 입력 위에서.

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑳ Evidence v2 Independent Audit ✓ WO-AUDIT-004
㉑ FP-03 Context Reconstruction ✓ WO-CTX-001 (wide, 근거조문수)
㉒ Context Matrix Normalization ✓ WO-CTX-002 (long, 조문번호 보존) ← 현재
㉓ FP-03 Context 분석/분류      ← 다음 (역할 분리·sector 함의)
㉔ Replay → Review → Mapping
```
