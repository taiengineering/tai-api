"""
법정점검 세트 관리 라우터 — v1.6.0
v1.6.0: inspection_set_items 자동생성 API 추가
  - POST /{set_id}/generate-items  : 단건 점검세트 → 항목 자동생성
  - POST /generate-all-items       : 전체 점검세트 일괄 항목 생성
  법령엔진 룰(obligation_summary, law_name, law_article, obligation_type)을
  기반으로 점검 항목을 자동 매핑. 이미 항목이 있는 세트는 스킵.
v1.5.0: Rolling 생성 방식 전환
  - _build_schedules: 1년치 일괄 → 오늘 이후 첫 번째 planned_date 1건만 생성
  - end_date 파라미터 제거 (실제 INSERT 불필요)
  - GET /inspection-sets/preview-schedule: 캘린더 표시용 가상 렌더링 (DB INSERT 없음)
v1.4.0: 1년치 반복 생성
v1.3.0: anchor 설정 시 work_schedules 1건 생성
v1.2.0: MANUAL 점검세트 등록
v1.1.0: 기준일 설정 API
v1.0.0: 기본 CRUD
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-sets", tags=["inspection_sets"])

VERSION = "1.6.0"

# cycle_unit → relativedelta 매핑
DELTA_MAP = {
    "day":       lambda v: relativedelta(days=v),
    "week":      lambda v: relativedelta(weeks=v),
    "month":     lambda v: relativedelta(months=v),
    "quarter":   lambda v: relativedelta(months=3 * v),
    "half_year": lambda v: relativedelta(months=6 * v),
    "year":      lambda v: relativedelta(years=v),
}

REPEAT_TYPE_MAP = {
    "day":       "daily",
    "week":      "weekly",
    "month":     "monthly",
    "quarter":   "quarterly",
    "half_year": "half_yearly",
    "year":      "yearly",
}

UNIT_KO = {"year": "년", "month": "개월", "quarter": "분기", "half_year": "반기"}

# obligation_type → check_type 분기 (description 접두어로 활용)
CHECK_TYPE_MAP = {
    "INSPECT":    "PASS_FAIL",
    "APPOINT":    "CHECK",
    "REPORT":     "DATE",
    "ACTION":     "PASS_FAIL",
    "NOTIFY":     "DATE",
    "DOCUMENT":   "CHECK",
    "BEFORE_WORK": "PASS_FAIL",
    "OTHER":      "PASS_FAIL",
}


def _get_delta(cycle_unit: str, cycle_value: int):
    fn = DELTA_MAP.get(cycle_unit.lower())
    return fn(cycle_value) if fn else relativedelta(years=cycle_value)


def _calc_next_date(anchor: date, cycle_unit: str, cycle_value: int) -> date:
    """anchor + cycle → next_date."""
    return anchor + _get_delta(cycle_unit, cycle_value)


def _next_planned_from(base: date, cycle_unit: str, cycle_value: int) -> date:
    """
    base(완료일/anchor) 기준으로 오늘 이후 첫 번째 planned_date 1건 계산.
    base 자체가 오늘 이후면 base가 첫 번째.
    """
    delta    = _get_delta(cycle_unit, cycle_value)
    cursor   = base + delta           # base 다음 회차부터 시작
    today    = date.today()
    while cursor < today:             # 과거 스킵
        cursor += delta
    return cursor


def _build_next_schedule_row(iset: dict, base: date) -> dict:
    """
    v1.5.0 Rolling 방식:
    base(완료일 또는 anchor)에서 다음 1건만 생성.
    """
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    planned     = _next_planned_from(base, cycle_unit, cycle_value)
    repeat_type = REPEAT_TYPE_MAP.get(cycle_unit, "yearly")
    source_type = "LEGAL" if iset.get("source") == "LEGAL_ENGINE" else "MANUAL"
    return {
        "factory_id":        iset["factory_id"],
        "company_id":        iset.get("company_id"),
        "inspection_set_id": iset["id"],
        "planned_date":      planned.isoformat(),
        "start_date":        planned.isoformat(),
        "end_date":          planned.isoformat(),
        "repeat_type":       repeat_type,
        "repeat_interval":   cycle_value,
        "status_code":       "SCHEDULED",
        "source_type":       source_type,
        "obligation_type":   iset.get("inspection_category") or "GENERAL",
        "summary":           iset.get("inspection_set_name") or "",
        "active_yn":         True,
        "assigned_user_id":  None,   # 배정은 안전관리자가 시행
    }, planned


def _build_items_for_set(iset: dict, rule: dict) -> List[dict]:
    """
    inspection_set 1건 + 법령룰 1건 → inspection_set_items 행 목록 반환.
    현재는 룰 1건당 항목 1건 생성.
    """
    obligation_type = (rule.get("obligation_type") or "INSPECT").upper()
    check_type = CHECK_TYPE_MAP.get(obligation_type, "PASS_FAIL")
    summary = (rule.get("obligation_summary") or rule.get("remarks") or "").strip()
    law_name = (rule.get("law_name") or "").strip()
    law_article = (rule.get("law_article") or "").strip()
    description = f"[{check_type}] {law_name} {law_article}".strip()

    return [{
        "inspection_set_id": iset["id"],
        "item_seq":          1,
        "item_name":         summary or f"{law_name} {law_article}".strip() or "점검 항목",
        "description":       description,
        "is_required":       True,
        "is_active":         True,
    }]


# ── Pydantic 모델 ─────────────────────────────────────

class AnchorBody(BaseModel):
    anchor_date:          Optional[str] = None
    schedule_anchor_date: Optional[str] = None   # 하위 호환
    last_inspection_date: Optional[str] = None


class BulkAnchorBody(BaseModel):
    factory_id:  str
    anchor_date: str


class AnchorBulkItem(BaseModel):
    id: str
    schedule_anchor_date: str
    last_inspection_date: Optional[str] = None


class AnchorBulkPatchBody(BaseModel):
    items: List[AnchorBulkItem]


class ManualInspectionSetBody(BaseModel):
    factory_id:           str
    inspection_set_name:  str
    inspection_category:  str = "GENERAL"
    template_id:          Optional[str] = None
    cycle_value:          int = 1
    cycle_unit:           str = "month"
    cycle_base_type:      str = "LAST_INSPECTION"
    description:          Optional[str] = None


# ══════════════════════════════════════════════
# GET /inspection-sets
# ══════════════════════════════════════════════

@router.get("")
def get_inspection_sets(
    factory_id:       Optional[str]  = Query(None),
    source:           Optional[str]  = Query(None),
    anchor_confirmed: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    query = supabase.table("inspection_sets").select(
        "id, company_id, factory_id, inspection_set_name, inspection_set_code, "
        "legal_rule_id, law_name, law_article, cycle_unit, cycle_value, "
        "cycle_base_type, cycle_base_guide, "
        "schedule_anchor_date, last_inspection_date, next_planned_date, anchor_confirmed, "
        "description, source, is_active, status_code, created_at, updated_at",
        count="exact"
    )
    if factory_id:              query = query.eq("factory_id", factory_id)
    if source:                  query = query.eq("source", source)
    if anchor_confirmed is not None: query = query.eq("anchor_confirmed", anchor_confirmed)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    return {
        "status": "success",
        "data": {
            "items": res.data or [], "total": res.count or 0,
            "page": page, "size": size,
            "total_pages": ((res.count or 0) + size - 1) // size if res.count else 0,
        }
    }


# ══════════════════════════════════════════════
# POST /inspection-sets/manual  ← /{id} 앞에 선언
# ══════════════════════════════════════════════

@router.post("/manual")
def create_manual_inspection_set(body: ManualInspectionSetBody):
    """MANUAL 점검세트 등록."""
    supabase = get_supabase()
    if not (body.inspection_set_name or "").strip():
        raise HTTPException(status_code=422, detail="점검 세트명은 필수입니다.")

    fac_res = supabase.table("factories").select("company_id").eq(
        "id", body.factory_id
    ).limit(1).execute()
    company_id = (fac_res.data[0].get("company_id") if fac_res.data else None)

    guide = f"마지막 점검일로부터 {body.cycle_value}{UNIT_KO.get(body.cycle_unit, body.cycle_unit)}마다"
    res = supabase.table("inspection_sets").insert({
        "factory_id":          body.factory_id,
        "company_id":          company_id,
        "inspection_set_name": body.inspection_set_name.strip(),
        "inspection_category": body.inspection_category,
        "template_id":         body.template_id,
        "cycle_value":         body.cycle_value,
        "cycle_unit":          body.cycle_unit,
        "cycle_base_type":     body.cycle_base_type,
        "cycle_base_guide":    guide,
        "custom_description":  body.description,
        "source":              "MANUAL",
        "status_code":         "PENDING_ANCHOR",
        "anchor_confirmed":    False,
        "is_active":           True,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="점검 세트 생성 실패")
    return {
        "status":  "success",
        "message": f'"{body.inspection_set_name}" 점검 세트 생성 완료',
        "data":    {"inspection_set_id": res.data[0]["id"]},
    }


# ══════════════════════════════════════════════
# GET /inspection-sets/preview-schedule  v1.5.0 (DB INSERT 없음)
# ══════════════════════════════════════════════

@router.get("/preview-schedule")
def preview_schedule(
    factory_id: str = Query(..., description="시설 ID"),
    months:     int = Query(3, ge=1, le=12, description="향후 대상 개월수 (1~12)"),
):
    """
    캘린더 표시용 가상 렌더링 (v1.5.0).
    DB에 INSERT 없이 순수 계산만으로 향후 months개월치 예정일 반환.
    프론트 캘린더에서 점선/회색 스타일로 표시.
    """
    supabase = get_supabase()

    sets_res = supabase.table("inspection_sets").select(
        "id, inspection_set_name, cycle_unit, cycle_value, "
        "schedule_anchor_date, schedule_end_date, anchor_confirmed, next_planned_date"
    ).eq("factory_id", factory_id).eq("anchor_confirmed", True).eq("is_active", True).execute()
    sets = sets_res.data or []

    today    = date.today()
    end_date = today + relativedelta(months=months)
    preview  = []

    for iset in sets:
        cycle_unit  = (iset.get("cycle_unit") or "year").lower()
        cycle_value = int(iset.get("cycle_value") or 1)
        delta       = _get_delta(cycle_unit, cycle_value)
        name        = iset.get("inspection_set_name") or ""

        anchor_str = iset.get("schedule_anchor_date")
        if not anchor_str:
            continue

        next_str = iset.get("next_planned_date")
        cursor   = date.fromisoformat(next_str) if next_str else date.fromisoformat(anchor_str) + delta

        end_str  = iset.get("schedule_end_date")
        iset_end = date.fromisoformat(end_str) if end_str else end_date
        eff_end  = min(end_date, iset_end)

        while cursor <= eff_end:
            preview.append({
                "inspection_set_id":   iset["id"],
                "inspection_set_name": name,
                "planned_date":        cursor.isoformat(),
                "is_actual":           False,
                "cycle":               f"{cycle_value} {cycle_unit}",
            })
            cursor += delta

    preview.sort(key=lambda x: x["planned_date"])

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "from":       today.isoformat(),
            "to":         end_date.isoformat(),
            "months":     months,
            "count":      len(preview),
            "preview":    preview,
        }
    }


# ══════════════════════════════════════════════
# POST /inspection-sets/anchor/bulk  ← /{id} 앞에 선언
# ══════════════════════════════════════════════

@router.post("/anchor/bulk")
def set_anchor_bulk(body: BulkAnchorBody):
    """
    factory_id의 PENDING_ANCHOR 상태 inspection_sets 전체에
    동일 anchor_date 적용 + Rolling 1건 일정 생성.
    """
    supabase = get_supabase()

    sets_res = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, cycle_value, cycle_unit, "
        "inspection_set_name, inspection_category, source"
    ).eq("factory_id", body.factory_id).eq("status_code", "PENDING_ANCHOR").eq("is_active", True).execute()
    sets = sets_res.data or []

    if not sets:
        return {
            "status":  "success",
            "message": "처리할 PENDING_ANCHOR 상태 점검세트가 없습니다.",
            "data":    {"total_sets": 0, "total_created": 0, "results": []},
        }

    anchor = date.fromisoformat(body.anchor_date)
    results, total_created = [], 0

    for iset in sets:
        iset_id = iset["id"]
        try:
            row, planned = _build_next_schedule_row(iset, anchor)

            supabase.table("inspection_sets").update({
                "schedule_anchor_date": anchor.isoformat(),
                "next_planned_date":    planned.isoformat(),
                "anchor_confirmed":     True,
                "status_code":          "ACTIVE",
                "updated_at":           datetime.now().isoformat(),
            }).eq("id", iset_id).execute()

            supabase.table("work_schedules").delete().eq(
                "inspection_set_id", iset_id
            ).eq("status_code", "SCHEDULED").execute()

            r = supabase.table("work_schedules").insert(row).execute()
            created = len(r.data or [])
            total_created += created
            results.append({"id": iset_id, "name": iset.get("inspection_set_name"),
                            "next_planned_date": planned.isoformat(), "created": created})
        except Exception as e:
            results.append({"id": iset_id, "name": iset.get("inspection_set_name"), "error": str(e)})

    return {
        "status":  "success",
        "message": f"{len(sets)}개 세트 처리, 총 {total_created}개 일정 생성",
        "data": {
            "factory_id":    body.factory_id,
            "anchor_date":   anchor.isoformat(),
            "total_sets":    len(sets),
            "total_created": total_created,
            "results":       results,
        },
    }


# ══════════════════════════════════════════════
# PATCH /inspection-sets/anchor/bulk  (하위 호환)
# ══════════════════════════════════════════════

@router.patch("/anchor/bulk")
def bulk_update_anchor(body: AnchorBulkPatchBody):
    """items 배열 방식 Rolling 업데이트 (하위 호환)."""
    supabase = get_supabase()
    updated_count, errors = 0, []

    for item in body.items:
        try:
            res = supabase.table("inspection_sets").select(
                "id, cycle_value, cycle_unit, factory_id, company_id, "
                "inspection_set_name, inspection_category, source"
            ).eq("id", item.id).limit(1).execute()
            if not res.data:
                errors.append({"id": item.id, "reason": "점검 세트를 찾을 수 없습니다."})
                continue

            iset   = res.data[0]
            anchor = date.fromisoformat(item.schedule_anchor_date)
            row, planned = _build_next_schedule_row(iset, anchor)

            update_data = {
                "schedule_anchor_date": anchor.isoformat(),
                "next_planned_date":    planned.isoformat(),
                "anchor_confirmed":     True,
                "status_code":          "ACTIVE",
                "updated_at":           datetime.now().isoformat(),
            }
            if item.last_inspection_date:
                update_data["last_inspection_date"] = item.last_inspection_date
            supabase.table("inspection_sets").update(update_data).eq("id", item.id).execute()

            try:
                supabase.table("work_schedules").delete().eq(
                    "inspection_set_id", item.id
                ).eq("status_code", "SCHEDULED").execute()
                supabase.table("work_schedules").insert(row).execute()
            except Exception:
                pass

            updated_count += 1
        except Exception as e:
            errors.append({"id": item.id, "reason": str(e)})

    return {"status": "success", "data": {"updated": updated_count, "failed": len(errors), "errors": errors}}


# ══════════════════════════════════════════════
# POST /inspection-sets/generate-all-items  v1.6.0
# ← /generate-all-items는 /{id} 앞에 반드시 선언
# ══════════════════════════════════════════════

@router.post("/generate-all-items")
def generate_all_items(
    factory_id: Optional[str] = Query(None, description="특정 시설만 처리 (미지정 시 전체)"),
    dry_run:    bool          = Query(False, description="True면 INSERT 없이 예상 결과만 반환"),
):
    """
    v1.6.0 — inspection_set_items 일괄 자동생성.

    처리 대상:
    - legal_rule_id가 있는 inspection_sets
    - 해당 legal_rule_id로 master_building_legal_rules 조회 (is_active=True)
    - 이미 inspection_set_items가 있는 set_id는 스킵 (덮어쓰지 않음)

    결과: 생성된 items 수, 스킵된 sets 수 반환
    """
    supabase = get_supabase()

    # 1. 대상 inspection_sets 조회 (legal_rule_id 있는 것만)
    q = supabase.table("inspection_sets").select(
        "id, inspection_set_name, legal_rule_id, factory_id"
    ).not_.is_("legal_rule_id", "null").eq("is_active", True)
    if factory_id:
        q = q.eq("factory_id", factory_id)

    sets_res = q.execute()
    sets = sets_res.data or []

    if not sets:
        return {
            "status": "success",
            "message": "처리할 점검세트가 없습니다.",
            "data": {"total_sets": 0, "created": 0, "skipped": 0, "failed": 0},
        }

    # 2. 이미 items가 있는 set_id 목록 조회 (스킵 대상)
    set_ids = [s["id"] for s in sets]
    # 100건씩 나눠 조회 (API size limit 100)
    existing_set_ids: set = set()
    for i in range(0, len(set_ids), 100):
        chunk = set_ids[i:i+100]
        ex_res = supabase.table("inspection_set_items").select(
            "inspection_set_id"
        ).in_("inspection_set_id", chunk).execute()
        for row in (ex_res.data or []):
            existing_set_ids.add(row["inspection_set_id"])

    # 3. 처리 대상 룰 일괄 조회
    rule_ids = list({s["legal_rule_id"] for s in sets if s.get("legal_rule_id")})
    rules_map: dict = {}
    for i in range(0, len(rule_ids), 100):
        chunk = rule_ids[i:i+100]
        r_res = supabase.table("master_building_legal_rules").select(
            "rule_id, obligation_summary, obligation_type, law_name, law_article"
        ).in_("rule_id", chunk).eq("is_active", True).execute()
        for rule in (r_res.data or []):
            rules_map[rule["rule_id"]] = rule

    # 4. 항목 생성
    created, skipped, failed = 0, 0, 0
    preview_rows = []

    for iset in sets:
        set_id   = iset["id"]
        rule_id  = iset.get("legal_rule_id")
        set_name = iset.get("inspection_set_name", "")

        # 이미 items 있으면 스킵
        if set_id in existing_set_ids:
            skipped += 1
            continue

        # 룰 없으면 스킵
        rule = rules_map.get(rule_id)
        if not rule:
            skipped += 1
            continue

        item_rows = _build_items_for_set(iset, rule)
        preview_rows.extend(item_rows)

        if not dry_run:
            try:
                supabase.table("inspection_set_items").insert(item_rows).execute()
                created += len(item_rows)
            except Exception as e:
                print(f"[generate-all-items] 생성 실패 set_id={set_id}: {e}")
                failed += 1
        else:
            created += len(item_rows)

    return {
        "status": "success",
        "message": (
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"총 {len(sets)}개 세트 처리 — 생성 {created}건, 스킵 {skipped}건, 실패 {failed}건"
        ),
        "data": {
            "total_sets": len(sets),
            "created":    created,
            "skipped":    skipped,
            "failed":     failed,
            "dry_run":    dry_run,
            **({"preview": preview_rows[:20]} if dry_run else {}),
        },
    }


# ══════════════════════════════════════════════
# PATCH /inspection-sets/{id}/anchor  v1.5.0
# ══════════════════════════════════════════════

@router.patch("/{inspection_set_id}/anchor")
def update_inspection_anchor(inspection_set_id: str, body: AnchorBody):
    """
    기준일 설정 + Rolling 1건 일정 생성 (v1.5.0).

    - anchor_date / schedule_anchor_date 중 하나 필수
    - 기존 SCHEDULED 삭제 후 오늘 이후 첫 번째 planned_date 1건 INSERT
    - COMPLETED 절대 건드리지 않음
    """
    supabase = get_supabase()

    anchor_str = body.anchor_date or body.schedule_anchor_date
    if not anchor_str:
        raise HTTPException(status_code=422, detail="anchor_date 또는 schedule_anchor_date는 필수입니다.")

    res = supabase.table("inspection_sets").select(
        "id, cycle_value, cycle_unit, factory_id, company_id, "
        "inspection_set_name, inspection_category, source, schedule_end_date"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")

    iset        = res.data[0]
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    anchor      = date.fromisoformat(anchor_str)

    row, planned = _build_next_schedule_row(iset, anchor)

    end_str = iset.get("schedule_end_date")
    if end_str and planned > date.fromisoformat(end_str):
        return {
            "status":  "success",
            "message": "일정 종료일이 지나 새로운 회차 생성 안 함.",
            "data": {
                "inspection_set_id": inspection_set_id,
                "anchor_date":       anchor.isoformat(),
                "next_planned_date": planned.isoformat(),
                "anchor_confirmed":  True,
                "created":           0,
            },
        }

    update_data = {
        "schedule_anchor_date": anchor.isoformat(),
        "next_planned_date":    planned.isoformat(),
        "anchor_confirmed":     True,
        "status_code":          "ACTIVE",
        "updated_at":           datetime.now().isoformat(),
    }
    if body.last_inspection_date:
        update_data["last_inspection_date"] = body.last_inspection_date

    upd = supabase.table("inspection_sets").update(update_data).eq("id", inspection_set_id).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="inspection_sets 업데이트 실패")

    created = 0
    try:
        supabase.table("work_schedules").delete().eq(
            "inspection_set_id", inspection_set_id
        ).eq("status_code", "SCHEDULED").execute()

        r = supabase.table("work_schedules").insert(row).execute()
        created = len(r.data or [])
    except Exception as e:
        print(f"[ANCHOR] work_schedules 생성 실패 (id={inspection_set_id}): {e}")

    return {
        "status":  "success",
        "message": f"{created}개 일정이 생성됐습니다.",
        "data": {
            "inspection_set_id": inspection_set_id,
            "anchor_date":       anchor.isoformat(),
            "next_planned_date": planned.isoformat(),
            "anchor_confirmed":  True,
            "cycle":             f"{cycle_value} {cycle_unit}",
            "created":           created,
        },
    }


# ══════════════════════════════════════════════
# POST /inspection-sets/{set_id}/generate-items  v1.6.0
# ══════════════════════════════════════════════

@router.post("/{inspection_set_id}/generate-items")
def generate_items(inspection_set_id: str):
    """
    v1.6.0 — 단건 점검세트 → inspection_set_items 자동생성.

    - legal_rule_id가 없으면 422
    - 이미 items가 있으면 스킵 (409)
    - 법령룰에서 obligation_summary, obligation_type, law_name, law_article 읽어 항목 생성
    """
    supabase = get_supabase()

    # 1. 점검세트 조회
    set_res = supabase.table("inspection_sets").select(
        "id, inspection_set_name, legal_rule_id, factory_id"
    ).eq("id", inspection_set_id).limit(1).execute()

    if not set_res.data:
        raise HTTPException(status_code=404, detail="점검세트를 찾을 수 없습니다.")

    iset    = set_res.data[0]
    rule_id = iset.get("legal_rule_id")

    if not rule_id:
        raise HTTPException(
            status_code=422,
            detail="legal_rule_id가 없는 점검세트입니다. MANUAL 등록 건은 항목을 수동으로 추가하세요."
        )

    # 2. 이미 items 있으면 스킵
    ex_res = supabase.table("inspection_set_items").select(
        "id"
    ).eq("inspection_set_id", inspection_set_id).limit(1).execute()

    if ex_res.data:
        return {
            "status":  "skipped",
            "message": "이미 점검 항목이 존재합니다. 덮어쓰지 않습니다.",
            "data": {
                "inspection_set_id": inspection_set_id,
                "existing_count":    len(ex_res.data),
                "created":           0,
            },
        }

    # 3. 법령룰 조회 (is_active=True 필수)
    rule_res = supabase.table("master_building_legal_rules").select(
        "rule_id, obligation_summary, obligation_type, law_name, law_article"
    ).eq("rule_id", rule_id).eq("is_active", True).limit(1).execute()

    if not rule_res.data:
        raise HTTPException(
            status_code=404,
            detail=f"법령룰을 찾을 수 없습니다 (rule_id={rule_id}). 비활성화 또는 삭제된 룰일 수 있습니다."
        )

    rule = rule_res.data[0]

    # 4. 항목 생성
    item_rows = _build_items_for_set(iset, rule)

    ins_res = supabase.table("inspection_set_items").insert(item_rows).execute()
    created = len(ins_res.data or [])

    return {
        "status":  "success",
        "message": f"{created}개 점검 항목이 생성됐습니다.",
        "data": {
            "inspection_set_id":   inspection_set_id,
            "inspection_set_name": iset.get("inspection_set_name"),
            "rule_id":             rule_id,
            "obligation_type":     rule.get("obligation_type"),
            "created":             created,
            "items":               ins_res.data or [],
        },
    }


# ══════════════════════════════════════════════
# 기존 엔드포인트 (하위 호환)
# ══════════════════════════════════════════════

@router.get("/company/{company_id}")
def get_company_inspection_sets(company_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets").select("*").eq(
        "company_id", company_id
    ).order("created_at", desc=True).execute()
    return {"status": "success", "data": result.data}


@router.get("/factory/{factory_id}")
def get_factory_inspection_sets(factory_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets").select("*").eq(
        "factory_id", factory_id
    ).order("created_at", desc=True).execute()
    return {"status": "success", "data": result.data}


@router.get("/{inspection_set_id}")
def get_inspection_set(inspection_set_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets").select("*").eq(
        "id", inspection_set_id
    ).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="점검세트를 찾을 수 없습니다")
    return {"status": "success", "data": result.data}
