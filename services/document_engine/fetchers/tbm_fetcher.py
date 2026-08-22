"""TBM 기록 데이터 패처 (DOC-TBM / 기존 DOC-OSH-056)

데이터 소스: tbm_meetings + tbm_attendees + factories
계약: fetch(params) 로 통일. params={'meeting_id'} 우선, 없으면 {'factory_id', date_from, date_to}로 최신 1건.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from db.supabase_client import get_supabase
from .base_fetcher import BaseFetcher

log = logging.getLogger(__name__)


class TbmFetcher(BaseFetcher):
    doc_id = "DOC-TBM"

    async def fetch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sb = get_supabase()
        meeting_id = params.get("meeting_id")
        factory_id = params.get("factory_id")
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        # 사업장 (factory_id 있을 때만)
        factory: Dict[str, Any] = {}
        if factory_id:
            try:
                fac = (
                    sb.table("factories").select("name, site_address, manager_name")
                    .eq("id", factory_id).limit(1).execute()
                )
                factory = fac.data[0] if fac.data else {}
            except Exception as e:
                log.warning("factory fetch 실패: %s", e)

        # TBM 회의 조회
        try:
            q = sb.table("tbm_meetings").select("*")
            if meeting_id:
                q = q.eq("id", meeting_id)
            else:
                if factory_id:
                    q = q.eq("factory_id", factory_id)
                if date_from:
                    q = q.gte("work_date", str(date_from))
                if date_to:
                    q = q.lte("work_date", str(date_to))
                q = q.order("work_date", desc=True).limit(1)
            mres = q.execute()
        except Exception as e:
            log.warning("tbm fetch 실패: %s", e)
            mres = None

        if not mres or not mres.data:
            return {
                "factory_name": factory.get("name", ""),
                "work_date": "-", "work_location": "-", "conductor_name": "-",
                "work_description": "-", "attendee_count": 0, "meeting_time": "-",
                "risk_items": [], "safety_items": [], "attendees": [],
                "conductor_signature": None, "manager_name": factory.get("manager_name", ""),
            }

        m = mres.data[0]

        # 참석자
        attendees: List[Dict[str, Any]] = []
        try:
            att = (
                sb.table("tbm_attendees")
                .select("name, job_type, subcontractor_name, signature_url, signed_at_final, signed_at, sign_status")
                .eq("meeting_id", m["id"]).execute()
            )
            for a in (att.data or []):
                signed = a.get("signed_at_final") or a.get("signed_at")
                attendees.append({
                    "name": a.get("name", ""),
                    "job_type": a.get("job_type", "-"),
                    "subcontractor_name": a.get("subcontractor_name", ""),
                    "signature_url": a.get("signature_url"),
                    "signed_at": signed[:16].replace("T", " ") if signed else "-",
                })
        except Exception as e:
            log.warning("attendees fetch 실패: %s", e)

        risk_items = m.get("risk_items") or []
        safety_items = m.get("safety_items") or []
        if risk_items and isinstance(risk_items[0], str):
            risk_items = [{"description": r} for r in risk_items]
        if safety_items and isinstance(safety_items[0], str):
            safety_items = [{"description": s} for s in safety_items]

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
            "conductor_signature": None,
            "manager_name": factory.get("manager_name", ""),
        }
