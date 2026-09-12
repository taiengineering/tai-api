"""KOSHA 안전보건 자료 License Policy — WO-SAFETY-LIBRARY-001 WP-1D / WP-1C-3A.

순수 deterministic 함수. 네트워크 호출·DB 접근·LLM 호출을 하지 않는다.
공공누리(KOGL) 유형과 content_type만으로 이용조건·저장·제공 정책을 결정한다.

기준 문서: docs/2026-09-11_KOSHA_SAFETY_LIBRARY_기획서.md §4
절대 규칙:
  - UNKNOWN / 미상 / 미지원 값 → LINK_ONLY (fail-closed, 낙관 판정 금지)
  - OFFICIAL_EMBED 은 kogl_type 만으로 자동 지정하지 않는다.
    content_type == 'VIDEO' 이고 공식 embed 가 별도 확인된 경우에만 허용.
    ytbUrlAddr / selectSiteList / external_url 존재만으로는 확인이 아니다.
  - VIDEO 의 storage_allowed / binary_storage_allowed 는 어떤 경우에도 False.
  - TAI 는 상업 서비스: KOGL 2/4 는 별도 허락 없이 binary 저장·내부 제공 금지.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

KOGL_VALID = ("1", "2", "3", "4", "UNKNOWN")

_KOGL_PATTERNS = (
    re.compile(r"^0?([1-4])$"),
    re.compile(r"제\s*([1-4])\s*유형"),
    re.compile(r"(?<!\d)([1-4])\s*유형"),
    re.compile(r"TYPE\s*([1-4])(?:\b|$)", re.I),
)
RENDER_VALID = ("INTERNAL", "ORIGINAL_ONLY", "OFFICIAL_EMBED", "LINK_ONLY")
STORAGE_BASIS_VALID = ("KOGL", "SEPARATE_PERMISSION", "NONE")
PLAYBACK_VALID = ("OFFICIAL_EMBED", "EXTERNAL_LINK")

# This WP: no KOSHA separate permission is assumed.
SEPARATE_PERMISSION = False


@dataclass(frozen=True)
class LicenseDecision:
    kogl_type: str
    commercial_allowed: Optional[bool]
    modification_allowed: Optional[bool]
    render_policy: str
    storage_allowed: Optional[bool]          # VIDEO 항상 False. 비영상은 binary_storage_allowed 와 동일.
    binary_storage_allowed: bool = False
    internal_serve_allowed: bool = False
    original_only: bool = False
    storage_basis: str = "NONE"
    playback_policy: Optional[str] = None    # VIDEO only: OFFICIAL_EMBED | EXTERNAL_LINK


# kogl_type -> (commercial, modification, base_render, binary_ok, original_only)
# 1 출처표시 / 2 출처표시+상업금지 / 3 출처표시+변경금지 / 4 출처표시+상업금지+변경금지
_POLICY = {
    "1": (True,  True,  "INTERNAL",       True,  False),
    "2": (False, True,  "LINK_ONLY",      False, False),
    "3": (True,  False, "ORIGINAL_ONLY",  True,  True),
    "4": (False, False, "LINK_ONLY",      False, False),
    "UNKNOWN": (None, None, "LINK_ONLY",  False, False),
}


def normalize_kogl_type(raw: Optional[str]) -> str:
    """확인 실패·미상·미지원 값은 모두 UNKNOWN 으로 정규화한다 (fail-closed).

    허용: '1'~'4', '01'~'04', '제N유형', 'N유형', 'TYPE N'.
    연도·사고코드 등 숫자가 들어 있는 임의 문자열은 UNKNOWN.
    """
    if raw is None:
        return "UNKNOWN"
    v = str(raw).strip()
    if not v:
        return "UNKNOWN"
    for pat in _KOGL_PATTERNS:
        m = pat.search(v)
        if m:
            return m.group(1)
    return "UNKNOWN"


def decide(
    kogl_type: Optional[str],
    content_type: Optional[str] = None,
    official_embed_confirmed: bool = False,
    storage_basis: Optional[str] = None,
) -> LicenseDecision:
    """이용조건·render_policy·binary 저장 가능 여부를 결정한다.

    storage_basis:
      KOGL — 공공누리 유형만으로 판단 (기본, 이번 WP).
      SEPARATE_PERMISSION — 예약. 이번 단계는 존재한다고 가정하지 않으며 저장을 켜지 않는다.
      NONE — UNKNOWN 또는 근거 없음.
    """
    kt = normalize_kogl_type(kogl_type)
    commercial, modification, base_render, binary_ok, original_only = _POLICY[kt]
    ct = (content_type or "").strip().upper() or None

    basis = (storage_basis or ("NONE" if kt == "UNKNOWN" else "KOGL")).strip().upper()
    if basis not in STORAGE_BASIS_VALID:
        basis = "KOGL" if kt in ("1", "2", "3", "4") else "NONE"
    # 이번 WP: SEPARATE_PERMISSION 을 저장 허용으로 해석하지 않는다.
    if basis == "SEPARATE_PERMISSION":
        binary_ok = False
        serve_ok = False
        render = "LINK_ONLY"
        orig = original_only
    else:
        if kt == "UNKNOWN":
            basis = "NONE"
        serve_ok = binary_ok
        render = base_render
        orig = original_only

    if ct == "VIDEO":
        play = "OFFICIAL_EMBED" if official_embed_confirmed else "EXTERNAL_LINK"
        render_v = "OFFICIAL_EMBED" if official_embed_confirmed else "LINK_ONLY"
        return LicenseDecision(
            kt, commercial, modification, render_v,
            storage_allowed=False,
            binary_storage_allowed=False,
            internal_serve_allowed=False,
            original_only=orig,
            storage_basis=basis,
            playback_policy=play,
        )

    return LicenseDecision(
        kt, commercial, modification, render,
        storage_allowed=binary_ok,
        binary_storage_allowed=binary_ok,
        internal_serve_allowed=serve_ok,
        original_only=orig,
        storage_basis=basis,
        playback_policy=None,
    )
