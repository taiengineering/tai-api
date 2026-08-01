---
wo: WO-REVIEW-007
class: records
type: report
scope: canonical
project: test-universe
title: Observation Revalidation Obs-005
version: 1
status: active
owner: taiwang
---

# REPORT — WO-REVIEW-007 Observation Revalidation (Obs-005)

> Review only. 병합 반영 엔진(after_obs002)에서 Obs-005 실재를 §12.9 전량 정독으로 재확인. 등장 사실·위치만(§12.6). 원인·category 정오 판단·Analysis·CHG 없음.
> Input: after_obs002(112, 병합 반영), Observation Inventory(6be576e4), REPORT_review-003-semantic(8869996a).

## 판정: Case A — Obs-005 유지 (새 엔진에서도 실재)

## 1. 존재 여부
- 선임/지정 성격 어휘(선임·지정·안전관리자·관리책임자 등)를 가진 의무가 category=신고(report)에 위치함을 정독 확인. 235건.
- §12.6 준수: 'category가 잘못됐다'는 판단 안 함. 일부는 텍스트에 '신고'가 포함('전기안전관리자의 선임 및 해임신고') — 정오는 Analysis 몫. 본 WO는 등장 사실+위치만.

## 2. 범위 (정독 확인)
```text
선임/지정 성격 의무가 category=신고에 위치:
  제조 46/46 · 건축 29/29 · 건설 24/27 · 특수 0/10
  총 235건, 미관측 13 profile(특수 10 + 건설 3)
```
- 대조(정상): 선임 성격이 category=선임에 위치한 것도 268건 존재(예: 기계설비유지관리자 선임). 즉 선임 성격이 선임·신고 양쪽에 분포.

## 3. 영향
- 영향도: High(광범위 3 sector). Confidence: 등장 사실 High.

## 4. 증거 위치 (§12.9, profile별 @pos)
- obs005_evidence_log.txt (472줄): profile마다 [신고] 위치의 선임성격 의무 @pos + READ COMPLETE. 예:
  - PF-0001: [신고] 승강기 안전관리법 | 승강기 안전관리자 @pos, 전기안전관리법 시행규칙 | 전기안전관리자의 선임 및 해임신고 @pos.
  - PF-0002: [신고] 산업안전보건법 시행령 | 안전관리자의 선임 등 @pos.
- 원본: after_obs002/SNAP-*.json 의 report_required 배열.

## 5. 다른 Observation (등록만 — §12.6)
- 정독 중 Obs-006(법/시행규칙 분리) 재관측(예: 기계설비법+기계설비법 시행규칙 선임). 본 WO 판단 아님.

## 결론
- Obs-005 = **유지(Observation 유효)**. 병합 반영 새 엔진에서 실재·범위 전량 정독 확인.
- 주의: 'category가 틀렸다'는 판단하지 않음. 선임 성격 어휘가 신고 category에 등장한 사실만 확정. category의 정오(예: 선임+해임신고는 실제 신고일 수 있음)는 Analysis 몫.

## 상태
```text
Obs-003 : RESOLVED
Obs-001 : RESOLVED
Obs-002 : RESOLVED
Obs-004 : ANALYZED (Metadata) → CHG 대상(별도 커버리지 프로젝트)
Obs-005 : VALID (새 엔진 재확인 완료) → Analysis 대상
Obs-006 : OPEN (재확인 필요)
```
