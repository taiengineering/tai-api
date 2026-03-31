# TAI Cursor 작업지시서 — 기준일 입력 + 반복일정 생성

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: `routers/inspection_sets.py` (수정)

---

## 배경 및 목적

`inspection_sets`에 점검세트가 등록되면 `status_code = 'PENDING_ANCHOR'` 상태가 됩니다.  
이 상태에서는 **기준일(anchor_date)을 입력해야** 비로소 `work_schedules`에 반복 점검일정이 생성됩니다.

현재 이 엔드포인트가 없어서 모든 점검세트가 PENDING_ANCHOR에서 멈춰 있습니다.

---

## DB 구조 (이미 존재 — DDL 불필요)

### inspection_sets (관련 컬럼)
```
id                  UUID PK
factory_id          UUID
company_id          UUID
inspection_set_name TEXT
inspection_category TEXT
cycle_value         INTEGER   -- 주기 숫자 (예: 1)
cycle_unit          TEXT      -- year/month/quarter/half_year
cycle_base_type     TEXT      -- LAST_INSPECTION / FIXED_DATE
schedule_anchor_date DATE     -- ← 기준일 저장
anchor_confirmed    BOOLEAN   -- ← TRUE로 업데이트
status_code         TEXT      -- PENDING_ANCHOR → ACTIVE
schedule_end_date   DATE      -- 일정 생성 종료일
source              TEXT      -- LEGAL_ENGINE / MANUAL
```

### work_schedules (반복일정 테이블)
```
id                UUID PK (gen_random_uuid())
factory_id        UUID
company_id        UUID
inspection_set_id UUID FK → inspection_sets
planned_date      DATE      -- 점검 예정일 (핵심)
start_date        DATE      -- = planned_date
end_date          DATE      -- = planned_date
repeat_type       TEXT      -- 'monthly' / 'yearly' / 'quarterly'
repeat_interval   INTEGER   -- cycle_value 그대로
status_code       TEXT      -- 'SCHEDULED'
source_type       TEXT      -- 'LEGAL' / 'MANUAL'
obligation_type   TEXT      -- inspection_sets.inspection_category
summary           TEXT      -- 점검세트명
schedule_group_id UUID      -- (NULL 허용)
active_yn         BOOLEAN   -- TRUE
```

---

## 구현할 엔드포인트

### PATCH /inspection-sets/{inspection_set_id}/anchor

**역할:** 기준일을 받아서 inspection_sets 업데이트 + work_schedules 1년치 생성

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import uuid

class AnchorBody(BaseModel):
    anchor_date: str           # 기준일 'YYYY-MM-DD'
    end_date: Optional[str] = None  # 일정 종료일 (없으면 1년 후)

@router.patch("/{inspection_set_id}/anchor")
def set_anchor(inspection_set_id: str, body: AnchorBody):
    supabase = get_supabase()

    # 1. inspection_set 조회
    res = supabase.table("inspection_sets").select("*") \
        .eq("id", inspection_set_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검세트를 찾을 수 없습니다.")
    iset = res.data

    anchor = date.fromisoformat(body.anchor_date)
    end    = date.fromisoformat(body.end_date) if body.end_date \
             else anchor + relativedelta(years=1)

    cycle_value = iset.get("cycle_value") or 1
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()

    # 2. inspection_sets 업데이트
    supabase.table("inspection_sets").update({
        "schedule_anchor_date": anchor.isoformat(),
        "schedule_end_date":    end.isoformat(),
        "anchor_confirmed":     True,
        "status_code":          "ACTIVE",
        "updated_at":           datetime.now().isoformat(),
    }).eq("id", inspection_set_id).execute()

    # 3. 기존 SCHEDULED 일정 삭제 (재설정 허용)
    supabase.table("work_schedules") \
        .delete() \
        .eq("inspection_set_id", inspection_set_id) \
        .eq("status_code", "SCHEDULED") \
        .execute()

    # 4. 반복 일정 생성
    rows   = []
    cursor = anchor

    # cycle_unit → relativedelta 매핑
    DELTA_MAP = {
        "day":        relativedelta(days=cycle_value),
        "week":       relativedelta(weeks=cycle_value),
        "month":      relativedelta(months=cycle_value),
        "quarter":    relativedelta(months=3 * cycle_value),
        "half_year":  relativedelta(months=6 * cycle_value),
        "year":       relativedelta(years=cycle_value),
    }
    delta = DELTA_MAP.get(cycle_unit, relativedelta(years=cycle_value))

    # repeat_type 결정
    REPEAT_MAP = {
        "day":       "daily",
        "week":      "weekly",
        "month":     "monthly",
        "quarter":   "quarterly",
        "half_year": "half_yearly",
        "year":      "yearly",
    }
    repeat_type = REPEAT_MAP.get(cycle_unit, "yearly")

    source_type = "LEGAL" if iset.get("source") == "LEGAL_ENGINE" else "MANUAL"

    while cursor <= end:
        rows.append({
            "factory_id":        iset["factory_id"],
            "company_id":        iset.get("company_id"),
            "inspection_set_id": inspection_set_id,
            "planned_date":      cursor.isoformat(),
            "start_date":        cursor.isoformat(),
            "end_date":          cursor.isoformat(),
            "repeat_type":       repeat_type,
            "repeat_interval":   cycle_value,
            "status_code":       "SCHEDULED",
            "source_type":       source_type,
            "obligation_type":   iset.get("inspection_category") or "GENERAL",
            "summary":           iset.get("inspection_set_name") or "",
            "active_yn":         True,
        })
        cursor += delta

    # 20건씩 배치 INSERT
    created = 0
    for i in range(0, len(rows), 20):
        r = supabase.table("work_schedules").insert(rows[i:i+20]).execute()
        created += len(r.data or [])

    return {
        "status":  "success",
        "message": f"{created}개 반복일정이 생성됐습니다.",
        "data": {
            "inspection_set_id": inspection_set_id,
            "anchor_date":       anchor.isoformat(),
            "end_date":          end.isoformat(),
            "cycle":             f"{cycle_value} {cycle_unit}",
            "created":           created,
        }
    }
```

---

## 추가 구현: 일괄 anchor 설정

### POST /inspection-sets/anchor/bulk

같은 factory의 PENDING_ANCHOR 전체를 한 번에 처리하는 엔드포인트.  
각 세트마다 anchor_date를 오늘로 적용.

```python
class BulkAnchorBody(BaseModel):
    factory_id:  str
    anchor_date: str           # 기준일 (전체 동일 적용)
    end_date:    Optional[str] = None

@router.post("/anchor/bulk")
def set_anchor_bulk(body: BulkAnchorBody):
    supabase = get_supabase()

    # PENDING_ANCHOR 상태 세트 전체 조회
    res = supabase.table("inspection_sets").select("id") \
        .eq("factory_id", body.factory_id) \
        .eq("status_code", "PENDING_ANCHOR") \
        .eq("is_active", True) \
        .execute()
    sets = res.data or []

    results = []
    for s in sets:
        try:
            r = set_anchor(s["id"], AnchorBody(
                anchor_date=body.anchor_date,
                end_date=body.end_date
            ))
            results.append({"id": s["id"], "created": r["data"]["created"]})
        except Exception as e:
            results.append({"id": s["id"], "error": str(e)})

    total_created = sum(r.get("created", 0) for r in results)
    return {
        "status":  "success",
        "message": f"{len(sets)}개 세트 처리, 총 {total_created}개 일정 생성",
        "data":    {"results": results, "total_created": total_created}
    }
```

---

## 주의사항

- `python-dateutil` 패키지 사용 (`relativedelta`). requirements.txt에 이미 있으면 생략.  
  없으면 `requirements.txt`에 `python-dateutil` 추가.
- `datetime` import 추가: `from datetime import date, datetime, timedelta`
- `dateutil.relativedelta` import 추가: `from dateutil.relativedelta import relativedelta`
- 재설정 시 기존 SCHEDULED 일정 먼저 삭제 후 새로 생성 (덮어쓰기 방식)
- COMPLETED 상태 일정은 절대 삭제하지 않음

---

## 완료 체크리스트

```
□ PATCH /inspection-sets/{id}/anchor 구현
□ POST  /inspection-sets/anchor/bulk 구현
□ python-dateutil import 확인
□ Railway 배포 후 버전 확인
```

## 검증 (배포 후 이 창에서 테스트)

```bash
# 단건 기준일 설정
curl -X PATCH https://api.taieng.co.kr/inspection-sets/{id}/anchor \
  -d '{"anchor_date": "2026-04-01"}'
# → created: N 개 반복일정 생성 확인

# 일괄 설정
curl -X POST https://api.taieng.co.kr/inspection-sets/anchor/bulk \
  -d '{"factory_id": "9ec1ac44-...", "anchor_date": "2026-04-01"}'
```
