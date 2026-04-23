# routers/law_collector_admrul.py v2.0
# 행정규칙(NFTC/NFPC 등) 수집용 헬퍼
#
# v2.0 (2026-04-23): 조문형식여부(Y/N) 기반 분기 파서
#   - NFPC (Y): <조문내용> 여러 개 순회 → "제N조" 추출
#     internal_key = "nfpc-art-{조문번호:03d}" (예: nfpc-art-038)
#     제N조의M 패턴: "nfpc-art-{조문번호:03d}-of-{sub:02d}"
#   - NFTC (N): 섹션 계층 번호 모든 레벨 캡처 (1, 1.1, 1.1.1, 1.7.1.11)
#     internal_key = "nftc-sec-{섹션번호}" (예: nftc-sec-1.7.1.11)
#   - 태그없음 (전기설비 등): 폴백 기반 전체 수집 (v1.4 유지)
#
# ⚠️ 내부 키 체계만 설계: 법제처 deep link/API/변경이력 연동 미포함 (별도 논의)
#
# v1.4: 조문내용 50자 미만 시 itertext() 폴백
# v1.3: article_internal_key에 idx 포함
# v1.2: 가상 조문 전략
# v1.1: LID 파라미터

import re
import requests
import xml.etree.ElementTree as ET
from typing import List, Optional

from routers.law_collector import (
    DEFAULT_HEADERS,
    LAW_API_OC,
    LAW_API_BASE,
    clean_cdata,
    parse_date,
)


# ============================================================
# 행정규칙 API (변경 없음)
# ============================================================

def fetch_admrul_list(query: str, display: int = 20, page: int = 1) -> dict:
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


def parse_admrul_list_xml(xml_text: str) -> list:
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
# 메타데이터 처리
# ============================================================

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


def _extract_info(basic: Optional[ET.Element]) -> dict:
    """<행정규칙기본정보>에서 메타 추출."""
    if basic is None:
        return {}
    return {
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


def _collect_full_text_fallback(root: ET.Element) -> str:
    """<조문내용>이 너무 짧을 때 폴백. 메타데이터 제외 전체 텍스트."""
    texts: List[str] = []
    
    def _walk(elem: ET.Element):
        if elem.tag in _META_TAGS_EXCLUDE:
            return
        if elem.text and elem.text.strip():
            texts.append(elem.text.strip())
        for child in elem:
            _walk(child)
        if elem.tail and elem.tail.strip():
            texts.append(elem.tail.strip())
    
    for child in root:
        _walk(child)
    
    return "\n".join(texts)


# ============================================================
# 본문 XML 파싱 (분기 처리)
# ============================================================

def parse_admrul_content_xml(xml_text: str) -> dict:
    """
    행정규칙 본문 XML 파싱 (v2.0: 조문형식여부 기반 분기).
    
    분기:
      Y (NFPC)       → _parse_nfpc_articles
      N (NFTC)       → _parse_nftc_articles  
      태그없음/기타  → _parse_fallback (기존 v1.4 로직)
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"행정규칙 XML 파싱 실패: {e}")
    
    if root.tag == "Law" and (root.text or "").strip().startswith("일치하는"):
        raise RuntimeError(f"행정규칙 본문 API: {root.text.strip()}")
    
    basic = root.find("행정규칙기본정보") or root.find("기본정보")
    info = _extract_info(basic)
    
    # ─── 조문형식여부 확인 ─────────────────────────────────
    form_flag = ""
    if basic is not None:
        form_flag = (basic.findtext("조문형식여부", "") or "").strip().upper()
    
    # ─── 체계별 파서 분기 ──────────────────────────────────
    if form_flag == "Y":
        # NFPC: <조문내용> 여러 개에서 "제N조" 추출
        articles = _parse_nfpc_articles(root)
        parse_mode = "NFPC"
    elif form_flag == "N":
        # NFTC: 섹션 계층 번호 모든 레벨 캡처
        articles = _parse_nftc_articles(root)
        parse_mode = "NFTC"
    else:
        # 태그없음: 전기설비기술기준 등 특수 구조
        articles = _parse_fallback(root)
        parse_mode = "FALLBACK"
    
    # 모든 경우: 결과 비어있으면 전문 1개로
    if not articles:
        full_text = _collect_full_text_fallback(root).strip()
        if full_text:
            articles = [{
                "article_internal_key": "admrul-full",
                "article_no":           1,
                "article_sub_no":       None,
                "article_type":         "본칙",
                "article_title":        "전문",
                "article_text":         full_text[:30000],
                "enforcement_date":     None,
                "is_changed":           False,
                "paragraphs":           [],
            }]
    
    info["_parse_mode"] = parse_mode
    return {"info": info, "articles": articles, "raw_xml": xml_text}


# ============================================================
# NFPC 파서 (조문형식여부=Y)
# ============================================================

# "제N조" 또는 "제N조의M" 패턴
_NFPC_ARTICLE_PATTERN = re.compile(
    r'^\s*제\s*(\d+)\s*조\s*(?:의\s*(\d+))?\s*(?:\(([^)]*)\))?\s*(.*)$',
    re.DOTALL
)


def _parse_nfpc_articles(root: ET.Element) -> List[dict]:
    """
    NFPC 파서: <조문내용> 태그 여러 개 순회.
    각 태그 텍스트에서 "제N조(제목) 본문" 패턴 추출.
    
    internal_key:
      일반 조문:  "nfpc-art-{조문번호:03d}"        예: nfpc-art-038
      제N조의M:   "nfpc-art-{조문번호:03d}-of-{M:02d}"  예: nfpc-art-038-of-02
      부칙:       "nfpc-bu-{idx:03d}"
    """
    articles = []
    content_elements = root.findall("조문내용")
    
    if not content_elements:
        return []
    
    for idx, elem in enumerate(content_elements, start=1):
        text = (elem.text or "").strip()
        if not text:
            continue
        
        text = clean_cdata(text) if callable(clean_cdata) else text
        
        # "제N조(제목) 본문" 패턴 매칭
        m = _NFPC_ARTICLE_PATTERN.match(text)
        
        if m:
            article_no = int(m.group(1))
            article_sub = int(m.group(2)) if m.group(2) else None
            title = (m.group(3) or "").strip()
            body = (m.group(4) or "").strip()
            
            # internal_key 생성 (결정적)
            if article_sub:
                internal_key = f"nfpc-art-{article_no:03d}-of-{article_sub:02d}"
            else:
                internal_key = f"nfpc-art-{article_no:03d}"
            
            # 제목 없으면 본문에서 추출 시도
            if not title:
                # "제1조" 뒤에 바로 본문 시작하는 경우
                title = body[:30].strip() or f"제{article_no}조"
            
            articles.append({
                "article_internal_key": internal_key,
                "article_no":           article_no,
                "article_sub_no":       article_sub,
                "article_type":         "본칙",
                "article_title":        title[:200],
                "article_text":         text[:30000],
                "enforcement_date":     None,
                "is_changed":           False,
                "paragraphs":           [],
            })
        else:
            # "제N조" 패턴 아닌 것 (부칙, 별표 등)
            # 부칙 감지
            if "부칙" in text[:20] or "附則" in text[:20]:
                internal_key = f"nfpc-bu-{idx:03d}"
                article_type = "부칙"
                title = "부칙"
            else:
                internal_key = f"nfpc-misc-{idx:03d}"
                article_type = "본칙"
                title = text[:30].strip() or f"항목 {idx}"
            
            articles.append({
                "article_internal_key": internal_key,
                "article_no":           idx,
                "article_sub_no":       None,
                "article_type":         article_type,
                "article_title":        title[:200],
                "article_text":         text[:30000],
                "enforcement_date":     None,
                "is_changed":           False,
                "paragraphs":           [],
            })
    
    return articles


# ============================================================
# NFTC 파서 (조문형식여부=N)
# ============================================================

# 섹션 번호 패턴: 1, 1.1, 1.1.1, 1.7.1.11 등 (모든 레벨)
_NFTC_SECTION_PATTERN = re.compile(r'^(\d+(?:\.\d+)*)\s*(.*)$')


def _parse_nftc_articles(root: ET.Element) -> List[dict]:
    """
    NFTC 파서: 본문 전체에서 계층 번호 섹션 모두 캡처.
    
    처리:
      1. <조문내용> 첫 번째만 가져오면 NFTC 본문 누락 위험
         → 모든 <조문내용> 텍스트 병합
      2. 라인별로 "N.N.N..." 패턴 매칭 (모든 깊이)
      3. 각 섹션을 독립 article로 저장
    
    internal_key:
      "nftc-sec-{섹션번호}"
      예: nftc-sec-1, nftc-sec-1.1, nftc-sec-1.1.1, nftc-sec-1.7.1.11
    """
    # 모든 <조문내용> 병합 (첫 번째만 가져오면 NFTC도 놓침)
    content_parts = []
    for elem in root.findall("조문내용"):
        if elem.text and elem.text.strip():
            content_parts.append(elem.text.strip())
    
    if not content_parts:
        # 폴백: 전체 텍스트 수집
        full_text = _collect_full_text_fallback(root)
    else:
        full_text = "\n".join(content_parts)
    
    if not full_text or len(full_text) < 30:
        return []
    
    # 라인별로 섹션 추출
    lines = full_text.split("\n")
    sections = []
    current_section = None  # {"num": "1.1.1", "title": "...", "lines": [...]}
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_section:
                current_section["lines"].append("")
            continue
        
        m = _NFTC_SECTION_PATTERN.match(stripped)
        if m and m.group(1) and "." in m.group(1) or (m and m.group(1) and m.group(1).isdigit()):
            # 섹션 헤더 발견 (1, 1.1, 1.1.1 등 모두)
            section_num = m.group(1)
            section_rest = m.group(2).strip()
            
            # 섹션 번호만 있고 뒤에 내용 없는 건 헤더로 처리
            # 섹션 번호 + 제목 또는 내용이 뒤따름
            
            # 이전 섹션 마무리
            if current_section:
                sections.append(current_section)
            
            current_section = {
                "num": section_num,
                "title": section_rest[:100] if section_rest else "",
                "lines": [section_rest] if section_rest else [],
            }
        elif current_section:
            current_section["lines"].append(stripped)
        # 섹션 시작 전 텍스트는 무시 (헤더/목차 영역)
    
    # 마지막 섹션 저장
    if current_section:
        sections.append(current_section)
    
    if not sections:
        return []
    
    # 섹션 → article 변환
    articles = []
    for idx, sec in enumerate(sections, start=1):
        section_num = sec["num"]
        title = sec["title"] or f"섹션 {section_num}"
        body_text = "\n".join(line for line in sec["lines"] if line is not None).strip()
        
        # article_text는 섹션 번호 + 제목 + 본문
        full_article_text = f"{section_num} {title}\n{body_text}".strip()
        
        # 섹션 깊이 (점 개수)
        depth = section_num.count(".")
        article_type = {
            0: "장",      # "1" → 대분류
            1: "절",      # "1.1" → 중분류
            2: "조",      # "1.1.1" → 세부
            3: "항",      # "1.1.1.1" → 말단
        }.get(depth, "목")
        
        articles.append({
            "article_internal_key": f"nftc-sec-{section_num}",
            # article_no는 첫 번째 점 앞 숫자
            "article_no":           int(section_num.split(".")[0]),
            "article_sub_no":       None,
            "article_type":         article_type,
            "article_title":        f"{section_num} {title}"[:200],
            "article_text":         full_article_text[:30000],
            "enforcement_date":     None,
            "is_changed":           False,
            "paragraphs":           [],
        })
    
    return articles


# ============================================================
# 폴백 파서 (조문형식여부 태그 없음 = 특수 구조)
# ============================================================

def _parse_fallback(root: ET.Element) -> List[dict]:
    """
    조문형식여부 태그 없는 경우 (전기설비기술기준 등).
    v1.4 로직 유지: 전체 텍스트 수집 후 섹션 분할 시도.
    """
    # 1차: <조문내용> 시도
    content_text = (root.findtext("조문내용", "") or "").strip()
    
    # 2차: 너무 짧으면 폴백
    MIN_CONTENT_LENGTH = 50
    if len(content_text) < MIN_CONTENT_LENGTH:
        content_text = _collect_full_text_fallback(root)
    
    if not content_text.strip():
        return []
    
    # 섹션 분할 시도 (기존 로직)
    lines = content_text.split("\n")
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
    
    # article 변환
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
