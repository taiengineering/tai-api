"""TBM 기록 데이터 패처 (DOC-OSH-056)

데이터 소스:
  - tbm_meetings: 회의 기본 정보
  - tbm_attendees: 참석자 + 서명
  - factories: 사업장 정보
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from .base_fetcher import BaseFetcher


class TbmFetcher(BaseFetcher):
    doc_id = "DOC-OSH-056"

    async def fetch(
        self,
        factory_id: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        meeting_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        supabase = get_supabase()

        # 사업장 정보
        fac = (
            supabase.table("factories")
            .select("name, site_address, manager_name")
            .eq("id", factory_id)
            .limit(1)
            .execute()
        )
        factory = fac.data[0] if fac.data else {}

        # TBM 회의 조회
        query = (
            supabase.table("tbm_meetings")
            .select("*")
            .eq("factory_id", factory_id)
        )
        if meeting_id:
            query = query.eq("id", meeting_id)
        else:
            # 최신 1건
            if date_from:
                query = query.gte("work_date", str(date_from))
            if date_to:
                query = query.lte("work_date", str(date_to))
            query = query.order("work_date", desc=True).limit(1)

        meeting_res = query.execute()
        if not meeting_res.data:
            return {
                "factory_name": factory.get("name", ""),
                "work_date": "-",
                "work_location": "-",
                "conductor_name": "-",
                "work_description": "-",
                "attendee_count": 0,
                "meeting_time": "-",
                "risk_items": [],
                "safety_items": [],
                "attendees": [],
                "conductor_signature": None,
                "manager_name": factory.get("manager_name", ""),
            }

        m = meeting_res.data[0]

        # 참석자 조회
        att_res = (
            supabase.table("tbm_attendees")
            .select("name, job_type, subcontractor_name, signature_url, signed_at_final, sign_status")
            .eq("meeting_id", m["id"])
            .execute()
        )

        attendees: List[Dict[str, Any]] = []
        for a in (att_res.data or []):
            signed = a.get("signed_at_final") or a.get("signed_at")
            attendees.append({
                "name": a.get("name", ""),
                "job_type": a.get("job_type", "-"),
                "subcontractor_name": a.get("subcontractor_name", ""),
                "signature_url": a.get("signature_url"),
                "signed_at": signed[:16].replace("T", " ") if signed else "-",
            })

        # risk_items, safety_items (JSONB)
        risk_items = m.get("risk_items") or []
        safety_items = m.get("safety_items") or []

        # JSONB가 문자열 리스트일 수 있음 → dict로 정규화
        if risk_items and isinstance(risk_items[0], str):
            risk_items = [{"description": r} for r in risk_items]
        if safety_items and isinstance(safety_items[0], str):
            safety_items = [{"description": s} for s in safety_items]

        # 회의 시간
        meeting_time = "-"
        md = m.get("meeting_date") or m.get("created_at")
        if md:
            meeting_time = str(md)[:16].replace("T", " ")

        return {
            "factory_name": factory.get("name", ""),
            "work_date": str(m.get("work_date", "-")),
            "work_location": m.get("work_location", "-"),
            "conductor_name": m.get("conductor_name", "-"),
            "work_description": m.get("work_description", "-"),
            "attendee_count": m.get("attendee_count", len(attendees)),
            "meeting_time": meeting_time,
            "risk_items": risk_items,
            "safety_items": safety_items,
            "attendees": attendees,
            "conductor_signature": None,  # TODO: conductor 서명 연결
            "manager_name": factory.get("manager_name", ""),
        }
