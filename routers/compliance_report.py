"""
routers/compliance_report.py — P2-3 증빙 이행 리포트

운영 SaaS 도메인 데이터(점검 이행률·미이행 에스컬레이션·교육·TBM)를
대상 기간·사업장 기준으로 집계해 Gotenberg A4 PDF 증빙 리포트로 생성.
법령/룰 엔진과 무관(엔진 독립). 데이터 소스는 전부 운영 테이블.

POST /compliance-report/generate
  body: { factory_id, date_from(YYYY-MM-DD), date_to(YYYY-MM-DD), company_id? }
  → application/pdf (attachment)

각 섹션은 스키마 드리프트/희박 데이터에 견디도록 try/except 로 방어(실패 시 0/빈값).
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.document_engine.renderer import generate_document_pdf

router = APIRouter(prefix="/compliance-report", tags=["compliance-report"])

DOC_ID = "DOC-COMPLIANCE-REPORT"


class ComplianceReportBody(BaseModel):
    factory_id: str
    date_from: str
    date_to: str
    company_id: Optional[str] = None


def _is_done(row: dict) -> bool:
    s = (row.get("status_code") or "").upper()
    return s in ("COMPLETED", "DONE") or bool(row.get("completed_at"))


def _assemble(body: ComplianceReportBody) -> Dict[str, Any]:
    sb = get_supabase()
    fid = body.factory_id
    dfrom, dto = body.date_from, body.date_to

    # 사업장/회사
    factory: Dict[str, Any] = {}
    try:
        fr = sb.table("factories").select(
            "name, site_address, manager_name, company_id"
        ).eq("id", fid).limit(1).execute()
        factory = fr.data[0] if fr.data else {}
    except Exception:
        pass

    company_id = body.company_id or factory.get("company_id")
    company_name = ""
    if company_id:
        try:
            cr = sb.table("companies").select("name").eq("id", company_id).limit(1).execute()
            company_name = cr.data[0].get("name", "") if cr.data else ""
        except Exception:
            pass

    # A. 점검 이행률 (work_schedules)
    compliance = {"planned": 0, "done": 0, "pending": 0, "overdue": 0, "rate": 0}
    try:
        ws = sb.table("work_schedules").select(
            "planned_date, completed_at, status_code"
        ).eq("factory_id", fid).gte("planned_date", dfrom).lte("planned_date", dto).limit(2000).execute()
        rows = ws.data or []
        planned = len(rows)
        done = sum(1 for r in rows if _is_done(r))
        today = date.today().isoformat()
        overdue = sum(1 for r in rows if not _is_done(r) and str(r.get("planned_date") or "") < today)
        compliance = {
            "planned": planned,
            "done": done,
            "pending": planned - done,
            "overdue": overdue,
            "rate": round(done / planned * 100) if planned else 0,
        }
    except Exception:
        pass

    # B. 미이행·에스컬레이션 (overdue_history)
    escalation = {"lvl1": 0, "lvl2": 0, "lvl3": 0, "lvl4": 0, "resolved": 0, "total": 0, "items": []}
    try:
        oh = sb.table("overdue_history").select(
            "overdue_level, action_type, resolved, created_at"
        ).eq("factory_id", fid).gte("created_at", dfrom).lte("created_at", dto + "T23:59:59") \
            .order("created_at", desc=True).limit(500).execute()
        rows = oh.data or []
        for r in rows:
            try:
                lvl = int(r.get("overdue_level") or 0)
            except Exception:
                lvl = 0
            if 1 <= lvl <= 4:
                escalation[f"lvl{lvl}"] += 1
            if r.get("resolved"):
                escalation["resolved"] += 1
        escalation["total"] = len(rows)
        escalation["items"] = [{
            "date": str(r.get("created_at", ""))[:10],
            "level": r.get("overdue_level"),
            "action": r.get("action_type", ""),
            "resolved": "완료" if r.get("resolved") else "미완료",
        } for r in rows[:20]]
    except Exception:
        pass

    # C. 교육 (education_history)
    education = {"total": 0, "completed": 0, "pending": 0, "overdue": 0, "items": []}
    try:
        eh = sb.table("education_history").select(
            "education_code, status, completed_date, due_date, institution_name"
        ).eq("factory_id", fid).limit(500).execute()
        rows = eh.data or []

        def _in_range(r: dict) -> bool:
            d = r.get("completed_date") or r.get("due_date") or ""
            return (not d) or (dfrom <= str(d)[:10] <= dto)

        rows = [r for r in rows if _in_range(r)]
        for r in rows:
            st = (r.get("status") or "").lower()
            if st == "completed":
                education["completed"] += 1
            elif st == "overdue":
                education["overdue"] += 1
            else:
                education["pending"] += 1
        education["total"] = len(rows)
        education["items"] = [{
            "code": r.get("education_code", ""),
            "status": r.get("status", ""),
            "completed_date": str(r.get("completed_date") or "")[:10],
            "institution": r.get("institution_name", ""),
        } for r in rows[:20]]
    except Exception:
        pass

    # D. TBM (tbm_meetings)
    tbm = {"total": 0, "completed": 0, "items": []}
    try:
        tb = sb.table("tbm_meetings").select(
            "work_date, conductor_name, attendee_count, status_code, work_location"
        ).eq("factory_id", fid).gte("work_date", dfrom).lte("work_date", dto) \
            .order("work_date", desc=True).limit(500).execute()
        rows = tb.data or []
        tbm["total"] = len(rows)
        tbm["completed"] = sum(1 for r in rows if (r.get("status_code") or "").upper() in ("COMPLETED", "DONE"))
        tbm["items"] = [{
            "work_date": str(r.get("work_date", "")),
            "conductor": r.get("conductor_name", ""),
            "attendees": r.get("attendee_count", 0),
            "location": r.get("work_location", ""),
            "status": r.get("status_code", ""),
        } for r in rows[:20]]
    except Exception:
        pass

    return {
        "company_name": company_name,
        "factory_name": factory.get("name", ""),
        "factory_address": factory.get("site_address", ""),
        "manager_name": factory.get("manager_name", ""),
        "period_from": dfrom,
        "period_to": dto,
        "compliance": compliance,
        "escalation": escalation,
        "education": education,
        "tbm": tbm,
    }


@router.post("/generate")
async def generate_compliance_report(body: ComplianceReportBody):
    if not body.factory_id:
        raise HTTPException(status_code=400, detail="factory_id 가 필요합니다.")
    if not body.date_from or not body.date_to:
        raise HTTPException(status_code=400, detail="date_from / date_to 가 필요합니다.")

    data = _assemble(body)

    try:
        pdf = await generate_document_pdf(DOC_ID, data)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="리포트 템플릿을 찾을 수 없습니다.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PDF 생성 실패: {e}")

    fname = f"compliance_{body.factory_id[:8]}_{body.date_from}_{body.date_to}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
