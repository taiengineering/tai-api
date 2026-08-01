---
wo: WO-VERIFY-002
class: records
type: analysis
scope: canonical
project: test-universe
title: Exception False Positive Analysis
version: 1
status: active
owner: taiwang
---

# EXCEPTION FALSE POSITIVE ANALYSIS (FROZEN) — WO-VERIFY-002

> EX-01 오탐 28건의 원인을 전량 분해. 대상 목록 수정·번역표·sector 변경·DB 수정 없음. 오탐 원인을 검증 가능한 형태로 고정.
> Input: WO-VERIFY-001 오탐 28, Replay 결과, 원문 Evidence.

## 판정: PASSED

## STEP 1 — False Positive Inventory (28건 전량)
- 예: 전기공사업법→{BUILDING,CONSTRUCTION}(예측 SPECIAL), 전기사업법→{BUILDING,INDUSTRIAL}, 전기안전관리법→{BUILDING,INDUSTRIAL}, 전기용품법→{BUILDING,INDUSTRIAL}, 건설폐기물 재활용법→{CONSTRUCTION}, 어린이놀이시설법→{BUILDING,INDUSTRIAL}, 제품안전기본법→{INDUSTRIAL}.
- 전량 목록: fp_analysis.json (law_id·name·실제 sector·예측·키워드).

## STEP 2-3 — Root Cause Classification + Frequency
```text
FP-01 부분 문자열 매칭 : 21 (75.0%)
FP-02 동음이의        :  0
FP-03 맥락 부족       :  7 (25.0%)
FP-04 원문 구조       :  0
FP-05 기타           :  0
```
- **FP-01 (21):** 키워드가 더 긴 단어의 일부. "전기"⊂전기공사·전기사업·전기용품·전기안전·전기공급·전기설비 (18건), "재활"⊂재활용 (3건). 단어 경계 무시.
- **FP-03 (7):** 키워드는 정확히 매칭되나 대상이 SPECIAL 아님. 어린이놀이시설(어린이 정확하나 =시설물, BUILDING) 3건, 제품안전기본법·수도용자재·건설기계(전기 언급되나 SPECIAL 대상 아님) 4건.

## STEP 4 — Exclusiveness
- **전 28건 단일 원인, 복합 0.** 각 오탐이 하나의 원인에만 귀속.

## STEP 5 — Independent Review (키워드/구현/Evidence 중 무엇)
- **FP-01 (75%) = Replay 구현 문제.** `"전기" in "전기공사업법"`=True — 부분 문자열 매칭이 단어 경계를 무시한 결과. 키워드 "전기" 선정 자체가 아니라 **매칭 방식**의 결함. 매칭을 단어/토큰 단위로 바꾸면 목록 수정 없이 해소.
- **FP-03 (25%) = 키워드/맥락 문제.** 키워드가 정확히 잡혔는데도 대상이 SPECIAL 아님(어린이놀이시설=BUILDING). **목록/맥락 규칙 정제** 필요.
- **Evidence 문제 = 없음.** 원문·실제 sector 데이터는 정확. 오탐은 예측 규칙 탓.
- **핵심 결론:** "키워드가 문제"는 25%만 맞음. 75%는 매칭 구현(부분 문자열). **정제 방법이 갈림.**

## STEP 6 — Independent Audit
```text
Inventory     : PASS (28 전량)
Classification: PASS (FP-01 21·FP-03 7, FP-02/04/05 = 0)
Frequency     : PASS (75%/25%)
Exclusiveness : PASS (전건 단일 원인)
특기: 원인이 2종(FP-01·FP-03)에 집중. 동음이의·원문구조·기타 0.
```

## STEP 7 — Freeze
```text
False Positive Inventory : 28건 (fp_analysis.json)
Root Cause Matrix        : FP-01 21(75%) · FP-03 7(25%)
Frequency Report         : 부분문자열 매칭 우세, 단일원인 100%
Review                   : 75% 구현 문제 / 25% 맥락 문제 / Evidence 무결
Audit                    : PASS
```

## 결론 — 정제 방법이 원인별로 갈림
- **오탐의 75%는 대상 목록의 문제가 아니라 매칭 구현(부분 문자열)의 문제.** "전기"를 목록에서 빼는 게 아니라(전기설비 관리 맥락에선 SPECIAL일 수 있음), 매칭을 단어 경계/토큰 기반으로 바꾸면 21건이 자동 해소.
- **나머지 25%(FP-03)만 목록/맥락 정제 대상** — 어린이놀이시설처럼 키워드는 맞으나 대상이 SPECIAL 아닌 경우. 이건 "키워드→대상 성격" 판단이 필요(예: 어린이놀이시설은 시설물이지 취약계층 대상 아님).
- **이 분해가 없었다면** "전기를 목록에서 제거"라는 잘못된 정제로 갔을 것 — 그럼 전기설비 관리자 선임 같은 진짜 SPECIAL 사례까지 놓쳤을 수 있음. 원인이 매칭 방식임을 확정해, 목록은 건드리지 않고 매칭만 고치는 방향이 드러남.

## 다음 (관측 — 판단 아님)
- FP-01 해소: 매칭을 부분 문자열→단어/토큰 경계 기반으로 변경(WO-VERIFY-001 Replay 재실행 시). 목록 불변.
- FP-03 해소: 어린이놀이시설·제품안전 등 7건의 대상 성격을 개별 확인(키워드 정확하나 SPECIAL 아님) → EX-01 대상 정의에 맥락 조건 추가 여부는 Policy.

## Exit Criteria 점검
```text
[v] FP 28건 전량 분류
[v] Root Cause 완료 (FP-01/FP-03)
[v] Frequency 완료 (75%/25%)
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑭ Exception Taxonomy         ✓ WO-MAPPING-004
⑮ Exception Replay Verify    ✓ WO-VERIFY-001 (오탐 28)
⑯ FP Analysis               ✓ WO-VERIFY-002 (FP-01 매칭구현 75% · FP-03 맥락 25%) ← 현재
⑰ 매칭 방식 교정 + 목록 정제   ← 다음 (FP-01 단어경계, FP-03 맥락)
⑱ 번역표 수립                ← 그 후
⑲ DB 반영 CHG + Verify       ← WO-CHG-005
```
