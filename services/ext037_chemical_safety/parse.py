"""EXT-037 XML 파서 — 화학안전원 화학물질안전정보.

G1 probe 확인 사항:
  - XML 응답, resultCode "00" = 정상
  - PK 필드: dataNo (TEXT)
  - 주요 필드: dataNo, casNo, chemEn, chemKo, symptom, inhale, skin, eyeball, oral
  - 특수문자 "·" 포함 (raw 보존)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any


class Ext037ParseError(Exception):
    """XML 파싱 실패 또는 예상 구조와 다를 때."""


@dataclass(frozen=True)
class Ext037Item:
    """원본 API 응답의 단일 화학물질안전정보 레코드.

    datano: 원본 source_id (G1 probe 확인).
    raw: 원본 XML 필드 전체 보존 (특수문자 포함).
    """
    datano: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageResult:
    total_count: int | None
    page_no: int
    num_of_rows: int
    items: list[Ext037Item]
    result_code: str | None = None
    result_msg: str | None = None


def parse_page(content: bytes) -> PageResult:
    """XML 바이트 → PageResult.

    Raises Ext037ParseError on malformed XML.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise Ext037ParseError(f"XML parse error: {exc}") from exc

    result_code = _text(root, ".//resultCode")
    result_msg = _text(root, ".//resultMsg")

    total_count_raw = _text(root, ".//totalCount")
    total_count = int(total_count_raw) if total_count_raw and total_count_raw.isdigit() else None

    page_no_raw = _text(root, ".//pageNo")
    num_of_rows_raw = _text(root, ".//numOfRows")

    items: list[Ext037Item] = []
    for item_el in root.findall(".//item"):
        raw: dict[str, Any] = {
            child.tag: child.text for child in item_el if child.text is not None
        }
        datano = raw.get("dataNo") or raw.get("datano") or ""
        items.append(Ext037Item(datano=datano, raw=raw))

    return PageResult(
        total_count=total_count,
        page_no=int(page_no_raw) if page_no_raw and page_no_raw.isdigit() else 0,
        num_of_rows=int(num_of_rows_raw) if num_of_rows_raw and num_of_rows_raw.isdigit() else 0,
        items=items,
        result_code=result_code,
        result_msg=result_msg,
    )


def _text(root: ET.Element, path: str) -> str | None:
    el = root.find(path)
    return el.text if el is not None else None
