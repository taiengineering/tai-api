"""점검 기록 공통 Fetcher — INSP·CHK·EQUIP·PPE 공통

safety_inspections + safety_inspection_results 에서 점검 1건(inspection_id)의
데이터를 가져와 문서 템플릿 변수로 조립한다.

단건형: 발행 단위 = 점검 1건. params={'inspection_id': ...}.

스키마 정합(2026-08-22 실측):
  safety_inspections = id, assignment_id, asset_id, inspector_id, inspection_date, status_code
    (factory_id 없음 → asset_id → equipment_assets.factory_id 경유)
  equipment_assets   = asset_name, asset_code, location_type, location_detail, factory_id ...
  safety_inspection_results = item_name, result_code, note, photo_urls, value_text, value_number, created_at

희박 데이터/스키마 드리프트에 견디도록 각 조회를 try/except 로 방어한다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from db.supabase_client import get_supabase
from services.document_engine.fetchers.base_fetcher import BaseFetcher

log = logging.getLogger(__name__)


class InspectionFetcher(BaseFetcher):
    """안전점검·설비점검·보호구 공통 데이터 패처 (단건)."""

    async def fetch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        inspection_id = params.get("inspection_id")
        if not inspection_id:
            raise ValueError("inspection_id 가 필요합니다.")
        sb = get_supabase()

        # 1) 점검 기본 (실제 존재 컬럼만)
        insp_res = (
            sb.table("safety_inspections")
            .select("id, assignment_id, asset_id, inspector_id, inspection_date, status_code")
            .eq("id", inspection_id).limit(1).execute()
        )
        if not insp_res.data:
            raise ValueError(f"점검 기록을 찾을 수 없습니다: {inspection_id}")
        insp = insp_res.data[0]

        # 2) 대상 설비 + factory_id (asset 경유)
        asset: Dict[str, Any] = {}
        factory_id = None
        asset_id = insp.get("asset_id")
        if asset_id:
            try:
                a = (
                    sb.table("equipment_assets")
                    .select("asset_name, asset_code, location_type, location_detail, factory_id")
                    .eq("id", asset_id).limit(1).execute()
                )
                if a.data:
                    asset = a.data[0]
                    factory_id = asset.get("factory_id")
            except Exception as e:
                log.warning("asset fetch 실패: %s", e)

        # 3) 사업장 + 회사
        factory: Dict[str, Any] = {}
        company: Dict[str, Any] = {}
        if factory_id:
            try:
                f = (
                    sb.table("factories")
                    .select("name, site_address, manager_name, company_id")
                    .eq("id", factory_id).limit(1).execute()
                )
                factory = f.data[0] if f.data else {}
            except Exception as e:
                log.warning("factory fetch 실패: %s", e)
            cid = factory.get("company_id")
            if cid:
                try:
                    c = (
                        sb.table("companies")
                        .select("name, logo_url, representative_name")
                        .eq("id", cid).limit(1).execute()
                    )
                    company = c.data[0] if c.data else {}
                except Exception as e:
                    log.warning("company fetch 실패: %s", e)

        # 4) 점검자
        inspector_name = ""
        iid = insp.get("inspector_id")
        if iid:
            try:
                u = sb.table("users").select("name").eq("id", iid).limit(1).execute()
                if u.data:
                    inspector_name = u.data[0].get("name", "")
            except Exception as e:
                log.warning("inspector fetch 실패: %s", e)

        # 5) 점검 결과 (항목별)
        items = []
        try:
            r = (
                sb.table("safety_inspection_results")
                .select("id, item_name, result_code, note, photo_urls, value_text, value_number")
                .eq("inspection_id", inspection_id).order("created_at").execute()
            )
            items = r.data or []
        except Exception as e:
            log.warning("results fetch 실패: %s", e)

        def _rc(i: dict) -> str:
            return (i.get("result_code") or "").upper()

        normal_count = sum(1 for i in items if _rc(i) == "NORMAL")
        issue_count = sum(1 for i in items if _rc(i) == "ISSUE")
        hold_count = sum(1 for i in items if _rc(i) == "HOLD")
        issue_items = [
            {
                "no": idx + 1,
                "item_name": i.get("item_name", ""),
                "note": i.get("note", ""),
                "photo_urls": i.get("photo_urls") or [],
            }
            for idx, i in enumerate(items) if _rc(i) == "ISSUE"
        ]

        location = asset.get("location_detail") or asset.get("location_type") or ""

        return {
            "company_name": company.get("name", ""),
            "company_logo": company.get("logo_url"),
            "factory_name": factory.get("name", ""),
            "factory_address": factory.get("site_address", ""),
            "manager_name": factory.get("manager_name", ""),
            "doc_title": asset.get("asset_name") or "점검 기록",
            "inspection_date": insp.get("inspection_date", ""),
            "inspector_name": inspector_name,
            "status_code": insp.get("status_code", ""),
            "asset_name": asset.get("asset_name", ""),
            "asset_code": asset.get("asset_code", ""),
            "asset_location": location,
            "items": items,
            "total_count": len(items),
            "normal_count": normal_count,
            "issue_count": issue_count,
            "hold_count": hold_count,
            "issue_items": issue_items,
            "has_issue": issue_count > 0,
        }
