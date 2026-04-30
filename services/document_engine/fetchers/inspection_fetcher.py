"""점검 기록 공통 Fetcher — 카테고리 2+5 (22건) 통합

safety_inspections + safety_inspection_results 에서
점검 기록 데이터를 가져와 문서 템플릿에 전달.

22건이 전부 동일한 DB 구조를 사용하므로
fetcher 1개로 22건 문서를 모두 커버.
차이점은 inspection_set의 점검 항목 구성뿐.
"""
from __future__ import annotations

import logging
from typing import Any

from db.supabase_client import get_supabase
from services.document_engine.fetchers.base_fetcher import BaseFetcher

log = logging.getLogger(__name__)


class InspectionFetcher(BaseFetcher):
    """안전점검·설비점검 공통 데이터 패처."""

    async def fetch(self, params: dict) -> dict[str, Any]:
        """
        params:
            inspection_id: str  — safety_inspections.id
        """
        inspection_id = params["inspection_id"]
        sb = get_supabase()

        # 1) 점검 기본 정보
        insp = (
            sb.table("safety_inspections")
            .select(
                "id, factory_id, asset_id, inspection_date, inspector_id, "
                "status_code, note, inspection_set_id, created_at, completed_at"
            )
            .eq("id", inspection_id)
            .limit(1)
            .execute()
        )
        if not insp.data:
            raise ValueError(f"점검 기록을 찾을 수 없습니다: {inspection_id}")
        inspection = insp.data[0]

        # 2) 회사·시설 정보
        factory_id = inspection["factory_id"]
        fac = (
            sb.table("factories")
            .select("name, site_address, company_id")
            .eq("id", factory_id)
            .limit(1)
            .execute()
        )
        factory = fac.data[0] if fac.data else {}
        company_id = factory.get("company_id")

        comp = (
            sb.table("companies")
            .select("name, logo_url, representative_name")
            .eq("id", company_id)
            .limit(1)
            .execute()
        ) if company_id else None
        company = comp.data[0] if comp and comp.data else {}

        # 3) 점검자 정보
        inspector_id = inspection.get("inspector_id")
        inspector_name = ""
        if inspector_id:
            usr = (
                sb.table("users")
                .select("name")
                .eq("id", inspector_id)
                .limit(1)
                .execute()
            )
            if usr.data:
                inspector_name = usr.data[0].get("name", "")

        # 4) 점검세트 정보 (문서 제목용)
        set_id = inspection.get("inspection_set_id")
        set_name = ""
        if set_id:
            s = (
                sb.table("inspection_sets")
                .select("name")
                .eq("id", set_id)
                .limit(1)
                .execute()
            )
            if s.data:
                set_name = s.data[0].get("name", "")

        # 5) 점검 대상 설비
        asset_id = inspection.get("asset_id")
        asset_name = ""
        asset_location = ""
        if asset_id:
            a = (
                sb.table("equipment_assets")
                .select("name, location, asset_code")
                .eq("id", asset_id)
                .limit(1)
                .execute()
            )
            if a.data:
                asset_name = a.data[0].get("name", "")
                asset_location = a.data[0].get("location", "")

        # 6) 점검 결과 (항목별)
        results = (
            sb.table("safety_inspection_results")
            .select(
                "id, item_name, result_code, note, photo_urls, "
                "inspection_set_item_id"
            )
            .eq("inspection_id", inspection_id)
            .order("created_at")
            .execute()
        )

        # 결과를 정상/이상/보류로 분류
        items = results.data or []
        normal_count = sum(1 for i in items if i.get("result_code") == "NORMAL")
        issue_count = sum(1 for i in items if i.get("result_code") == "ISSUE")
        hold_count = sum(1 for i in items if i.get("result_code") == "HOLD")

        # 이상 항목만 별도 추출
        issue_items = [
            {
                "no": idx + 1,
                "item_name": i.get("item_name", ""),
                "note": i.get("note", ""),
                "photo_urls": i.get("photo_urls", []),
            }
            for idx, i in enumerate(items)
            if i.get("result_code") == "ISSUE"
        ]

        # 7) 데이터 조립
        return {
            # 회사·시설
            "company_name": company.get("name", ""),
            "company_logo": company.get("logo_url"),
            "factory_name": factory.get("name", ""),
            "factory_address": factory.get("site_address", ""),

            # 문서 정보
            "doc_title": set_name or "점검 기록",
            "inspection_date": inspection.get("inspection_date", ""),
            "inspector_name": inspector_name,
            "status_code": inspection.get("status_code", ""),

            # 설비 정보
            "asset_name": asset_name,
            "asset_location": asset_location,

            # 점검 결과
            "items": items,
            "total_count": len(items),
            "normal_count": normal_count,
            "issue_count": issue_count,
            "hold_count": hold_count,
            "issue_items": issue_items,
            "has_issue": issue_count > 0,

            # 메모
            "inspection_note": inspection.get("note", ""),
        }
