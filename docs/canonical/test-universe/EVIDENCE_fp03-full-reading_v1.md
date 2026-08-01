---
wo: WO-READ-001
class: records
type: evidence
scope: canonical
project: test-universe
title: FP-03 Full Evidence Reading
version: 1
status: active
owner: taiwang
---

# FP-03 FULL EVIDENCE READING (FROZEN) — WO-READ-001

> FP-03 7개 법령 523개 조문 전량 정독. **판단·Classification·CTX·Replay 없음. 원문 Evidence만 확보.** 발췌(200자)로 여러 번 교정이 일어났으므로, 전체를 Evidence로 고정한 뒤 Context를 재수행하기 위함.
> Input: fp03_source.csv (523 조문 전문).

## 판정: PASSED — READ COMPLETE 523/523

## STEP 1-3 — 전량 정독 + Evidence Sheet
- 523개 조문을 처음부터 끝까지 읽고, 조문마다 원문에 실제로 등장하는 것만 기록(law_name·article·원문·적용대상·규율대상·시설·업종·사람·행위). 원문에 없는 항목은 공란. 판단·요약·분류 없음.
- 산출: fp03_evidence_sheet.csv (523행, 원문 전문 보존).

### 발췌로는 못 봤던 원문 사실 (정독으로 확보 — 기록만, 판단 아님)
- **건설기계 안전기준 규칙 제5조(적용범위):** "이 규칙은 건설기계에 적용하고… 「산업표준화법」 한국산업표준이 정하는 바에 따른다." (적용범위 조문이 제1조가 아니라 제5조에 별도 존재 — 발췌 200자엔 없었음)
- **수도용 자재 인증규칙 제2조:** "인증을 받아야 하는 수도용 자재와 제품의 범위는 별표 1과 같다." + 제3조 "학교·연구기관 등의 범위".
- **어린이놀이시설법 제2조(정의):** "'어린이놀이기구'란… 「어린이제품 안전 특별법」 제2조제9호에 따른 안전인증대상어린이제품."
- **제품안전기본법 제2조:** "제품의 생산·조립·가공이나 수입·판매·대여 또는 사용과 관련된 행위."

## STEP 4 — READ COMPLETE
```text
READ COMPLETE : 523 / 523
법령별: 건설기계 295 · 수도용자재 31 · 어린이놀이시설법 46 · 시행규칙 26 · 시행령 27 · 제품안전기본법 47 · 시행령 51
```

## STEP 5 — Independent Review
- 523 전량 읽음(Evidence Sheet 523행). 법령별 DB 조문 수 = 예상 = Sheet 수, 전부 OK. 누락 없음.

## STEP 6 — Independent Audit
```text
조문 수 : 523 (기대 523) — PASS
빈 조문 : 0 — PASS
중복    : 4 — 실제 중복 아님(제1조가 '장 제목'과 '조문'으로 이원 저장된 DB 구조, 정독 누락 아님)
누락    : 없음
```

## STEP 7 — Freeze
```text
Evidence Sheet : fp03_evidence_sheet.csv (523행, 원문 전문)
Reading Log    : 7법령 523조문, READ COMPLETE 523/523
Review         : PASS (전량·무누락)
Audit          : PASS (523·빈0·중복4는 DB구조·누락0)
```

## 결론
- FP-03 7법령 523조문 전량 정독 완료. 원문 Evidence 확보·고정.
- **이 WO는 읽기만 수행 — CTX·분류·Replay·판단 없음.** 앞선 e4c7d915의 발췌(200자) 기반 CTX 분류는 이 전문 Evidence로 대체될 예정(별도 WO).
- 다음(별도): 이 523조문 Evidence Sheet를 근거로 Context·Classification·Replay 재수행.

## Exit Criteria 점검
```text
[v] 523개 조문 전량 정독
[v] Evidence Sheet 작성 (523행)
[v] READ COMPLETE (523/523)
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑰ Matching Correction(FP-01) ✓ WO-CHG-007
⑱ FP-03 Context(발췌기반)     ~ e4c7d915 (발췌 한계, 대체 예정)
⑱' FP-03 Source Collection    ✓ WO-VERIFY-003(수정) (523조문 확보)
⑱" FP-03 Full Reading         ✓ WO-READ-001 (523/523 정독) ← 현재
⑲ FP-03 Context 재수행        ← 다음 (523 Evidence 근거, e4c7d915 대체)
⑳ 번역표 수립                ← 그 후
```
