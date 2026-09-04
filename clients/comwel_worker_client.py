"""근로복지공단 상시인원 조회 클라이언트.

ENDPOINT: gySjbPstateInfoService/getGySjBoheomBsshItem
serviceKey = env DATA_GO_KR_SERVICE_KEY (하드코딩 금지). retry 0.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx

from utils.logger import get_logger

log = get_logger(__name__)

ENDPOINT = "https://apis.data.go.kr/B490001/gySjbPstateInfoService/getGySjBoheomBsshItem"
SOURCE = "근로복지공단"
_SAEOP_FG_CONTINUE = "1"
_COUNT_FIELD = "sangsiInwonCnt"
_DATE_FIELD = "seongripDt"


class ComwelApiError(RuntimeError):
    pass


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _child_text(el: ET.Element, name: str) -> str:
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _parse_count(raw: str) -> Optional[int]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        n = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None
    return n


def parse_items(xml_text: str) -> List[Dict[str, Any]]:
    """items/item[] → records. sangsiInwonCnt<=0 또는 파싱불가 제외."""
    root = ET.fromstring(xml_text)
    result_code = None
    items_parent = None
    for el in root.iter():
        loc = _local(el.tag)
        if loc == "resultCode":
            result_code = (el.text or "").strip()
        if loc == "items":
            items_parent = el
    if result_code is not None and result_code != "00":
        raise ComwelApiError("resultCode={}".format(result_code))
    if items_parent is None:
        return []
    out: List[Dict[str, Any]] = []
    for item in items_parent:
        if _local(item.tag) != "item":
            continue
        cnt = _parse_count(_child_text(item, _COUNT_FIELD))
        if cnt is None or cnt <= 0:
            continue
        out.append({
            "sangsiInwonCnt": cnt,
            "seongripDt": _child_text(item, _DATE_FIELD),
            "saeopFg": _child_text(item, "saeopFg"),
            "saeopjangNm": _child_text(item, "saeopjangNm"),
            "addr": _child_text(item, "addr"),
            "opaBoheomFg": _child_text(item, "opaBoheomFg"),
        })
    return out


def select_latest(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """계속(saeopFg=1) 우선 → seongripDt 최신 1건. 계속 없으면 전체 최신 + is_blanket."""
    if not records:
        return None
    cont = [r for r in records if str(r.get("saeopFg") or "") == _SAEOP_FG_CONTINUE]
    is_blanket = not bool(cont)
    pool = cont if cont else list(records)
    pool.sort(key=lambda r: r.get("seongripDt") or "", reverse=True)
    picked = pool[0]
    return {
        "external_reference_count": picked["sangsiInwonCnt"],
        "reference_date": picked.get("seongripDt") or None,
        "saeop_fg": picked.get("saeopFg") or None,
        "is_blanket": is_blanket,
        "saeopjang_nm": picked.get("saeopjangNm") or None,
        "source": SOURCE,
    }


def _service_key() -> str:
    return (os.environ.get("DATA_GO_KR_SERVICE_KEY") or "").strip()


def normalize_business_number(raw: Any) -> Optional[str]:
    digits = re.sub(r"[^0-9]", "", str(raw or ""))
    return digits if len(digits) == 10 else None


def get_worker_reference(
    business_number: str,
    boheom_fg: int = 1,
    timeout: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """httpx GET, retry 0. 키 없으면 None. timeout/5xx/네트워크 → ComwelApiError."""
    key = _service_key()
    if not key:
        return None
    bn = normalize_business_number(business_number)
    if not bn:
        return None
    params = {
        "serviceKey": key,
        "v_saeopjaDrno": bn,
        "BoheomFg": str(boheom_fg),
        "pageNo": "1",
        "numOfRows": "100",
    }
    req_kw: Dict[str, Any] = {"params": params, "timeout": timeout}
    try:
        from services.kr_public_api import httpx_proxy
        proxy = httpx_proxy()
        if proxy:
            req_kw["proxy"] = proxy
    except Exception:
        pass
    try:
        resp = httpx.get(ENDPOINT, **req_kw)
    except httpx.TimeoutException as e:
        raise ComwelApiError("timeout: {}".format(e)) from e
    except httpx.RequestError as e:
        raise ComwelApiError("network: {}".format(e)) from e
    if resp.status_code >= 500:
        raise ComwelApiError("HTTP {}".format(resp.status_code))
    if resp.status_code != 200:
        raise ComwelApiError("HTTP {}".format(resp.status_code))
    try:
        records = parse_items(resp.text)
    except ComwelApiError:
        raise
    except Exception as e:
        raise ComwelApiError("xml parse: {}".format(e)) from e
    return select_latest(records)
