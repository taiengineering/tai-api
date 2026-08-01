---
wo: WO-QA-READ-001
class: records
type: verification
scope: canonical
project: test-universe
title: Evidence Sheet Quality Assurance
version: 1
status: active
owner: taiwang
---

# EVIDENCE SHEET QUALITY ASSURANCE (FROZEN) — WO-QA-READ-001

> WO-READ-001이 정말 '읽기'였는지, Evidence Sheet(523행)가 품질 기준을 만족하는지 QA. 새 판단·CTX·Replay 없음. 원문↔Sheet 일치만 검증.
> Input: fp03_evidence_sheet.csv(523행), fp03_source.csv(원문).

## 판정: 원문 컬럼 PASS / 파생 추출 필드 FAIL — Evidence Sheet 재작성 필요

## QA 항목별 결과
```text
QA-1 적용대상 공란인데 원문에 적용범위 조문 : 3건 → 전부 정상(전조등·벌칙 공무원의제는 적용범위 조문 아님, 공란 옳음)
QA-2 사람 필드 부분매칭 오추출              : 45건 FAIL
QA-3 시설 필드 부분매칭 오추출              : 33건 FAIL
QA-4 조문번호 원문 불일치                  : 0건 PASS
QA-6 원문 컬럼 공란                        : 0건 PASS
```

## 핵심 결함 — 파생 필드의 부분 문자열 매칭 오염 (78건)
- **원인:** READ-001의 추출 로직이 `keyword in text` (부분 문자열 매칭). WO-CHG-007에서 반증된 바로 그 방식이 사람/시설 필드에 재현됨.
- **사람 필드 45건:** "어린이놀이시설"·"어린이놀이기구"·"어린이제품"의 '어린이'가 사람(대상)으로 오추출. 실제로는 시설명/제품명의 일부이지 규율 대상인 사람이 아님.
- **시설 필드 33건:** "놀이시설"의 '시설'이 독립 시설 어휘로 오추출.
- **결과:** "판단 없이 원문만 기록"이라 했으나, 추출 과정에서 부분매칭 오류가 파생 필드를 오염시킴. 원문을 읽은 것은 사실이나, Sheet의 파생 필드는 원문 사실을 정확히 반영하지 못함.

## PASS된 부분 (신뢰 가능)
- **원문 컬럼:** 523개 조문 전문 온전, 공란 0, 조문번호 일치(QA-4 0 불일치). 원문 텍스트 자체는 신뢰 가능한 입력.
- **적용대상 공란:** QA-1 3건 재검증 결과 전부 정상(적용범위 아닌 조문의 공란은 옳음).

## Independent Audit
```text
QA 대상    : Evidence Sheet 523행 전량
QA 방법    : 원문(원문 컬럼) ↔ 파생 필드 대조, 부분매칭 오추출 탐지
결함 규모   : 파생 필드 78건(사람 45·시설 33) 부분매칭 오염
무결 부분   : 원문 컬럼·조문번호·적용대상 공란 정합
판정 신뢰성 : QA-1 오탐(3건 정상)까지 재검증해 진짜 결함(78)만 남김
```

## Freeze
```text
QA Report        : 원문 PASS / 파생 필드 FAIL(78건 부분매칭)
결함 목록         : 사람 45(어린이=시설/제품명 일부) · 시설 33(놀이시설의 시설)
신뢰 가능 부분     : 원문 컬럼(523 전문)·조문번호
Evidence Sheet 판정: 재작성 필요 — 파생 필드를 부분매칭 아닌 단어경계/의미 기반으로 재추출
```

## 결론
- **"523개를 읽었다" ≠ "Evidence Sheet가 품질 기준 만족".** QA가 이 차이를 78건 오염으로 정량화.
- **원문 컬럼은 신뢰 가능** — 정독 자체는 유효(전문 확보·조문번호 정합).
- **파생 필드는 재작성 필요** — 부분 문자열 매칭 오염(CHG-007 반증 오류 재현). 이 Sheet로 CTX를 진행했다면 오염된 '사람=어린이' 필드를 근거로 오판했을 것.
- **다음:** Evidence Sheet의 파생 필드를 단어 경계/의미 기반으로 재추출(원문 컬럼은 재사용). 그 후에야 Evidence Sheet = 신뢰 가능한 입력 → CTX-001로 진행.

## Exit Criteria 점검
```text
[v] Evidence Sheet 품질 대조 (원문↔파생 필드)
[v] 결함 목록화 (78건, 사람 45·시설 33)
[v] QA-1 오탐 재검증 (3건 정상 확인)
[v] Independent Audit
[v] Freeze
[v] Evidence Sheet 신뢰 가능 여부 판정 (원문 PASS·파생 FAIL)
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑱" FP-03 Full Reading        ✓ WO-READ-001 (523/523 정독, 원문 확보)
⑱‴ Evidence Sheet QA          ✓ WO-QA-READ-001 (원문 PASS·파생 FAIL 78) ← 현재
⑲ Evidence Sheet 파생필드 재추출 ← 다음 (단어경계/의미 기반, 원문 재사용)
⑳ FP-03 CTX-001              ← 그 후 (신뢰 가능 Sheet 근거)
㉑ Replay → Review
```
