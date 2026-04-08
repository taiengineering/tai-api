# QR / RFID 설비 체크인 — 백엔드 작업지시서

생성일: 2026-04-08  
대상 파일: `routers/equipment_assets.py` (기존 파일에 엔드포인트 추가)  
신규 파일: `routers/equipment_checkins.py`

---

## 개요

현장 작업자가 설비에 부착된 **QR 코드** 또는 **RFID 태그**를 스캔하여  
직접 점검 체크인을 수행하는 기능의 백엔드 API.

### 핵심 설계 원칙
- QR 스캔 조회는 **인증 불필요** (현장에서 로그인 없이 접근)
- 체크인 제출은 **인증 불필요** (이름 직접 입력 또는 로그인 선택)
- 모든 체크인 기록은 `equipment_checkins` 테이블에 저장
- 이상(NG) 발생 시 **FCM 푸시 + DB 알림** 자동 생성

---

## DB 현황 (2026-04-08 기획창에서 완료)

`equipment_assets` 테이블에 이미 추가된 컬럼:
```
factory_process_id  uuid        -- 공정 연결
rfid_tag            text UNIQUE -- RFID 물리 태그 ID  
rfid_tag_type       text        -- NFC | HF_13MHZ | UHF_900MHZ
qr_code_generated_at timestamptz
qr_print_count      integer DEFAULT 0
qr_code             text        -- (기존) QR URL 저장
```

---

## 작업 1: equipment_checkins 테이블 생성

`main.py` 또는 별도 migration 스크립트에서 실행:

```sql
CREATE TABLE IF NOT EXISTS equipment_checkins (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  equipment_asset_id  uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE CASCADE,
  schedule_id         uuid REFERENCES work_schedules(id) ON DELETE SET NULL,
  factory_id          uuid REFERENCES factories(id) ON DELETE SET NULL,
  company_id          uuid REFERENCES companies(id) ON DELETE SET NULL,

  -- 작업자 (로그인 or 익명)
  worker_id           uuid,           -- 로그인 사용자 ID (선택)
  worker_name         text,           -- 미로그인 시 직접 입력

  -- 점검 결과
  checkin_items       jsonb,          -- 항목별 결과 배열
  overall_result      text NOT NULL,  -- OK | NG | HOLD
  note                text,           -- 특이사항

  -- 증빙
  signature_data      text,           -- base64 서명 이미지
  photo_urls          text[],         -- Supabase Storage URL 배열

  -- 인식 방법
  scan_method         text DEFAULT 'QR', -- QR | RFID | MANUAL

  -- 위치
  latitude            numeric,
  longitude           numeric,

  -- 시간
  checkin_at          timestamptz NOT NULL DEFAULT NOW(),
  created_at          timestamptz DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkins_equipment_id
  ON equipment_checkins(equipment_asset_id);
CREATE INDEX IF NOT EXISTS idx_checkins_factory_id
  ON equipment_checkins(factory_id);
CREATE INDEX IF NOT EXISTS idx_checkins_checkin_at
  ON equipment_checkins(checkin_at DESC);
```

---

## 작업 2: equipment_assets.py 에 엔드포인트 추가

기존 `routers/equipment_assets.py` 파일 하단에 아래 3개 엔드포인트 추가.

### 2-1. QR 코드 생성 (인증 필요)

```python
@router.post("/{asset_id}/generate-qr")
def generate_qr(asset_id: str):
    """
    설비의 QR 코드 URL을 생성하고 DB에 저장.
    QR 내용: safe.taieng.co.kr 체크인 페이지 URL
    인증: 필요 (사업장 소속 확인)
    """
    supabase = get_supabase()

    asset = supabase.table("equipment_assets").select(
        "id, asset_name, asset_code, factory_id"
    ).eq("id", asset_id).single().execute()
    if not asset.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")

    qr_url = f"https://safe.taieng.co.kr/html/vertical-menu-template-no-customizer/qr-check.html?id={asset_id}"

    from datetime import datetime
    res = supabase.table("equipment_assets").update({
        "qr_code": qr_url,
        "qr_code_generated_at": datetime.utcnow().isoformat(),
    }).eq("id", asset_id).execute()

    return {
        "status": "success",
        "data": {
            "qr_url": qr_url,
            "asset_id": asset_id,
            "asset_name": asset.data["asset_name"],
            "asset_code": asset.data.get("asset_code"),
            "generated_at": datetime.utcnow().isoformat(),
        }
    }
```

---

### 2-2. QR/RFID 스캔 조회 (인증 불필요 — 공개 API)

```python
@router.get("/scan")
def scan_equipment(
    id:   Optional[str] = Query(None, description="equipment_asset_id"),
    rfid: Optional[str] = Query(None, description="RFID 태그 ID"),
):
    """
    QR 스캔 또는 RFID 스캔 시 설비 정보 + 오늘 점검 일정 반환.
    인증: 불필요 (공개 접근)
    """
    supabase = get_supabase()

    if not id and not rfid:
        raise HTTPException(status_code=422, detail="id 또는 rfid 파라미터가 필요합니다")

    # 설비 조회
    q = supabase.table("equipment_assets").select(
        "id, asset_name, asset_code, equipment_type_code, equipment_category, "
        "main_image_url, description, factory_id, factory_process_id, "
        "rfid_tag, rfid_tag_type, location_detail"
    )
    if id:
        q = q.eq("id", id)
    else:
        q = q.eq("rfid_tag", rfid)

    asset_res = q.single().execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="등록된 설비를 찾을 수 없습니다")

    asset = asset_res.data
    factory_id = asset.get("factory_id")

    # 사업장 + 회사 정보 조회
    factory_info = {}
    company_info = {}
    if factory_id:
        fac = supabase.table("factories").select(
            "id, name, company_id"
        ).eq("id", factory_id).single().execute()
        if fac.data:
            factory_info = {"id": fac.data["id"], "name": fac.data["name"]}
            company_id = fac.data.get("company_id")
            if company_id:
                comp = supabase.table("companies").select(
                    "id, name"
                ).eq("id", company_id).single().execute()
                if comp.data:
                    company_info = {"id": comp.data["id"], "name": comp.data["name"]}

    # 공정 정보 조회
    process_info = {}
    factory_process_id = asset.get("factory_process_id")
    if factory_process_id:
        proc = supabase.table("factory_process").select(
            "id, process_path, process_name_manual, process_lv1, process_lv2, process_lv3"
        ).eq("id", factory_process_id).single().execute()
        if proc.data:
            process_info = proc.data

    # 오늘 예정된 점검 일정 조회
    from datetime import date
    today = date.today().isoformat()
    schedules_res = supabase.table("work_schedules").select(
        "id, description, planned_date, status_code, law_name, law_article"
    ).eq("factory_id", factory_id).eq("planned_date", today).neq(
        "status_code", "DONE"
    ).limit(10).execute()

    # scan_method 판별
    scan_method = "RFID" if rfid else "QR"

    return {
        "status": "success",
        "data": {
            "equipment": asset,
            "factory":   factory_info,
            "company":   company_info,
            "process":   process_info,
            "pending_schedules": schedules_res.data or [],
            "scan_method": scan_method,
        }
    }
```

---

### 2-3. QR 출력 횟수 카운트 (인증 필요)

```python
@router.post("/{asset_id}/qr-printed")
def increment_qr_print(asset_id: str):
    """
    QR 프린트 버튼 클릭 시 호출 → qr_print_count += 1
    """
    supabase = get_supabase()
    asset = supabase.table("equipment_assets").select(
        "qr_print_count"
    ).eq("id", asset_id).single().execute()
    if not asset.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")

    current = asset.data.get("qr_print_count") or 0
    supabase.table("equipment_assets").update({
        "qr_print_count": current + 1
    }).eq("id", asset_id).execute()

    return {"status": "success", "qr_print_count": current + 1}
```

---

## 작업 3: equipment_checkins.py 신규 생성

`routers/equipment_checkins.py` 파일 전체 내용:

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/equipment-checkins", tags=["equipment_checkins"])

VERSION = "1.0.0"
"""
equipment_checkins.py v1.0.0
v1.0.0: QR/RFID 설비 체크인 API
  - POST /equipment-checkins         체크인 제출 (인증 불필요)
  - GET  /equipment-checkins         체크인 이력 조회 (인증 필요)
  - GET  /equipment-checkins/{id}    단건 조회
"""


# ── Pydantic 모델 ─────────────────────────────────

class CheckinItem(BaseModel):
    item_key:   str              # 예: 'tire', 'brake', 'horn'
    item_label: str              # 예: '타이어 상태', '브레이크'
    result:     str              # OK | NG | HOLD
    note:       Optional[str] = None


class EquipmentCheckinCreate(BaseModel):
    equipment_asset_id: str
    schedule_id:        Optional[str] = None
    checkin_items:      Optional[List[CheckinItem]] = None
    overall_result:     str                           # OK | NG | HOLD
    note:               Optional[str] = None
    worker_id:          Optional[str] = None          # 로그인 사용자
    worker_name:        Optional[str] = None          # 미로그인 직접 입력
    signature_data:     Optional[str] = None          # base64
    photo_urls:         Optional[List[str]] = None
    scan_method:        Optional[str] = "QR"          # QR | RFID | MANUAL
    latitude:           Optional[float] = None
    longitude:          Optional[float] = None


# ── 체크인 제출 (인증 불필요) ─────────────────────────────────
@router.post("")
async def submit_checkin(body: EquipmentCheckinCreate):
    """
    QR/RFID 스캔 후 점검 결과 제출.
    인증: 불필요 (현장 작업자 익명 접근 허용)
    이상(NG) 시 관리자에게 FCM 푸시 + 알림 DB 생성.
    """
    supabase = get_supabase()

    if body.overall_result not in ("OK", "NG", "HOLD"):
        raise HTTPException(status_code=422, detail="overall_result는 OK|NG|HOLD 중 하나여야 합니다")
    if not body.worker_id and not body.worker_name:
        raise HTTPException(status_code=422, detail="worker_id 또는 worker_name 중 하나는 필수입니다")

    # 설비 + 사업장 정보 조회
    asset = supabase.table("equipment_assets").select(
        "id, asset_name, factory_id"
    ).eq("id", body.equipment_asset_id).single().execute()
    if not asset.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다")

    factory_id = asset.data.get("factory_id")
    company_id = None
    if factory_id:
        fac = supabase.table("factories").select("company_id").eq(
            "id", factory_id
        ).single().execute()
        company_id = (fac.data or {}).get("company_id")

    # 체크인 저장
    insert_data = {
        "equipment_asset_id": body.equipment_asset_id,
        "schedule_id":        body.schedule_id,
        "factory_id":         factory_id,
        "company_id":         company_id,
        "worker_id":          body.worker_id,
        "worker_name":        body.worker_name,
        "checkin_items":      [i.dict() for i in body.checkin_items] if body.checkin_items else None,
        "overall_result":     body.overall_result,
        "note":               body.note,
        "signature_data":     body.signature_data,
        "photo_urls":         body.photo_urls,
        "scan_method":        body.scan_method or "QR",
        "latitude":           body.latitude,
        "longitude":          body.longitude,
        "checkin_at":         datetime.utcnow().isoformat(),
    }
    insert_data = {k: v for k, v in insert_data.items() if v is not None}

    res = supabase.table("equipment_checkins").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="체크인 저장 실패")

    new_checkin = res.data[0]

    # 일정 상태 업데이트 (schedule_id 있을 때)
    if body.schedule_id and body.overall_result == "OK":
        try:
            supabase.table("work_schedules").update({
                "status_code": "DONE"
            }).eq("id", body.schedule_id).execute()
        except Exception as e:
            print(f"[CHECKIN] 일정 상태 업데이트 실패: {e}")

    # 이상(NG) 시 관리자 알림
    if body.overall_result in ("NG", "HOLD") and factory_id:
        try:
            await _notify_abnormal_checkin(
                factory_id=factory_id,
                company_id=company_id,
                asset_name=asset.data["asset_name"],
                worker_name=body.worker_name or body.worker_id or "작업자",
                overall_result=body.overall_result,
                note=body.note,
                checkin_id=new_checkin["id"],
            )
        except Exception as e:
            print(f"[CHECKIN] 이상 알림 실패: {e}")

    return {
        "status":     "success",
        "message":    "체크인이 완료됐습니다",
        "data": {
            "checkin_id":     new_checkin["id"],
            "overall_result": body.overall_result,
            "checkin_at":     new_checkin["checkin_at"],
        }
    }


async def _notify_abnormal_checkin(
    factory_id: str,
    company_id: Optional[str],
    asset_name: str,
    worker_name: str,
    overall_result: str,
    note: Optional[str],
    checkin_id: str,
):
    """이상/보류 체크인 시 관리자에게 알림 생성 + FCM 발송"""
    supabase = get_supabase()

    label = "이상" if overall_result == "NG" else "보류"
    title = f"[TAI Safe] 설비 점검 {label} 발생"
    body_text = f"{asset_name} — {worker_name}님이 {label}로 보고했습니다."
    if note:
        body_text += f" ({note})"

    # DB 알림 생성
    notif = {
        "factory_id": factory_id,
        "title":      title,
        "body":       body_text,
        "type":       "EQUIPMENT_ABNORMAL",
        "reference_id": checkin_id,
        "is_read":    False,
    }
    if company_id:
        notif["company_id"] = company_id
    supabase.table("notifications").insert(notif).execute()

    # FCM 발송 — 해당 사업장 관리자 토큰 조회 후 발송
    try:
        mgr = supabase.table("users").select(
            "fcm_token"
        ).eq("factory_id", factory_id).eq("role_code", "003").not_.is_(
            "fcm_token", "null"
        ).execute()
        from routers.fcm import send_fcm_message
        for u in (mgr.data or []):
            token = u.get("fcm_token")
            if token:
                await send_fcm_message(token=token, title=title, body=body_text, data={
                    "type": "EQUIPMENT_ABNORMAL",
                    "checkin_id": checkin_id,
                })
    except Exception as e:
        print(f"[CHECKIN] FCM 발송 실패: {e}")


# ── 체크인 이력 조회 (인증 필요) ─────────────────────────────────
@router.get("")
def get_checkins(
    factory_id:         Optional[str] = Query(None),
    equipment_asset_id: Optional[str] = Query(None),
    overall_result:     Optional[str] = Query(None),  # OK | NG | HOLD
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("equipment_checkins").select(
        "id, equipment_asset_id, factory_id, worker_id, worker_name, "
        "overall_result, note, scan_method, checkin_at, "
        "checkin_items, photo_urls",
        count="exact"
    )
    if factory_id:
        q = q.eq("factory_id", factory_id)
    if equipment_asset_id:
        q = q.eq("equipment_asset_id", equipment_asset_id)
    if overall_result:
        q = q.eq("overall_result", overall_result)

    offset = (page - 1) * size
    res = q.order("checkin_at", desc=True).range(offset, offset + size - 1).execute()
    return {
        "status": "success",
        "data": {
            "items": res.data,
            "total": res.count or 0,
            "page":  page,
            "size":  size,
        }
    }


# ── 단건 조회 ─────────────────────────────────
@router.get("/{checkin_id}")
def get_checkin(checkin_id: str):
    supabase = get_supabase()
    res = supabase.table("equipment_checkins").select("*").eq(
        "id", checkin_id
    ).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="체크인 기록을 찾을 수 없습니다")
    return {"status": "success", "data": res.data}
```

---

## 작업 4: main.py 라우터 등록

`main.py`에서 기존 라우터 import 패턴과 동일하게 추가:

```python
from routers import equipment_checkins
app.include_router(equipment_checkins.router)
```

---

## 전체 API 목록 요약

| Method | Endpoint | 인증 | 설명 |
|--------|----------|------|------|
| `POST` | `/equipment-assets/{id}/generate-qr` | 필요 | QR URL 생성 저장 |
| `GET`  | `/equipment-assets/scan?id=` | **불필요** | QR 스캔 조회 |
| `GET`  | `/equipment-assets/scan?rfid=` | **불필요** | RFID 스캔 조회 |
| `POST` | `/equipment-assets/{id}/qr-printed` | 필요 | 출력 횟수 카운트 |
| `POST` | `/equipment-checkins` | **불필요** | 체크인 제출 |
| `GET`  | `/equipment-checkins` | 필요 | 이력 조회 |
| `GET`  | `/equipment-checkins/{id}` | 필요 | 단건 조회 |

---

## 주의사항

1. **라우팅 순서**: `equipment_assets.py`에서
   - `GET /scan` 은 `GET /{asset_id}` 보다 **먼저** 선언해야 함
   - FastAPI 라우팅 원칙: 구체 경로 → 파라미터 경로 순서

2. **인증 불필요 엔드포인트**: `main.py`에서 해당 라우터를 등록할 때
   - 기존 `get_current_user` 의존성을 해당 엔드포인트에 **적용하지 않음**
   - 또는 각 엔드포인트에서 Depends 사용 안 하면 됨

3. **FCM send_fcm_message 함수**: `routers/fcm.py`에 이미 존재 확인 후 import
   - 없으면 firebase_admin 직접 호출로 대체

4. **equipment_checkins 테이블**: 작업 시작 전 Supabase에서 테이블 생성 SQL 실행

---

## 검증 시나리오

```bash
# 1. QR 생성
curl -X POST https://api.taieng.co.kr/equipment-assets/{asset_id}/generate-qr \
  -H 'Authorization: Bearer {token}'

# 2. QR 스캔 (인증 없음)
curl "https://api.taieng.co.kr/equipment-assets/scan?id={asset_id}"

# 3. RFID 스캔 (인증 없음)
curl "https://api.taieng.co.kr/equipment-assets/scan?rfid=TAG-001"

# 4. 체크인 제출 — 정상 (인증 없음)
curl -X POST https://api.taieng.co.kr/equipment-checkins \
  -H 'Content-Type: application/json' \
  -d '{"equipment_asset_id":"{id}","overall_result":"OK","worker_name":"김작업","scan_method":"QR"}'

# 5. 체크인 제출 — 이상 (FCM 발송 확인)
curl -X POST https://api.taieng.co.kr/equipment-checkins \
  -H 'Content-Type: application/json' \
  -d '{"equipment_asset_id":"{id}","overall_result":"NG","worker_name":"김작업","note":"경적 작동 불량","scan_method":"QR"}'

# 6. 이력 조회
curl "https://api.taieng.co.kr/equipment-checkins?factory_id={factory_id}" \
  -H 'Authorization: Bearer {token}'
```
