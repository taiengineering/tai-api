---
wo: WO-E2E-FREEZE-001
class: normative
type: standard
scope: canonical
project: test-universe
title: Before Baseline Freeze v1
version: 1
status: active
owner: taiwang
---

# STANDARD — Before Baseline Freeze v1 (BEFORE_BASELINE_V1)

> WO-E2E-FREEZE-001. Baseline Snapshot Set을 회귀검증의 **영구 기준(Before)**으로 확정·Freeze.
> 비교·엔진수정 없음. 이 Freeze 이후 Snapshot·Baseline·Profile Universe는 **수정 금지(LOCKED)**.
> SET CHECKSUM (SHA256): `d2d2e39f1a328d4ccbd9f2e5dc7e772c788098ad9a215e3b72a48464915c7fc3`

## 1. Freeze Manifest

| 항목 | 값 |
|---|---|
| Freeze ID | BEFORE_BASELINE_V1 |
| Engine Version | v3.0-compiler-core-anonymous (전건 동일) |
| Baseline Run Date | 2026-07-30 (initial 110) + 2026-07-31 (refill PF-0107·PF-0111) |
| Freeze Date | 2026-07-31 |
| Snapshot Count | 112 |
| Success | 112 |
| Failure | 0 |
| Set Checksum (SHA256) | `d2d2e39f1a328d4ccbd9f2e5dc7e772c788098ad9a215e3b72a48464915c7fc3` |
| Engine Uniform | True |

## 2. STEP 1 — 실패 2건 재실행 결과

| Profile | Before | After 재실행 | 결과 |
|---|---|---|---|
| PF-0107 | HTTP 502 | HTTP 200, obligation 7 | 성공본 교체 |
| PF-0111 | HTTP 502 | HTTP 200, obligation 7 | 성공본 교체 |

> 누락분만 채움(기존 110건 무변경). 결과: **112/112 SUCCESS**.

## 3. Freeze 시점 섹터 통계 (사실)

| Sector | Count | Avg | Median | Min | Max | StdDev |
|---|---|---|---|---|---|---|
| 제조(MANUFACTURING) | 46 | 21.7 | 23.0 | 18 | 23 | 2.1 |
| 건축물(BUILDING) | 29 | 98.1 | 107 | 28 | 107 | 23.9 |
| 건설(CONSTRUCTION) | 27 | 23.3 | 24 | 20 | 24 | 1.2 |
| 특수시설(SPECIAL_FACILITY) | 10 | 7 | 7.0 | 7 | 7 | 0.0 |

## 4. Baseline Lock (STEP 4)

다음 3개는 이 Freeze 이후 **변경 금지**:

- BEFORE_BASELINE_V1 (112 Snapshot, 각 SHA256 고정)
- baseline_snapshot_set_v1
- profile-universe-v1

> Lock 규칙: Engine 수정 후 재실행은 **AFTER로 별도 저장**한다. Before는 영구 불변.
> 무결성 검증: 각 Snapshot SHA256 + 집합 통합 SET CHECKSUM(§1)으로 위변조 탐지.

## 5. 산출물

| 파일 | 소재 |
|---|---|
| before_baseline_v1.json | project: test-universe/ (112 record + per-snapshot sha + set checksum) |
| freeze_manifest_v1.json | project: test-universe/ (freeze metadata + lock + per-snapshot checksum) |
| REGISTRY_before-baseline_v1.md | tai-api canonical (본 문서) |
| BEFORE_BASELINE_V1 snapshots (112) | 사용자 PC ~/45cm-test/snapshots_all/ + project |

## 6. 다음

```
Before Freeze (완료) → Engine 수정 → 112 재실행(AFTER) → Semantic Before/After 비교 → 운영자 판정
```

> Before가 고정됐으므로 이후 모든 엔진 개선은 동일 기준(SET CHECKSUM d2d2e39f…)에서 객관 비교 가능.
