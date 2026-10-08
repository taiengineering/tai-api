"""TBM 기록 데이터 패처 (DOC-OSH-056)

데이터 소스: tbm_meetings + tbm_attendees + factories + companies
계약: fetch(params) → template 변수. params={'meeting_id'} 우선, 없으면 {'factory_id', date_from, date_to}로 최신 1건.

CORR-A: factory_id 는 tbm_meetings 원본에서 우선 취득.
         params.factory_id 가 함께 있으면 일치 검증 — 불일치 시 조용히 대체 금지.
         factories 에서 company_id 포함 조회 후 companies 체인 조회.
CORR-B: factory_address, company_name, company_logo, work_time 필드 추가.
         work_time 은 meeting_date 의 HH:MM 으로만 채운다 (created_at fallback 금지).
CORR-C: 서명 상태(sign_status)와 서명 증적(signature_url)을 sign_display 로 분리.
         SIGNED_WITH_EVIDENCE / SIGNED_STATUS_ONLY / UNSIGNED / UNKNOWN.
CORR-D: attendee_count_recorded(원본 기록값) / attendee_count_registered(실제 rows) 구분.
         불일치 시 attendee_count_mismatch=True.
CORR-E: risk_items 가 문자열 배열이면 countermeasure=None 명시 — 임의 생성 금지.
CORR-F: issue_flag 는 DB 값 그대로 전달 — None 이면 None 유지(False 단정 금지).
         has_issue 는 issue_flag 확인된 참석자 기준; 데이터 없으면 None.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from .base_fetcher import BaseFetcher

log = logging.getLogger(__name__)

_DOC_ID = "DOC-OSH-056"


def _attendee_sign_display(a: dict) -> str:
    """서명 상태와 증적을 구분한 display 코드를 반환한다.

    signature_url 이 유일한 증적 근거다 — signed_at 타임스탬프만으로
    서명 이미지가 있다고 추론하지 않는다.
    """
    if a.get("signature_url"):
        return "SIGNED_WITH_EVIDENCE"
    sign_status = (a.get("sign_status") or "").upper()
    if sign_status == "SIGNED":
        return "SIGNED_STATUS_ONLY"
    if sign_status in ("UNSIGNED", "PENDING", ""):
        return "UNSIGNED"
    return "UNKNOWN"


class TbmFetcher(BaseFetcher):
    doc_id = _DOC_ID

    async def fetch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sb = get_supabase()
        meeting_id = params.get("meeting_id")
        factory_id_param: Optional[str] = params.get("factory_id")
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        # 1. TBM 회의 조회
        try:
            q = sb.table("tbm_meetings").select("*")
            if meeting_id:
                q = q.eq("id", meeting_id)
            else:
                if factory_id_param:
                    q = q.eq("factory_id", factory_id_param)
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
                "company_name": "", "company_logo": None,
                "factory_name": "", "factory_address": "", "manager_name": "",
                "work_date": "-", "work_time": "", "work_location": "-",
                "conductor_name": "-", "work_description": "-",
                "attendee_count": 0, "attendee_count_recorded": 0,
                "attendee_count_registered": 0, "attendee_count_mismatch": False,
                "work_type": "", "doc_id": _DOC_ID,
                "risk_items": [], "safety_items": [], "attendees": [],
                "conductor_signature": None, "has_issue": None,
                "empty_rows": [],
            }

        m = mres.data[0]

        # 2. CORR-A: factory_id 결정 — 회의 원본 우선, 불일치 시 에러
        factory_id_meeting = m.get("factory_id")
        if (
            factory_id_param
            and factory_id_meeting
            and factory_id_param != factory_id_meeting
        ):
            raise ValueError(
                f"params.factory_id {factory_id_param!r} 가 "
                f"meeting.factory_id {factory_id_meeting!r} 와 다릅니다."
            )
        factory_id = factory_id_param or factory_id_meeting

        # 3. 사업장 + 회사
        factory: Dict[str, Any] = {}
        company: Dict[str, Any] = {}
        if factory_id:
            try:
                fac = (
                    sb.table("factories")
                    .select("name, site_address, manager_name, company_id")
                    .eq("id", factory_id).limit(1).execute()
                )
                factory = fac.data[0] if fac.data else {}
            except Exception as e:
                log.warning("factory fetch 실패: %s", e)
            cid = factory.get("company_id")
            if cid:
                try:
                    c = (
                        sb.table("companies")
                        .select("name, logo_url")
                        .eq("id", cid).limit(1).execute()
                    )
                    company = c.data[0] if c.data else {}
                except Exception as e:
                    log.warning("company fetch 실패: %s", e)

        # 4. 참석자 (CORR-C sign_display, CORR-F issue_flag None 유지)
        attendees: List[Dict[str, Any]] = []
        try:
            att = (
                sb.table("tbm_attendees")
                .select(
                    "name, job_type, subcontractor_name, "
                    "signature_url, signed_at_final, signed_at, sign_status, "
                    "issue_flag, issue_note"
                )
                .eq("meeting_id", m["id"]).execute()
            )
            for a in (att.data or []):
                attendees.append({
                    "name": a.get("name", ""),
                    "job_type": a.get("job_type", "-"),
                    "subcontractor_name": a.get("subcontractor_name", ""),
                    "signature_url": a.get("signature_url"),
                    "signed_at": a.get("signed_at_final") or a.get("signed_at"),
                    "sign_display": _attendee_sign_display(a),
                    "issue_flag": a.get("issue_flag"),
                    "issue_note": a.get("issue_note") or "",
                })
        except Exception as e:
            log.warning("attendees fetch 실패: %s", e)

        # 5. CORR-E: risk_items countermeasure 명시 — 임의 생성 금지
        raw_risk = m.get("risk_items") or []
        raw_safety = m.get("safety_items") or []
        risk_items = []
        for item in raw_risk:
            if isinstance(item, str):
                risk_items.append({"description": item, "countermeasure": None})
            elif isinstance(item, dict):
                risk_items.append(dict(item, countermeasure=item.get("countermeasure")))
            else:
                risk_items.append({"description": str(item), "countermeasure": None})
        safety_items = []
        for item in raw_safety:
            if isinstance(item, str):
                safety_items.append({"description": item})
            elif isinstance(item, dict):
                safety_items.append(item)

        # 6. CORR-B: work_time — meeting_date 의 HH:MM (created_at fallback 금지)
        work_time = ""
        md_raw = m.get("meeting_date")
        if md_raw:
            md_str = str(md_raw)
            time_part = md_str[11:16]
            if len(time_part) == 5 and ":" in time_part:
                work_time = time_part

        # 7. CORR-D: 참석인원 구분
        attendee_count_recorded = (
            m["attendee_count"] if m.get("attendee_count") is not None else len(attendees)
        )
        attendee_count_registered = len(attendees)
        attendee_count_mismatch = (
            m.get("attendee_count") is not None
            and m["attendee_count"] != attendee_count_registered
        )

        # 8. CORR-F: has_issue — 확인된 issue_flag 기준, 데이터 없으면 None
        known_flags = [a["issue_flag"] for a in attendees if a["issue_flag"] is not None]
        has_issue: Optional[bool] = bool(any(known_flags)) if known_flags else None

        return {
            "company_name": company.get("name", ""),
            "company_logo": company.get("logo_url"),
            "factory_name": factory.get("name", ""),
            "factory_address": factory.get("site_address", ""),
            "manager_name": factory.get("manager_name", ""),
            "work_date": str(m.get("work_date", "-")),
            "work_time": work_time,
            "work_location": m.get("work_location", "-"),
            "conductor_name": m.get("conductor_name", "-"),
            "work_description": m.get("work_description", "-"),
            "attendee_count": attendee_count_recorded,
            "attendee_count_recorded": attendee_count_recorded,
            "attendee_count_registered": attendee_count_registered,
            "attendee_count_mismatch": attendee_count_mismatch,
            "work_type": m.get("work_type") or "",
            "doc_id": _DOC_ID,
            "risk_items": risk_items,
            "safety_items": safety_items,
            "attendees": attendees,
            "conductor_signature": None,
            "has_issue": has_issue,
            "empty_rows": [],
        }
