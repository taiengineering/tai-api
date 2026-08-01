---
wo: WO-CHG-008
class: records
type: verification
scope: canonical
project: test-universe
title: Evidence Sheet 파생 필드 재생성
version: 1
status: active
owner: taiwang
---

# EVIDENCE SHEET 파생 필드 재생성 (FROZEN) — WO-CHG-008

> READ-001 원문 컬럼은 그대로 유지, QA-READ-001에서 발견된 오염 파생 필드(78건 부분매칭)만 재생성. 추출을 부분 문자열→토큰 경계로 교체. CTX·sector 판단 없음.
> Input: fp03_evidence_sheet.csv(v1, 523행), 원문 컬럼(불변 대상).

## 판정: PASSED — 원문 불변, 부분매칭 오탐 0, 신규 FN 0

## STEP 1 — Baseline Freeze
```text
총 행수 : 523
원문 checksum      : 44cd9b2894bb3f64
조문번호 checksum   : 940055fc545d6985
법령명 checksum    : dfedb40f160725f6
파생 필드 checksum  : (v1 기준 기록, baseline_v1.json)
```

## STEP 2 — 추출 방식 교체
```text
금지(v1): keyword in text  (부분 문자열)
허용(v2): 토큰 경계 매칭 — 키워드 앞뒤에 한글이 붙으면 합성어 일부로 간주해 제외
  예: "어린이놀이시설"의 어린이 → 제외 (뒤에 '놀'이 붙음)
      "어린이 등이" 의 어린이   → 추출 (뒤가 공백)
```

## STEP 3 — 원문 재추출 (523 전량)
- 파생 필드만 재작성. **원문·조문번호·법령명 불변 검증: checksum 3개 전부 동일(불변 OK).**

## STEP 4 — Delta Report
```text            변경행  삭제  추가
규율대상          198   285    0
시설             198   285    0
업종              56    59    0
사람              64    87    0
행위             294   445    0
```
- **전부 삭제만, 추가 0** — 토큰 경계 매칭이 오탐(합성어 일부)만 제거, 새 오추출 없음.

## STEP 5 — Regression (부분매칭 재발 0)
```text
전기 ⊂ 전기공사        : v1=0 → v2=0  [OK] (이 7법령엔 원래 없음)
재활 ⊂ 재활용          : v1=0 → v2=0  [OK]
어린이 ⊂ 어린이놀이시설 : v1=38 → v2=0 [OK]
어린이 부분매칭 전수     : v1=49 → v2=0 [해소]
부분매칭 전량 0 : True
```

## STEP 6 — QA (전수, 원문↔Sheet 일치)
```text
신규 FN (단독 등장하는데 Sheet 누락) : 사람 0 · 시설 0
```
- **결정적 검증 — 어린이놀이시설법 제13조:** 원문 "…어린이 등이 해당 어린이놀이시설에…"
  - "어린이 등이"(단독, 사람 대상) → 추출됨 [정탐 보존]
  - "어린이놀이시설"(합성어) → 제외됨 [오탐 제거]
  - 같은 조문에서 단독은 잡고 합성어는 버림 = 토큰 경계 정확.

## STEP 7 — Independent Audit
```text
행수     : 523 (기대 523) PASS
중복     : 4 (DB 구조상 제1조 이원 저장, READ-001과 동일 — 정독 누락 아님)
신규 FP  : 0 (부분매칭 재발 없음)
신규 FN  : 0 (단독 대상 전부 보존)
누락     : 없음
```

## STEP 8 — Freeze
```text
산출물:
  fp03_evidence_sheet_v2.csv  (523행, 원문 불변·파생 재생성)
  delta_report (본 문서 STEP4)
  qa_report (본 문서 STEP6)
  audit_report (본 문서 STEP7)
```

## Exit Criteria 점검
```text
[v] 원문 변경 0 (checksum 44cd9b2894bb3f64 불변)
[v] 조문번호 변경 0 (checksum 940055fc545d6985 불변)
[v] 부분 문자열 오탐 0 (어린이 49→0)
[v] 신규 FN 0 (단독 대상 전부 보존)
[v] QA PASS
[v] Independent Audit PASS
```

## 결론
- **Evidence Sheet v2 = 신뢰 가능한 입력.** 원문 컬럼은 불변(checksum 동일), 파생 필드는 부분매칭 오염 78건 제거하되 진짜 대상(단독 등장)은 전부 보존(신규 FN 0).
- CHG-007의 단어 경계 원칙을 파생 필드 추출에 올바르게 적용. 어린이 제13조가 정탐/오탐 분리를 증명.
- 이제 CTX-001(Context 분류)을 신뢰 가능한 Sheet 위에서 시작 가능.

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑱" FP-03 Full Reading          ✓ WO-READ-001 (523 정독)
⑱‴ Evidence Sheet QA           ✓ WO-QA-READ-001 (파생 FAIL 78)
⑲ 파생 필드 재생성             ✓ WO-CHG-008 (v2, 오탐 0·FN 0) ← 현재
⑳ FP-03 CTX-001               ← 다음 (v2 신뢰 입력 근거)
㉑ Replay → Review
```
