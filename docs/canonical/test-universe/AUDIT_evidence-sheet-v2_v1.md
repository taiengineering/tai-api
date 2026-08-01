---
wo: WO-AUDIT-004
class: records
type: audit
scope: canonical
project: test-universe
title: Evidence Sheet v2 Independent Audit
version: 1
status: active
owner: taiwang
---

# EVIDENCE SHEET v2 INDEPENDENT AUDIT (FROZEN) — WO-AUDIT-004

> fp03_evidence_sheet_v2.csv가 원문을 정확히 반영했는지 독립 검증. READ→QA→CHG-008이 전부 같은 구현 산출물이므로 독립 검증자 부재를 보완. '분류가 맞는가'가 아니라 'CHG-008이 정말 원문만 반영했는가'. CTX·sector·Policy 없음.

## 판정: KEEP WITH LIMITATION

## STEP 1 — 523행 전수 확인
- 행수 523/523. 원문 checksum 44cd9b2894bb3f64 = CHG-008 기록과 동일.
- **원문 무결성 독립 대조:** 처음 dict 매핑(law_name+article+title)으로 대조 시 불일치 2·못찾음 31 발생 → 조사 결과 **검증자 쪽 결함**(src 내 중복 키 3종 7행: 수도용자재 제16조 3회 등 빈 title 하위항목이 dict에서 덮어써짐)임을 규명. **순서(행 위치) 기반 1:1 재대조: 원문 불일치 0/523.** v2 원문 == src article_text 완전 일치. CHG-008이 원문을 건드리지 않았음이 독립 확인됨.

## STEP 2-3 — 층화표본 원문 대조
- 표본: 7법령 각 무작위 5행 = 35행 (seed 404).
- 원문↔Sheet 파생 필드 대조(사람·시설·업종·행위), 독립 규칙(원문에서 키워드가 단독 토큰=앞뒤 비한글로 등장하면 정당).

## STEP 4 — 오추출·누락·과잉추출
```text
과잉추출(원문 근거 없는데 추출) : 0
누락(원문 단독인데 빠짐)        : 0
```

## STEP 5 — FN=0 독립 확인
- CHG-008의 FN=0 주장을 표본 아닌 **전수**로 독립 재확인: 사람 필드 FN 0.
- 한계: 본 확인도 CHG-008과 동일한 '단독 토큰'(앞뒤 비한글) 정의를 사용 → '같은 정의 하 재현'이지 '정의 자체의 타당성' 증명은 아님. (STEP6가 이를 일부 보완)

## STEP 6 — 재현성
- **독립 재구현으로 검증:** CHG-008은 '앞뒤 문자 검사' 방식, 본 Audit은 'regex lookahead/lookbehind' 방식 — 서로 다른 구현.
- 사람·시설·업종·행위 전 셀 대조: **불일치 0.** 두 독립 구현이 완전 일치 → 파생 필드는 구현 방식에 의존하지 않는 재현 가능 결과. STEP5의 정의 한계를 구현 독립성으로 일부 보완.

## STEP 7 — Audit 판정: KEEP WITH LIMITATION
```text
원문 불일치 : 0 (순서 대조 523/523, checksum 동일)
오추출      : 0 (표본 과잉 0)
신규 FN     : 0 (전수 독립 확인)
재현성      : PASS (독립 재구현 완전 일치)
```
- **KEEP** 근거: Exit 4조건(원문 불일치 0·오추출 0·신규 FN 0·재현성 PASS) 전부 충족. CHG-008이 원문만 반영하고 파생 필드를 정확히 재생성했음이 독립 확인.
- **LIMITATION** 근거: (1) 검증자가 동일 주체(완전 외부 감사 아님). (2) '단독 토큰' 정의를 Audit도 공유(정의 자체는 재검증 대상 아님) — 단 STEP6 구현 독립성이 이를 부분 완화. (3) 표본 35행 + 전수 자동 대조 병행이나, 의미 층위(예: 어떤 사람 어휘가 '규율 대상'인지)는 이 Audit 범위 밖(CTX에서 다룸).

## Exit Criteria 점검
```text
[v] 원문 불일치 0
[v] 오추출 0
[v] 신규 FN 0
[v] 재현성 PASS
```

## 결론
- **Evidence Sheet v2 = 독립 검증 통과한 신뢰 가능 입력.** 원문 무결(순서 대조 무손상), 파생 필드 정확(과잉·누락 0), 재현 가능(독립 구현 일치).
- 명시된 한계(동일 검증자·공유 정의) 하에서 KEEP. 완전 외부 감사가 필요하면 별도 주체 필요하나, 현 체계(생성→QA→CHG→Independent Audit)로 도달 가능한 신뢰도는 확보.
- **이제 CTX-001 진행 가능** — v2를 신뢰 입력으로 삼아 FP-03 Context 분류를 원문 기반으로 수행(e4c7d915 발췌 분류 대체).

## 품질관리 체계 (확립됨)
```text
생성(READ) → QA → CHG(재생성) → Independent Audit → 다음 단계
이 체계를 이후 CTX·Replay·Mapping·Policy에도 동일 적용.
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑱‴ Evidence Sheet QA          ✓ WO-QA-READ-001 (파생 FAIL 78)
⑲ 파생 필드 재생성            ✓ WO-CHG-008 (v2, 오탐 0·FN 0)
⑳ Evidence v2 Independent Audit ✓ WO-AUDIT-004 (KEEP WITH LIMITATION) ← 현재
㉑ FP-03 CTX-001              ← 다음 (v2 독립검증 통과 입력)
㉒ Replay → Review
```
