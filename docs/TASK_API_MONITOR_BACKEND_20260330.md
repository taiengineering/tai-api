# API 모니터 백엔드 작업 지시서
## 담당: Cursor (백엔드 창)

---

## 개요
부안 데이터가 `internal_api_registry` 테이블에 21개 등록되어 있음.
`report_api_registry` 테이블에 외부 API 5개 등록되어 있음.

프론트 `api-monitor-internal.html` 및 `api-monitor-external.html` 에서 아래 API 호출함.

---

## PART 1. 내부 API 레지스트리 (routers/internal_api_registry.py)

```python
from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/internal-api-registry", tags=["내부-API-레지스트리"])

@router.get("")
def list_endpoints():
    sb = get_supabase()
    rows = sb.table("internal_api_registry")\
        .select("*").eq("is_active", True)\
        .order("sort_order").execute().data or []
    return {"status": "success", "data": rows}

@router.post("")
def add_endpoint(body: dict):
    sb = get_supabase()
    allowed = ["group_name","api_name","method","endpoint","auth_required",
               "expect_status","description","is_active","sort_order"]
    data = {k: v for k, v in body.items() if k in allowed}
    res = sb.table("internal_api_registry").insert(data).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}

@router.delete("/{ep_id}")
def delete_endpoint(ep_id: str):
    sb = get_supabase()
    sb.table("internal_api_registry").update({"is_active": False})\
        .eq("id", ep_id).execute()
    return {"status": "success"}
```

## PART 2. 외부 API 레지스트리 (routers/report_api_registry.py)

```python
router = APIRouter(prefix="/report-api-registry", tags=["외부-API-레지스트리"])

@router.get("")
def list_external():
    sb = get_supabase()
    rows = sb.table("report_api_registry")\
        .select("*").order("created_at").execute().data or []
    return {"status": "success", "data": rows}

@router.post("")
def add_external(body: dict):
    sb = get_supabase()
    allowed = ["system_name","operator","system_type","official_api",
               "api_apply_url","login_required","approval_type",
               "can_use_for_auto_filing","recommendation","apply_status",
               "apply_date","approved_date","api_key_issued","notes"]
    data = {k: v for k, v in body.items() if k in allowed}
    res = sb.table("report_api_registry").insert(data).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}

@router.patch("/{reg_id}")
def update_external(reg_id: str, body: dict):
    sb = get_supabase()
    allowed = ["apply_status","apply_date","approved_date","api_key_issued","notes"]
    data = {k: v for k, v in body.items() if k in allowed}
    res = sb.table("report_api_registry").update(data).eq("id", reg_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}

@router.delete("/{reg_id}")
def delete_external(reg_id: str):
    sb = get_supabase()
    sb.table("report_api_registry").delete().eq("id", reg_id).execute()
    return {"status": "success"}
```

## PART 3. main.py 등록

```python
from routers import internal_api_registry, report_api_registry
app.include_router(internal_api_registry.router)
app.include_router(report_api_registry.router)
```

## 검증
```bash
curl -s https://api.taieng.co.kr/internal-api-registry | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['data']), 'endpoints')"
# 기대: 21 endpoints

curl -s https://api.taieng.co.kr/report-api-registry | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['data']), 'systems')"
# 기대: 5 systems
```

## git commit
```
feat: internal-api-registry + report-api-registry 라우터 추가
```
