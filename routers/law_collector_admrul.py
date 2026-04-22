# routers/law_collector_admrul.py v1.4
# 행정규칙(NFTC/NFPC 등) 수집용 헬퍼
#
# 법제처 행정규칙 API:
#   검색: http://www.law.go.kr/DRF/lawSearch.do?target=admrul
#   본문: http://www.law.go.kr/DRF/lawService.do?target=admrul&LID={행정규칙ID}
#
# ⚠️ 행정규칙 XML 구조는 다양함:
#   패턴 A (NFTC/NFPC):    <조문내용>에 "1./1.1/1.1.1" 계층 번호 텍스트 통째
#   패턴 B (전기설비기준): <조문내용>에 "제1장 총칙"만 있고
#                         본문은 <제YYYY-NN호,날짜> 등 개정이력 태그에 분산
#
# v1.4 (2026-04-23): 조문내용이 50자 미만이면 itertext() 폴백 강제 발동
#                    → 전기설비기술기준, 한국전기설비규정 등 특수 구조 대응
# v1.3: article_internal_key에 순차 idx 포함
# v1.2: 가상 조문 전략 도입
# v1.1: LID 파라미터 수정

import re
import requests
import xml.etree.ElementTree as ET
from typing import List

from routers.law_collector import (
    DEFAULT_HEADERS,
    LAW_API_OC,
    LAW_API_BASE,
    clean_cdata,
    parse_date,
)


# ============================================================
# 행정규칙 검색/본문 API
# ============================================================

def fetch_admrul_list(query: str, display: int = 20, page: int = 1) -> dict:
    """행정규칙 목록 검색. OC=taieng 등록 IP 필요."""
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
    ⚠️ 파라미터는 "LID" (ID 아님!)
    """
    url = f"{LAW_API_BASE}/lawService.do"
    params = {
        "OC": LAW_API_OC,
        "target": "admrul",
        "type": "XML",
        "LID": admrul_id,
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
# 행정규칙 검색 결과 XML 파싱
# ============================================================

def parse_admrul_list_xml(xml_text: str) -> list:
    """행정규칙 검색 결과 XML 파싱."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    
    rules = []
    for rul in root.findall(".//admrul") + root.findall(".//행정규칙"):
        admrul_id_short = rul.findtext("행정규칙ID", "")
        admrul_seq_long = rul.findtext("행정규칙일련번호", "")
        
        rules.append({
            "law_api_id":        admrul_id_short or admrul_seq_long,
            "law_mst_no":        admrul_seq_long or admrul_id_short,
            "law_name":          clean_cdata(rul.findtext("행정규칙명", "")),
            "law_name_short":    "",
            "law_type_name":     rul.findtext("행정규칙종류", ""),
            "ministry_code":     rul.findtext("소관부처코드", ""),
            "ministry_name":     rul.findtext("소관부처명", ""),
            "law_number":        rul.findtext("발령번호", ""),
            "announcement_date": parse_date(rul.findtext("발령일자", "")),
            "enforcement_date":  parse_date(rul.findtext("시행일자", "")),
            "revision_type":     rul.findtext("제개정구분명", ""),
            "current_status":    rul.findtext("현행연혁구분", ""),
        })
    return rules


# ============================================================
# 행정규칙 본문 XML 파싱 (v1.4: 강화된 폴백)
# ============================================================

# 본문 이외 메타데이터 태그 (폴백 시 제외)
_META_TAGS_EXCLUDE = {
    "행정규칙기본정보", "기본정보",
    "행정규칙ID", "행정규칙일련번호", "행정규칙명",
    "행정규칙종류", "행정규칙종류코드", "발령번호", "발령일자",
    "시행일자", "생성일자", "현행여부", "조문형식여부",
    "소관부처명", "소관부처코드", "상위부처명",
    "담당부서기관명", "담당부서기관코드", "담당자명", "전화번호",
    "제개정구분명", "제개정구분코드",
    "첨부파일", "첨부파일링크", "첨부파일명",
}


def _collect_full_text_fallback(root: ET.Element) -> str:
    """
    <조문내용>이 너무 짧을 때 사용하는 폴백.
    메타데이터 태그는 제외하고 나머지 전체 텍스트 수집.
    """
    texts: List[str] = []
    
    def _should_skip(elem: ET.Element) -> bool:
        """이 요소를 건너뛸지 결정."""
        return elem.tag in _META_TAGS_EXCLUDE
    
    def _walk(elem: ET.Element):
        if _should_skip(elem):
            return
        if elem.text and elem.text.strip():
            texts.append(elem.text.strip())
        for child in elem:
            _walk(child)
        if elem.tail and elem.tail.strip():
            texts.append(elem.tail.strip())
    
    # root의 직속 자식부터 순회 (root의 text는 보통 빈 줄)
    for child in root:
        _walk(child)
    
    return "\n".join(texts)


def parse_admrul_content_xml(xml_text: str) -> dict:
    """
    행정규칙 본문 XML 파싱.
    
    v1.4: <조문내용>이 50자 미만이면 폴백 강제 발동.
          전기설비기술기준 같이 본문이 <제YYYY-NN호> 태그에 분산된 경우 대응.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"행정규칙 XML 파싱 실패: {e}")
    
    if root.tag == "Law" and (root.text or "").strip().startswith("일치하는"):
        raise RuntimeError(f"행정규칙 본문 API: {root.text.strip()}")
    
    basic = root.find("행정규칙기본정보") or root.find("기본정보")
    info = {}
    if basic is not None:
        info = {
            "law_api_id":        (
                basic.findtext("행정규칙ID", "")
                or basic.findtext("행정규칙일련번호", "")
            ),
            "announcement_date": parse_date(
                basic.findtext("발령일자", "")
                or basic.findtext("공포일자", "")
            ),
            "law_number":        (
                basic.findtext("발령번호", "")
                or basic.findtext("공포번호", "")
            ),
            "law_name":          clean_cdata(
                basic.findtext("행정규칙명", "")
                or basic.findtext("법령명_한글", "")
            ),
            "law_type_name":     (
                basic.findtext("행정규칙종류", "")
                or basic.findtext("법종구분", "")
            ),
            "ministry_code":     basic.findtext("소관부처코드", ""),
            "ministry_name":     (
                basic.findtext("소관부처명", "")
                or basic.findtext("소관부처", "")
            ),
            "enforcement_date":  parse_date(basic.findtext("시행일자", "")),
            "revision_type":     basic.findtext("제개정구분명", "") or basic.findtext("제개정구분", ""),
        }
    
    # ─── 본문 추출 (v1.4 강화) ─────────────────────────────
    # 1차: <조문내용> 시도
    content_text = (root.findtext("조문내용", "") or "").strip()
    
    # 2차: <조문내용>이 너무 짧으면 폴백
    # NFTC 102 = 16663자 정상 / 전기설비기술기준 = "제1장 총칙" 7자 이상 현상
    MIN_CONTENT_LENGTH = 50
    
    if len(content_text) < MIN_CONTENT_LENGTH:
        # 폴백: 메타데이터 제외한 전체 텍스트 수집
        content_text = _collect_full_text_fallback(root)
    
    full_text = content_text.strip()
    
    # ─── 계층 번호 기반 섹션 분할 ──────────────────────────
    articles = _split_admrul_by_sections(full_text)
    
    # 섹션 분할도 안 되면 전체를 조문 1개로
    if not articles and full_text:
        articles = [{
            "article_internal_key": "admrul-idx-001-full",
            "article_no":           1,
            "article_sub_no":       None,
            "article_type":         "본칙",
            "article_title":        "전문",
            "article_text":         full_text[:30000],
            "enforcement_date":     None,
            "is_changed":           False,
            "paragraphs":           [],
        }]
    
    return {"info": info, "articles": articles, "raw_xml": xml_text}


def _split_admrul_by_sections(text: str) -> List[dict]:
    """
    본문을 계층 번호(1.1, 1.2, 2.1 등)로 분할.
    v1.3: article_internal_key에 순차 idx 포함 → UNIQUE 보장
    """
    if not text or not text.strip():
        return []
    
    lines = text.split("\n")
    sections = []
    current_section = None
    current_content_lines = []
    current_title = ""
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            if current_section is not None:
                current_content_lines.append("")
            continue
        
        # "N.N 제목" 패턴 ("N.N.N"은 제외)
        m = re.match(r'^(\d+)\.(\d+)(?!\.\d)\s*(.*)$', line_stripped)
        if m:
            if current_section is not None:
                content = "\n".join(current_content_lines).strip()
                if content or current_title:
                    sections.append({
                        "major": current_section[0],
                        "minor": current_section[1],
                        "title": current_title,
                        "content": content,
                    })
            
            current_section = (int(m.group(1)), int(m.group(2)))
            current_title = m.group(3).strip()
            current_content_lines = []
        elif current_section is not None:
            current_content_lines.append(line_stripped)
    
    if current_section is not None:
        content = "\n".join(current_content_lines).strip()
        if content or current_title:
            sections.append({
                "major": current_section[0],
                "minor": current_section[1],
                "title": current_title,
                "content": content,
            })
    
    # 가상 조문 변환 (v1.3: idx 포함)
    articles = []
    for idx, sec in enumerate(sections, start=1):
        section_no = f"{sec['major']}.{sec['minor']}"
        full_title = f"{section_no} {sec['title']}".strip()
        full_text_val = f"{full_title}\n{sec['content']}".strip()
        
        articles.append({
            "article_internal_key": f"admrul-idx-{idx:03d}-sec-{section_no}",
            "article_no":           idx,
            "article_sub_no":       None,
            "article_type":         "본칙",
            "article_title":        full_title[:200],
            "article_text":         full_text_val[:30000],
            "enforcement_date":     None,
            "is_changed":           False,
            "paragraphs":           [],
        })
    
    return articles


# ============================================================
# 디버그
# ============================================================

def debug_admrul_api(query: str) -> dict:
    """행정규칙 API 테스트."""
    result = fetch_admrul_list(query=query, display=5)
    if not result["ok"]:
        return {"ok": False, "status": result["status"]}
    
    rules = parse_admrul_list_xml(result["xml"])
    return {
        "ok": True,
        "count": len(rules),
        "samples": [
            {"name": r["law_name"], "id": r["law_api_id"]}
            for r in rules[:3]
        ],
    }
