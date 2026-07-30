---
wo: WO-E2E-GOLDEN-001
class: records
type: registry
scope: canonical
project: test-universe
title: Golden Approval System and Registry v1
version: 1
status: active
owner: taiwang
---

# REGISTRY — Golden Approval System & Registry v1

> WO-E2E-GOLDEN-001. Golden 승인 체계 구축 + 최초 Golden 등록.
> 원칙: **Snapshot ≠ Golden. Golden = 사람이 승인한 Snapshot.** APPROVED만 Golden Registry에 등록.
> Snapshot은 Fact(불변). 이번 WO에서 Rule·엔진·Snapshot·의무개수 무수정.

## 1. 승인 체계 (Approval Flow)

```
Profile → Runner → Snapshot → ①실행검증 → ②구조검증 → ③의미검증(자료) → 운영자 판정 → APPROVED → Golden
```

- ①②는 기계적 PASS/FAIL. ③은 대표 의무 도메인 커버리지 **자료 제시**(AI 판정 아님).
- 판정은 APPROVED / REJECTED 두 가지. AI 단독 의미판정 금지 — 운영자 승인.
- APPROVED만 Golden Registry 등록. REJECTED는 사유·재판정 대기로 기록.

## 2. 검증 결과 (4 Snapshot)

| Snapshot | Profile | Sector | ①실행 | ②구조 | ③의미(기대 대표도메인 커버) | 판정 | Golden ID |
|---|---|---|---|---|---|---|---|
| SNAP-0001-001 | PF-0001 | MANUFACTURING | PASS | PASS | 5/5 (완전) | **APPROVED** | GOLD-0001 |
| SNAP-0019-001 | PF-0019 | BUILDING | PASS | PASS | 3/5 (미커버:전기·승강기) | **REJECTED** | — |
| SNAP-0028-001 | PF-0028 | CONSTRUCTION | PASS | PASS | 3/3 (완전) | **APPROVED** | GOLD-0028 |
| SNAP-0037-001 | PF-0037 | SPECIAL_FACILITY | PASS | PASS | 1/2 (미커버:산업안전) | **REJECTED** | — |

## 3. Golden Registry (APPROVED만)

| Golden ID | Snapshot | Profile | Sector | Engine | 승인 근거 |
|---|---|---|---|---|---|
| GOLD-0001 | SNAP-0001-001 | PF-0001 | MANUFACTURING | v3.0-compiler-core-anonymous | 실행·구조 PASS, 대표도메인 5/5 완전 커버(산업안전·전기·기계설비·화학물질·작업환경). |
| GOLD-0028 | SNAP-0028-001 | PF-0028 | CONSTRUCTION | v3.0-compiler-core-anonymous | 실행·구조 PASS, 대표도메인 3/3 완전 커버(산업안전·건설안전·중대재해). |

## 4. REJECTED (재판정 대기 — Golden 미등록)

| Snapshot | Profile | Sector | 사유 (관찰, 판정 근거) |
|---|---|---|---|
| SNAP-0019-001 | PF-0019 | BUILDING | 실행·구조 PASS이나 total 107에서 전기·승강기 대표의무 미커버 관찰. 갭 원인 별도 조사 후 재판정. |
| SNAP-0037-001 | PF-0037 | SPECIAL_FACILITY | 실행·구조 PASS이나 total 7에서 산업안전 대표의무 미커버 관찰. 갭 원인 별도 조사 후 재판정. |

> REJECTED는 Snapshot(Fact)을 부정하는 것이 아니라 Golden(Approval) 미승인이다. Snapshot은 그대로 보존.
> 미커버 갭이 '정당한 제외'인지 '엔진 커버리지 갭'인지는 별도 WO에서 조사 후 재판정한다.

## 5. 원칙 (재확정)

```
Snapshot 이 쌓이는 것이 아니라 Approved Golden 이 쌓인다.
Regression · Coverage · Benchmark 는 모두 Approved Golden 을 기준으로 한다.
```

## 6. 다음 WO

> Golden Registry(GOLD-0001·GOLD-0028)가 최초 기준선. 다음=WO-E2E-DIFF-001(Diff 분석).
> REJECTED 2건(SNAP-0019·SNAP-0037)의 갭 원인 조사는 별도 트랙.
