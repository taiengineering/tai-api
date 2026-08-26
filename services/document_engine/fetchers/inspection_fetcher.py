"""점검 기록 공통 Fetcher — INSP·CHK·EQUIP·PPE 공통

점검 1건(inspection_id)의 현재 유효 데이터를 가져와 문서 템플릿 변수로 조립한다.

OBJ-01 KNOT-2 read cutover:
  점검 헤더/결과의 source 는 base ledger 직독(safety_inspections /
  safety_inspection_results)이 아니라 Effective Record Resolver
  (fn_resolve_inspection_record)이다. 비활성 점검은 발행 실패로 처리하고,
  결과는 is_active=true 만 소비하며, result_code 는 effective canonical
  (NORMAL/ABNORMAL/HOLD)을 그대로 쓴다(재해석 금지). status_code 는 앱/문서
  구버전 호환용 별칭으로만 유도한다.

단건형: 발행 단위 = 점검 1건. params={'inspection_id': ...}.

스키마 정합(2026-08-22 실측):
  equipment_assets = asset_name, asset_code, location_type, location_detail, factory_id ...
  factories        = name, site_address, manager_name, company_id
  companies        = name, logo_url, representative_name

희박 데이터/스키마 드리프트에 견디도록 asset/factory/company/inspector 조회를 try/except 로 방어한다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from db.supabase_client import get_supabase
from services.document_engine.fetchers.base_fetcher import BaseFetcher
from services.inspection_record_resolver import (
    InspectionRecordError,
    resolve_inspection_record,
)

log = logging.getLogger(__name__)

# result_summary(effective overall_result) → legacy status_code 별칭.
# result_summary 가 None 이면 inspection_status 를 status_code 로 쓴다.
_STATUS_ALIAS = {"NORMAL": "COMPLETED", "ABNORMAL": "ISSUE", "HOLD": "HOLD"}


class InspectionFetcher(BaseFetcher):
    """안전점검·설비점검·보호구 공통 데이터 패처 (단건)."""

    async def fetch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        inspection_id = params.get("inspection_id")
        if not inspection_id:
            raise ValueError("inspection_id 가 필요합니다.")
        sb = get_supabase()

        # 1) 현재 유효 점검 레코드 (base 직독 대신 Effective Record Resolver)
        try:
            record = resolve_inspection_record(inspection_id, sb)
        except InspectionRecordError as e:
            raise ValueError(f"점검 기록을 찾을 수 없습니다: {inspection_id} ({e.code})")
        if record.get("is_active") is False:
            raise ValueError(f"점검 기록이 비활성 상태입니다: {inspection_id}")

        inspection_status = record.get("inspection_status")
        result_summary = record.get("overall_result")
        if result_summary is None:
            status_code = inspection_status
        else:
            status_code = _STATUS_ALIAS.get(result_summary, result_summary)

        # 2) 대상 설비 + factory_id (asset 경유)
        asset: Dict[str, Any] = {}
        factory_id = None
        asset_id = record.get("asset_id")
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
        iid = record.get("inspector_id")
        if iid:
            try:
                u = sb.table("users").select("name").eq("id", iid).limit(1).execute()
                if u.data:
                    inspector_name = u.data[0].get("name", "")
            except Exception as e:
                log.warning("inspector fetch 실패: %s", e)

        # 5) 점검 결과 (effective ACTIVE results only — 재해석 없이 canonical code 사용)
        raw_results = record.get("results") or []
        active = [e for e in raw_results if e.get("is_active") is True]
        active.sort(key=lambda e: (e.get("created_at") is None, e.get("created_at") or "", str(e.get("result_id"))))
        items = [
            {
                "id": e.get("result_id"),
                "item_name": e.get("item_name"),
                "result_code": e.get("result_code"),  # effective canonical (NORMAL/ABNORMAL/HOLD)
                "note": e.get("note"),
                "photo_urls": e.get("photo_urls"),
                "value_text": e.get("value_text"),
                "value_number": e.get("value_number"),
            }
            for e in active
        ]

        def _rc(i: dict) -> str:
            return (i.get("result_code") or "").upper()

        normal_count = sum(1 for i in items if _rc(i) == "NORMAL")
        issue_count = sum(1 for i in items if _rc(i) == "ABNORMAL")  # canonical ABNORMAL (legacy "ISSUE" 비교 제거)
        hold_count = sum(1 for i in items if _rc(i) == "HOLD")
        issue_items = [
            {
                "no": idx + 1,
                "item_name": i.get("item_name", ""),
                "note": i.get("note", ""),
                "photo_urls": i.get("photo_urls") or [],
            }
            for idx, i in enumerate(items) if _rc(i) == "ABNORMAL"
        ]

        location = asset.get("location_detail") or asset.get("location_type") or ""

        return {
            "company_name": company.get("name", ""),
            "company_logo": company.get("logo_url"),
            "factory_name": factory.get("name", ""),
            "factory_address": factory.get("site_address", ""),
            "manager_name": factory.get("manager_name", ""),
            "doc_title": asset.get("asset_name") or "점검 기록",
            "inspection_date": record.get("inspection_date") or "",
            "inspector_name": inspector_name,
            "status_code": status_code,
            "inspection_status": inspection_status,
            "result_summary": result_summary,
            "asset_name": asset.get("asset_name", ""),
            "asset_code": asset.get("asset_code", ""),
            "asset_location": location,
            "items": items,
            "total_count": len(items),
            "normal_count": normal_count,
            "issue_count": issue_count,
            "abnormal_count": issue_count,  # canonical alias of issue_count
            "hold_count": hold_count,
            "issue_items": issue_items,
            "has_issue": issue_count > 0,
        }
