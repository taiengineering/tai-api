"""통합 공지 배너 서비스 (WO-16 NoticeBanner).

Goal: G-ms4je4z3-33eada
- marketing(taieng.co.kr)·safe(safe.taieng.co.kr) 두 채널 공지 통합 관리.
- 채널 타깃은 ARRAY(channels text[]) — 한 공지를 한쪽/양쪽 노출.
- 공개 조회: 채널 포함 + enabled + 노출기간 내. priority desc.
- notice_banner(RLS off).
- 2026-08-13 공지 유형(category) 추가: NEW·IMPROVE·SAFETY·NOTICE. 게시판형 분류·필터용.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

CHANNELS = ("MARKETING", "SAFE")
BANNER_TYPES = ("INFO", "WARNING", "MAINTENANCE", "EVENT")
CATEGORIES = ("NEW", "IMPROVE", "SAFETY", "NOTICE")


class NoticeError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_admin(channel: Optional[str] = None, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
    """어드민 목록(필터)."""
    q = get_supabase().table("notice_banner").select("*")
    if channel:
        q = q.contains("channels", [channel])
    if enabled is not None:
        q = q.eq("enabled", enabled)
    res = q.order("priority", desc=True).order("created_at", desc=True).execute()
    return res.data or []


def create(data: Dict[str, Any]) -> Dict[str, Any]:
    channels = data.get("channels") or list(CHANNELS)
    for ch in channels:
        if ch not in CHANNELS:
            raise NoticeError(400, f"지원하지 않는 채널: {ch}")
    if data.get("banner_type") and data["banner_type"] not in BANNER_TYPES:
        raise NoticeError(400, f"지원하지 않는 배너 유형: {data['banner_type']}")
    if data.get("category") and data["category"] not in CATEGORIES:
        raise NoticeError(400, f"지원하지 않는 공지 유형: {data['category']}")
    row = {
        "title": data["title"],
        "body": data.get("body"),
        "channels": channels,
        "banner_type": data.get("banner_type", "INFO"),
        "category": data.get("category", "NOTICE"),
        "link_url": data.get("link_url"),
        "link_label": data.get("link_label"),
        "starts_at": data.get("starts_at"),
        "ends_at": data.get("ends_at"),
        "priority": data.get("priority", 0),
        "enabled": data.get("enabled", True),
        "created_by": data.get("created_by"),
    }
    res = get_supabase().table("notice_banner").insert(row).execute()
    return res.data[0] if res.data else {}


def update(notice_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    patch = {k: v for k, v in data.items() if v is not None and k in (
        "title", "body", "channels", "banner_type", "category", "link_url", "link_label",
        "starts_at", "ends_at", "priority", "enabled")}
    if "channels" in patch:
        for ch in patch["channels"]:
            if ch not in CHANNELS:
                raise NoticeError(400, f"지원하지 않는 채널: {ch}")
    if "category" in patch and patch["category"] not in CATEGORIES:
        raise NoticeError(400, f"지원하지 않는 공지 유형: {patch['category']}")
    patch["updated_at"] = _now_iso()
    res = get_supabase().table("notice_banner").update(patch).eq("id", notice_id).execute()
    if not res.data:
        raise NoticeError(404, "공지를 찾을 수 없습니다.")
    return res.data[0]


def toggle(notice_id: str, enabled: bool) -> Dict[str, Any]:
    res = get_supabase().table("notice_banner").update(
        {"enabled": enabled, "updated_at": _now_iso()}
    ).eq("id", notice_id).execute()
    if not res.data:
        raise NoticeError(404, "공지를 찾을 수 없습니다.")
    return res.data[0]


def delete(notice_id: str) -> None:
    get_supabase().table("notice_banner").delete().eq("id", notice_id).execute()


def active_for_channel(channel: str) -> List[Dict[str, Any]]:
    """공개용: 채널 현재 노출 공지(enabled + 기간 내). priority desc."""
    if channel not in CHANNELS:
        raise NoticeError(400, f"지원하지 않는 채널: {channel}")
    now = _now_iso()
    # 채널 포함 + enabled
    rows = (
        get_supabase().table("notice_banner").select("*")
        .contains("channels", [channel]).eq("enabled", True)
        .order("priority", desc=True).execute().data or []
    )
    # 노출기간 필터(파이썬 — null 허용: starts_at 없으면 이미 시작, ends_at 없으면 무기한)
    out = []
    for r in rows:
        starts = r.get("starts_at")
        ends = r.get("ends_at")
        if starts and starts > now:
            continue
        if ends and ends < now:
            continue
        out.append(r)
    return out
