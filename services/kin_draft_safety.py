"""
네이버 지식인 답변 초안 세이프티 — 변호사법·표현 리스크 완화.

자동 게시가 아닌 '초안 검토용' 필터입니다.
"""

from __future__ import annotations

import re

DIAGNOSIS_URL_FRAGMENT = "taieng.co.kr/free-diagnosis.html"


def sanitize_kin_draft(text: str) -> str:
    """금지·민감 표현을 시스템 안내 문구로 치환."""
    if not text:
        return ""
    t = text
    t = re.sub(r"법률\s*상담", "조건코드 기반 자동 판정", t, flags=re.I)
    t = re.sub(r"법률\s*자문", "조건코드 기반 자동 판정", t, flags=re.I)
    t = re.sub(r"법적\s*조언", "시스템 가이드", t, flags=re.I)
    return t.strip()


def ensure_diagnosis_link(text: str) -> str:
    """본문 하단에 무료 진단 링크가 없으면 추가."""
    if DIAGNOSIS_URL_FRAGMENT in text:
        return text
    suffix = (
        "\n\n---\n3분 무료 법령진단: https://taieng.co.kr/free-diagnosis.html"
    )
    return text.rstrip() + suffix


def validate_draft_for_playwright(text: str) -> tuple[str, list[str]]:
    """
    입력 직전 검증. 반환: (최종 텍스트, 경고 메시지 목록).
    은 네이버 입력 실패 대신 로그용.
    """
    warnings: list[str] = []
    t = sanitize_kin_draft(text)
    if text != t:
        warnings.append("금지 표현이 조건코드 기반 자동 판정 등으로 치환되었습니다.")
    t = ensure_diagnosis_link(t)
    if DIAGNOSIS_URL_FRAGMENT not in t:
        warnings.append("무료 진단 링크 삽입에 실패했습니다. 수동으로 추가해 주세요.")
    return t, warnings
