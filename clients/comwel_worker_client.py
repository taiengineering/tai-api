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


_SIDO_REPLACEMENTS = (
    ("서울특별시", "서울"),
    ("부산광역시", "부산"),
    ("대구광역시", "대구"),
    ("인천광역시", "인천"),
    ("광주광역시", "광주"),
    ("대전광역시", "대전"),
    ("울산광역시", "울산"),
    ("세종특별자치시", "세종"),
    ("경기도", "경기"),
    ("강원특별자치도", "강원"),
    ("강원도", "강원"),
    ("충청북도", "충북"),
    ("충청남도", "충남"),
    ("전북특별자치도", "전북"),
    ("전라북도", "전북"),
    ("전라남도", "전남"),
    ("경상북도", "경북"),
    ("경상남도", "경남"),
    ("제주특별자치도", "제주"),
    ("제주도", "제주"),
)
_METRO_ADMIN = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"}


def normalize_address(addr: Any) -> str:
    """공백 압축 · 명백한 시도 축약 · 괄호(동명) 제거 · 특수문자 제거 후 토큰 문자열."""
    if addr is None:
        return ""
    s = str(addr).strip()
    if not s:
        return ""
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"（[^）]*）", " ", s)
    for long, short in _SIDO_REPLACEMENTS:
        s = s.replace(long, short)
    s = re.sub(r"[^0-9A-Za-z가-힣]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(addr: Any) -> List[str]:
    n = normalize_address(addr)
    return n.split() if n else []


def _admin_keys(tokens: List[str]) -> set:
    keys = set()
    for t in tokens:
        if t in _METRO_ADMIN:
            keys.add(t)
        if t.endswith(("시", "군", "구")) and len(t) >= 2:
            keys.add(t)
            keys.add(t[:-1])
    return keys


def _suffix_set(tokens: List[str], suffixes: tuple) -> set:
    return {t for t in tokens if t.endswith(suffixes) and len(t) >= 2}


def address_match(user_addr: Any, record_addr: Any) -> bool:
    """시군구 + 도로명(또는 동) 핵심 토큰이 명확히 일치할 때만 True. 애매하면 False."""
    ut = _tokens(user_addr)
    rt = _tokens(record_addr)
    if not ut or not rt:
        return False
    u_admin, r_admin = _admin_keys(ut), _admin_keys(rt)
    if not u_admin or not r_admin or u_admin.isdisjoint(r_admin):
        return False
    u_road, r_road = _suffix_set(ut, ("로", "길")), _suffix_set(rt, ("로", "길"))
    u_dong, r_dong = _suffix_set(ut, ("동", "읍", "면", "리")), _suffix_set(rt, ("동", "읍", "면", "리"))
    road_ok = bool(u_road and r_road and not u_road.isdisjoint(r_road))
    dong_ok = bool(u_dong and r_dong and not u_dong.isdisjoint(r_dong))
    if u_road or u_dong:
        return road_ok or dong_ok
    return False


def filter_by_address(records: List[Dict[str, Any]], expected_address: Any) -> List[Dict[str, Any]]:
    if not (expected_address or "").strip():
        return []
    return [r for r in records if address_match(expected_address, r.get("addr"))]


def select_latest(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """계속(saeopFg=1) 우선 → seongripDt 최신 1건. 계속 없으면 전체 최신 + is_blanket.
    호출자는 주소 매칭된 subset 만 넘겨야 한다.
    """
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
        "matched_address": picked.get("addr") or None,
        "source": SOURCE,
    }


def pick_reference(records: List[Dict[str, Any]], expected_address: Any) -> Optional[Dict[str, Any]]:
    """주소 필터 후 select_latest. 주소 없거나 매칭 0건 → None. 전체 records에서 계속 우선 선택 금지."""
    matched = filter_by_address(records, expected_address)
    if not matched:
        return None
    return select_latest(matched)


def _service_key() -> str:
    return (os.environ.get("DATA_GO_KR_SERVICE_KEY") or "").strip()


def normalize_business_number(raw: Any) -> Optional[str]:
    digits = re.sub(r"[^0-9]", "", str(raw or ""))
    return digits if len(digits) == 10 else None


def get_worker_reference(
    business_number: str,
    expected_address: Optional[str] = None,
    boheom_fg: int = 1,
    timeout: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """httpx GET, retry 0. 키 없으면 None. timeout/5xx/네트워크 → ComwelApiError.
    expected_address 없거나 매칭 0건 → None (사업자번호만으로 선택 금지).
    """
    if not (expected_address or "").strip():
        return None
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
    return pick_reference(records, expected_address)
