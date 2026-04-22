# routers/law_collector_admrul.py
# 행정규칙(NFTC/NFPC 등) 수집용 헬퍼
# 기존 law_collector.py의 law API 호출을 admrul API로 전환
#
# 법제처 행정규칙 API:
#   검색: http://www.law.go.kr/DRF/lawSearch.do?target=admrul
#   본문: http://www.law.go.kr/DRF/lawService.do?target=admrul&ID=...
#
# NFTC/NFPC 등 소방청/국립소방연구원 고시는 "법령"이 아닌 "행정규칙"으로 분류됨.

import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional

from routers.law_collector import (
    DEFAULT_HEADERS,
    DATA_GOV_KEY,
    DATA_GOV_BASE,
    LAW_API_OC,
    LAW_API_BASE,
    clean_cdata,
    parse_date,
    _iter_jo_units,
    _parse_article_from_jo,
    _dedupe_articles_by_internal_key,
)


# ============================================================
# 행정규칙 검색/본문 API (law.go.kr target=admrul)
# ============================================================

def fetch_admrul_list(query: str, display: int = 20, page: int = 1) -> dict:
    """
    행정규칙 목록 검색.
    data.go.kr에는 admrul용 별도 엔드포인트가 있을 수 있지만,
    우선 law.go.kr target=admrul 사용 (OC=taieng 등록 IP 필요).
    """
    url = f"{LAW_API_BASE}/lawSearch.do"
    params = {
        "OC": LAW_API_OC,
        "target": "admrul",
        "type": "XML",
        "query": query,
        "display": display,
        "page": page,
    }
    resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return {
        "xml": resp.text,
        "status": resp.status_code,
        "ok": resp.ok,
        "source": "law.go.kr/admrul",
    }


def fetch_admrul_content(admrul_id: str) -> dict:
    """
    행정규칙 본문 조회.
    
    Args:
        admrul_id: 행정규칙일련번호 또는 ID (law_api_id에 저장된 값)
    """
    url = f"{LAW_API_BASE}/lawService.do"
    params = {
        "OC": LAW_API_OC,
        "target": "admrul",
        "type": "XML",
        "ID": admrul_id,
    }
    resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=60)
    resp.encoding = "utf-8"
    return {
        "xml": resp.text,
        "status": resp.status_code,
        "ok": resp.ok,
        "source": "law.go.kr/admrul",
    }


# ============================================================
# 행정규칙 XML 파싱
# ============================================================

def parse_admrul_list_xml(xml_text: str) -> list:
    """행정규칙 검색 결과 XML 파싱."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    
    rules = []
    # <AdmRulSearch><행정규칙> 구조
    for rul in root.findall(".//행정규칙") + root.findall(".//admrul"):
        rules.append({
            "law_mst_no":        rul.findtext("행정규칙일련번호", "") or rul.findtext("행정규칙ID", ""),
            "law_api_id":        rul.findtext("행정규칙ID", "") or rul.findtext("행정규칙일련번호", ""),
            "law_name":          clean_cdata(rul.findtext("행정규칙명", "")),
            "law_name_short":    "",
            "law_type_name":     rul.findtext("행정규칙종류", ""),
            "ministry_code":     rul.findtext("소관부처코드", ""),
            "ministry_name":     rul.findtext("소관부처명", ""),
            "law_number":        rul.findtext("발령번호", ""),
            "announcement_date": parse_date(rul.findtext("발령일자", "")),
            "enforcement_date":  parse_date(rul.findtext("시행일자", "")),
            "revision_type":     rul.findtext("제개정구분", ""),
            "current_status":    rul.findtext("현행연혁코드", ""),
        })
    return rules


def parse_admrul_content_xml(xml_text: str) -> dict:
    """행정규칙 본문 XML 파싱. law API와 구조 유사하나 태그명 일부 다름."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"행정규칙 XML 파싱 실패: {e}")
    
    basic = root.find("행정규칙기본정보") or root.find("기본정보")
    info = {}
    if basic is not None:
        info = {
            "law_api_id":        basic.findtext("행정규칙ID", "") or basic.findtext("법령ID", ""),
            "announcement_date": parse_date(
                basic.findtext("발령일자", "") or basic.findtext("공포일자", "")
            ),
            "law_number":        basic.findtext("발령번호", "") or basic.findtext("공포번호", ""),
            "law_name":          clean_cdata(
                basic.findtext("행정규칙명", "") or basic.findtext("법령명_한글", "")
            ),
            "law_type_name":     basic.findtext("행정규칙종류", "") or basic.findtext("법종구분", ""),
            "ministry_code":     basic.findtext("소관부처코드", ""),
            "ministry_name":     basic.findtext("소관부처명", "") or basic.findtext("소관부처", ""),
            "enforcement_date":  parse_date(basic.findtext("시행일자", "")),
            "revision_type":     basic.findtext("제개정구분", ""),
        }
    
    # 행정규칙도 law와 동일한 조문단위 구조 사용
    # <조문><조문단위> 또는 <조문단위>
    raw_articles = [_parse_article_from_jo(jo) for jo in _iter_jo_units(root)]
    articles = _dedupe_articles_by_internal_key(raw_articles)
    for art in articles:
        ik = art.get("article_internal_key") or ""
        if ik.startswith("__noid_"):
            art["article_internal_key"] = ""
    
    return {"info": info, "articles": articles, "raw_xml": xml_text}


# ============================================================
# 디버그/테스트
# ============================================================

def debug_admrul_api(query: str) -> dict:
    """행정규칙 API가 정상 동작하는지 확인."""
    result = fetch_admrul_list(query=query, display=5)
    if not result["ok"]:
        return {"ok": False, "status": result["status"], "source": result["source"]}
    
    rules = parse_admrul_list_xml(result["xml"])
    return {
        "ok": True,
        "source": result["source"],
        "count": len(rules),
        "samples": [
            {
                "name": r["law_name"],
                "id": r["law_api_id"],
                "mst": r["law_mst_no"],
                "ministry": r["ministry_name"],
            }
            for r in rules[:3]
        ],
    }
