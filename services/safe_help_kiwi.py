# -*- coding: utf-8 -*-
"""safe 헬프센터 한글 형태소 검색 색인/질의 유틸(자족). 45cminc/marketing kiwi_search.py 이식.

pg 기본 파서는 한글 형태소를 못 쪼갠다. 이 모듈이 Kiwi(kiwipiepy)로 형태소 분석해
검색어 토큰(명사·외국어·숫자 위주)을 뽑고, 그 토큰 문자열을 to_tsvector('simple', ...) 에 넣는다.
색인(문서)과 질의(검색어)를 동일 분석기로 처리해 매칭 일관성을 보장한다.

안전 후퇴(가짜값 금지): Kiwi 미설치/로드 실패 시 _fallback_tokens 로 공백·기호 분해만 수행.
이 경우에도 색인·질의가 같은 폴백을 쓰므로 정합. tai-api requirements.txt 에 kiwipiepy 존재.
"""
from __future__ import annotations
import re
from html.parser import HTMLParser
from typing import List, Optional

_KIWI = None
_KIWI_TRIED = False

# 색인 대상 품사(Kiwi 태그): 명사/외국어/한자/숫자/영문/어근 + 동·형용사 어간.
_KEEP_TAGS = ("NNG", "NNP", "NNB", "SL", "SH", "SN", "NR", "NP", "VV", "VA", "XR")


def _get_kiwi():
    global _KIWI, _KIWI_TRIED
    if _KIWI is not None or _KIWI_TRIED:
        return _KIWI
    _KIWI_TRIED = True
    try:
        from kiwipiepy import Kiwi  # type: ignore
        _KIWI = Kiwi()
    except Exception:
        _KIWI = None
    return _KIWI


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._buf: List[str] = []

    def handle_data(self, data):
        self._buf.append(data)

    def text(self) -> str:
        return " ".join(self._buf)


def strip_html(html: str) -> str:
    if not html:
        return ""
    try:
        p = _Stripper()
        p.feed(html)
        return re.sub(r"\s+", " ", p.text()).strip()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _fallback_tokens(text: str) -> List[str]:
    if not text:
        return []
    raw = re.findall(r"[0-9A-Za-z가-힣]+", text)
    return [t.lower() for t in raw if len(t) >= 2]


def tokens(text: str) -> List[str]:
    if not text:
        return []
    kiwi = _get_kiwi()
    if kiwi is None:
        return _fallback_tokens(text)
    try:
        out: List[str] = []
        for tok in kiwi.tokenize(text):
            tag = getattr(tok, "tag", "")
            form = getattr(tok, "form", "")
            if tag in _KEEP_TAGS and form and len(form) >= 1:
                out.append(form.lower())
        return out or _fallback_tokens(text)
    except Exception:
        return _fallback_tokens(text)


def index_text(*parts: Optional[str]) -> str:
    """색인 대상 필드들을 합쳐 토큰 문자열 반환. SQL 에서 to_tsvector('simple', :txt) 로 감싼다."""
    joined = " ".join(p for p in parts if p)
    return " ".join(tokens(joined))


def query_text(q: str) -> str:
    """검색어 → 토큰 문자열. websearch_to_tsquery('simple', :q) 입력. 색인과 동일 분석기."""
    return " ".join(tokens(q or ""))
