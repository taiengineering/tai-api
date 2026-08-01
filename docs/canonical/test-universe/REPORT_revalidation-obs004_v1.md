---
wo: WO-REVIEW-006
class: records
type: report
scope: canonical
project: test-universe
title: Observation Revalidation Obs-004
version: 1
status: active
owner: taiwang
---

# REPORT — WO-REVIEW-006 Observation Revalidation (Obs-004)

> Review only. 병합 반영 엔진 산물(after_obs002)에서 Obs-004 실재를 §12.9 전량 정독으로 재확인. 등장 사실·위치만 기록(§12.6). 원인·오적용 판단·Analysis·CHG 없음.
> Input: after_obs002(112, 병합 반영), Observation Inventory(6be576e4), REPORT_review-003-semantic(8869996a).

## 판정: Case A — Obs-004 유지 (새 엔진에서도 실재)

## 1. 존재 여부
- Obs-004 지목 8개 항목이 병합 반영 엔진에서도 예상 밖 sector에 그대로 등장. 오염 기준선 산물 아님(Obs-002 병합은 중복만 제거, sector 혼입 불변 — 예상된 결과).
- §12.6 준수: '타 도메인=오적용'이라는 판단은 하지 않음(Analysis 영역). 등장 사실과 위치만 기록.

## 2. 범위 (정독 확인, sector × profile)
```text
표면공급식 잠수작업 시 조치   : 제조 46 · 건축 29 · 건설 27           (특수 제외)
에너지절약형 친환경주택 설계조건 : 제조 46 · 건축 29 · 건설 27 · 특수 10  (112/112 전량)
방사선 안전관리 화재방호시설    : 건축 29 · 건설 27 · 특수 10
도로터널 화재안전기준        : 건축 29
다중이용업소             : 건축 29
초고층 복합건축물          : 건축 29
공동주택               : 건축 29
고층건축물              : 건축 29
```
- 정독 지표: 112/112 READ COMPLETE, Evidence 항목 454, 지목 항목 미등장 profile 0(모든 profile에 최소 1개 지목 항목 — 대개 에너지절약형주택 공통).

## 3. 영향
- 영향도: Critical(광범위 — 전 sector, 특히 에너지절약형주택은 112/112).
- 등장 사실 Confidence: High(전량 정독).

## 4. 증거 위치 (§12.9, profile별 @pos)
- obs004_evidence_log.txt (678줄): profile마다 지목 항목의 위치 인덱스(@pos) + READ COMPLETE. 예:
  - 제조/건축/건설 profile: [잠수작업] @pos, [에너지절약형주택] @pos.
  - 건축 profile: [도로터널]·[다중이용업소]·[초고층]·[공동주택]·[고층건축물] @pos.
  - 특수 profile: [에너지절약형주택]·[방사선] @pos.
- 원본: after_obs002/SNAP-*.json 의 *_required 배열.

## 5. 다른 Observation (등록만 — §12.6)
- 정독 중 Obs-005(선임류 report 위치)·Obs-006(법/시행규칙 분리) 재관측. 본 WO 판단 아님. 각 Revalidation WO에서.

## 결론
- Obs-004 = **유지(Observation 유효)**. 병합 반영 새 엔진에서 실재·범위 전량 정독 확인.
- 다음 단계(Analysis)는 별도 WO. 본 WO는 실재 확인까지 — 원인·오적용 판단 없음.
- 주의: '이 법령이 이 sector에 오적용인가'는 판단하지 않았다. 등장 사실만 확정. 정오(正誤)는 Analysis의 몫.

## 상태
```text
Obs-003 : RESOLVED (측정)
Obs-001 : RESOLVED (기준선)
Obs-002 : RESOLVED (Presentation Merge)
Obs-004 : VALID (새 엔진 재확인 완료) → Analysis 대상
Obs-005 : OPEN (재확인 필요)
Obs-006 : OPEN (재확인 필요)
```
