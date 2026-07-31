---
wo: WO-E2E-BASELINE-001
class: records
type: report
scope: canonical
project: test-universe
title: Golden Candidates v1
version: 1
status: active
owner: taiwang
---

# REPORT — Golden Candidates v1

> WO-E2E-BASELINE-001. Golden 후보 자동 추천. **표시만. APPROVED/REJECTED 금지.**
> 후보 유형: Representative(섹터평균 근접) · Median · High · Low · Boundary.

## 섹터별 Golden 후보 (표시만)

### 제조 (MANUFACTURING)

| 유형 | Snapshot | Profile | obligation |
|---|---|---|---|
| Representative | SNAP-0041-001 | PF-0041 | 22 |
| Median | SNAP-0002-001 | PF-0002 | 23 |
| High | SNAP-0002-001 | PF-0002 | 23 |
| Low | SNAP-0001-001 | PF-0001 | 18 |

Boundary 후보: SNAP-0040-001(PF-0040: worker_count=49 (안전관리자 선임 50명 경계)), SNAP-0041-001(PF-0041: worker_count=50 (안전관리자 선임 50명 경계)), SNAP-0042-001(PF-0042: worker_count=51 (안전관리자 선임 50명 경계)), SNAP-0043-001(PF-0043: worker_count=99 (100명 경계)), SNAP-0044-001(PF-0044: worker_count=100 (100명 경계)), SNAP-0045-001(PF-0045: worker_count=101 (100명 경계))

### 건축물 (BUILDING)

| 유형 | Snapshot | Profile | obligation |
|---|---|---|---|
| Representative | SNAP-0023-001 | PF-0023 | 102 |
| Median | SNAP-0019-001 | PF-0019 | 107 |
| High | SNAP-0019-001 | PF-0019 | 107 |
| Low | SNAP-0021-001 | PF-0021 | 28 |

Boundary 후보: SNAP-0049-001(PF-0049: total_floor_area=4999.0 (연면적 5000 경계)), SNAP-0050-001(PF-0050: total_floor_area=5000.0 (연면적 5000 경계)), SNAP-0051-001(PF-0051: total_floor_area=5001.0 (연면적 5000 경계)), SNAP-0062-001(PF-0062: total_floor_area=2999.0 (연면적 3000 경계)), SNAP-0063-001(PF-0063: total_floor_area=3000.0 (연면적 3000 경계)), SNAP-0064-001(PF-0064: total_floor_area=3001.0 (연면적 3000 경계))

### 건설 (CONSTRUCTION)

| 유형 | Snapshot | Profile | obligation |
|---|---|---|---|
| Representative | SNAP-0028-001 | PF-0028 | 23 |
| Median | SNAP-0032-001 | PF-0032 | 24 |
| High | SNAP-0032-001 | PF-0032 | 24 |
| Low | SNAP-0034-001 | PF-0034 | 20 |

Boundary 후보: SNAP-0052-001(PF-0052: contract_amount_eok=49.0 (공사금액 50억 경계)), SNAP-0053-001(PF-0053: contract_amount_eok=50.0 (공사금액 50억 경계)), SNAP-0054-001(PF-0054: contract_amount_eok=51.0 (공사금액 50억 경계)), SNAP-0055-001(PF-0055: contract_amount_eok=119.0 (120억 경계)), SNAP-0056-001(PF-0056: contract_amount_eok=120.0 (120억 경계)), SNAP-0057-001(PF-0057: contract_amount_eok=121.0 (120억 경계))

### 특수시설 (SPECIAL_FACILITY)

| 유형 | Snapshot | Profile | obligation |
|---|---|---|---|
| Representative | SNAP-0037-001 | PF-0037 | 7 |
| Median | SNAP-0037-001 | PF-0037 | 7 |
| High | SNAP-0037-001 | PF-0037 | 7 |
| Low | SNAP-0037-001 | PF-0037 | 7 |

## 원칙

> 후보는 추천 표시일 뿐이다. 어느 것도 Golden이 아니다.
> Golden 승인은 다음 WO(WO-E2E-GOLDEN-002)에서 운영자가 이 후보 자료를 근거로 수행한다.
