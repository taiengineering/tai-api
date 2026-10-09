"""EXT-132 XML 파서 — 소방청 위험물안전관리.

XML 필드명/구조는 UNVERIFIED: 샘플 응답 수신 전까지 unknown_fields 로 수집.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any


class Ext132ParseError(Exception):
    """XML 파싱 실패 또는 예상 구조와 다를 때."""


@dataclass(frozen=True)
class Ext132Item:
    """원본 API 응답의 단일 위험물 레코드.

    chemicalno: 원본 source_id (XML 필드명 UNVERIFIED).
    raw: 원본 XML 필드 전체 보존 — 스키마 확정 전 유실 방지.
    """
    chemicalno: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageResult:
    total_count: int | None      # totalCount 필드 UNVERIFIED
    page_no: int
    num_of_rows: int
    items: list[Ext132Item]
    result_code: str | None = None
    result_msg: str | None = None


def parse_page(content: bytes) -> PageResult:
    """XML 바이트 → PageResult.

    Raises Ext132ParseError on malformed XML.
    total_count=None when API does not include totalCount.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise Ext132ParseError(f"XML parse error: {exc}") from exc

    result_code = _text(root, ".//resultCode")
    result_msg = _text(root, ".//resultMsg")

    total_count_raw = _text(root, ".//totalCount")
    total_count = int(total_count_raw) if total_count_raw and total_count_raw.isdigit() else None

    page_no_raw = _text(root, ".//pageNo")
    num_of_rows_raw = _text(root, ".//numOfRows")

    items: list[Ext132Item] = []
    for item_el in root.findall(".//item"):
        raw: dict[str, Any] = {
            child.tag: child.text for child in item_el if child.text is not None
        }
        chemicalno = raw.get("chemicalno") or ""
        items.append(Ext132Item(chemicalno=chemicalno, raw=raw))

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
