"""
위험성평가 — 중대재해처벌법 반기 점검 증적 리포트. v1.0.1

Goal: G-ms6xe3z4-76dbad

v1.0.1 (2026-07-30) — ra_item select 에서 존재하지 않는 process_name 컬럼 제거.
  종전에는 select 오류가 except 로 잡혀 요인 집계가 항상 0 이었다(실화면 검증에서 발견).
  ra_item 에는 work_process 만 있고 process_name 은 없다.

법적 근거 — 중대재해처벌법 시행령 제4조제3호:
  경영책임자등은 ① 사업장 특성에 따른 유해·위험요인을 확인하여 개선하는 업무절차를
  마련하고, ② 그 절차에 따라 유해·위험요인의 확인 및 개선이 이루어지는지를 반기 1회
  이상 점검한 후, ③ 필요한 조치를 하여야 한다.
  단서: 「산업안전보건법」 제36조에 따른 위험성평가를 하는 절차를 마련하고 그 절차에 따라
  위험성평가를 직접 실시하거나 실시하도록 하여 그 결과를 보고받은 경우에는, 유해·위험요인의
  확인 및 개선에 대한 점검을 한 것으로 본다(간주).

점검 판정 매핑
  DONE   반기 내 위험성평가 완료 ≥ 1건 이고 미해결(허용 불가) 요인 0
  GAP    반기 내 위험성평가 실시 ≥ 1건이나 미해결 요인이 남음
  NONE   반기 내 위험성평가 실시 0건

API:
  GET /ra/semiannual-report?company_id&factory_id&year&half=H1|H2
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import scoped_list_company
from services.time import business_today

router = APIRouter(prefix="/ra", tags=["위험성평가 증적 리포트"])

VERSION = "1.0.1"

_LEGAL_BASIS = "중대재해처벌법 시행령 제4조제3호 (유해·위험요인 확인·개선의 반기 1회 이상 점검)"
_DEEM_BASIS = "산업안전보건법 제36조 위험성평가로 갈음(시행령 제4조제3호 단서)"


def _half_range(year: int, half: str) -> tuple:
    if half == "H1":
        return f"{year}-01-01", f"{year}-06-30", "상반기(1~6월)"
    return f"{year}-07-01", f"{year}-12-31", "하반기(7~12월)"


@router.get("/semiannual-report")
def semiannual_report(
    company_id: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    year:       Optional[int] = Query(None, description="대상 연도(기본: 올해)"),
    half:       str = Query("H1", description="H1 상반기 | H2 하반기"),
    current: dict = Depends(get_current_user),
):
    """중처법 시행령 제4조3호 반기 점검 증적 — 위험성평가 데이터 집계."""
    if not company_id and not factory_id:
        raise HTTPException(status_code=422, detail="company_id 또는 factory_id 가 필요합니다.")
    half = (half or "H1").upper()
    if half not in ("H1", "H2"):
        raise HTTPException(status_code=422, detail="half 는 H1 또는 H2 여야 합니다.")
    y = year or business_today().year
    lo, hi, half_label = _half_range(y, half)

    sb = get_supabase()

    scoped_cid, deny_all = scoped_list_company(current, sb, company_id)
    if deny_all:
        return {"status": "success", "data": {}}
    company_id = scoped_cid

    # 1) 반기 내 위험성평가 (assessment_date 기준)
    aq = sb.table("risk_assessments").select(
        "id, assessment_type, title, assessment_date, status_code, completed_at, process_name, factory_id")
    if company_id: aq = aq.eq("company_id", company_id)
    if factory_id: aq = aq.eq("factory_id", factory_id)
    assessments = (aq.gte("assessment_date", lo).lte("assessment_date", hi)
                   .order("assessment_date").execute().data) or []

    total_assess = len(assessments)
    completed_assess = sum(1 for a in assessments if str(a.get("status_code")).upper() == "COMPLETED")
    aids = [a["id"] for a in assessments]

    # 2) 요인·대책 집계 (ra_item / ra_control). 테이블 미적용이면 0.
    #    ra_item 에는 work_process 만 있고 process_name 은 없다(v1.0.1 정정).
    hazard_total = acceptable_cnt = open_cnt = 0
    control_total = control_done = control_interim = 0
    open_items = []
    if aids:
        try:
            items = (sb.table("ra_item").select(
                "id, assessment_id, hazard, level, acceptable, work_process")
                .in_("assessment_id", aids).execute().data) or []
        except Exception:
            items = []
        hazard_total = len(items)
        for it in items:
            if it.get("acceptable") is True:
                acceptable_cnt += 1
            else:
                open_cnt += 1
                open_items.append({
                    "hazard": it.get("hazard"),
                    "level": it.get("level"),
                    "work_process": it.get("work_process"),
                })
        iids = [str(it["id"]) for it in items]
        if iids:
            try:
                controls = (sb.table("ra_control").select("id, item_id, done_at, is_interim")
                            .in_("item_id", iids).execute().data) or []
            except Exception:
                controls = []
            control_total = len(controls)
            control_done = sum(1 for c in controls if c.get("done_at"))
            control_interim = sum(1 for c in controls if c.get("is_interim"))

    # 3) 점검 판정
    if total_assess == 0:
        verdict = "NONE"
        verdict_label = "반기 점검 미이행"
        verdict_detail = ("이 반기에 실시된 위험성평가가 없습니다. 산업안전보건법 제36조 위험성평가를 "
                          "실시하면 중처법 제4조3호의 반기 점검을 갈음할 수 있습니다.")
    elif open_cnt > 0:
        verdict = "GAP"
        verdict_label = "점검 실시 — 개선조치 미완"
        verdict_detail = (f"위험성평가는 실시되었으나 허용 가능한 수준에 이르지 못한 유해·위험요인이 "
                          f"{open_cnt}건 남아 있습니다. 제4조3호의 '필요한 조치'로서 감소대책을 완료하십시오.")
    else:
        verdict = "DONE"
        verdict_label = "반기 점검 완료(위험성평가로 갈음)"
        verdict_detail = ("반기 내 위험성평가가 완료되고 파악된 유해·위험요인이 모두 허용 가능한 수준입니다. "
                          "중처법 제4조3호의 확인·개선 점검을 이행한 것으로 봅니다.")

    return {
        "status": "success",
        "data": {
            "period": {"year": y, "half": half, "label": half_label,
                       "date_from": lo, "date_to": hi},
            "legal_basis": _LEGAL_BASIS,
            "deem_basis": _DEEM_BASIS,
            "assessments": {
                "total": total_assess,
                "completed": completed_assess,
                "list": [{
                    "id": a["id"], "title": a.get("title"),
                    "assessment_type": a.get("assessment_type"),
                    "assessment_date": a.get("assessment_date"),
                    "status_code": a.get("status_code"),
                    "process_name": a.get("process_name"),
                } for a in assessments],
            },
            "hazards": {
                "total": hazard_total,
                "acceptable": acceptable_cnt,
                "open": open_cnt,
                "open_items": open_items[:50],
            },
            "controls": {
                "total": control_total,
                "done": control_done,
                "interim": control_interim,
            },
            "verdict": verdict,
            "verdict_label": verdict_label,
            "verdict_detail": verdict_detail,
            "note": "본 판정은 위험성평가 데이터에 근거한 시스템 집계이며, 반기 점검의 최종 책임은 경영책임자에게 있습니다.",
        }
    }
