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

    # REPAIR-A: resultCode MUST be present — fail-closed
    if result_code is None:
        raise Ext037ParseError("resultCode missing from response")

    # REPAIR-A: non-"00" → early return (body may be absent — API error response)
    if result_code != "00":
        return PageResult(
            total_count=None,
            page_no=0,
            num_of_rows=0,
            items=[],
            result_code=result_code,
            result_msg=result_msg,
        )

    # REPAIR-A FINAL: body element must exist for resultCode="00"
    body_el = root.find("body")
    if body_el is None:
        raise Ext037ParseError("body element missing for resultCode='00'")

    # REPAIR-A: resultCode == "00" — validate all required pagination fields
    total_count_raw = _text(root, ".//totalCount")
    if total_count_raw is None or not total_count_raw.isdigit():
        raise Ext037ParseError(
            f"totalCount missing or invalid for resultCode='00' (got {total_count_raw!r})"
        )
    total_count = int(total_count_raw)
    if total_count < 0:
        raise Ext037ParseError(f"totalCount must be >= 0 (got {total_count})")

    page_no_raw = _text(root, ".//pageNo")
    if page_no_raw is None or not page_no_raw.isdigit() or int(page_no_raw) < 1:
        raise Ext037ParseError(
            f"pageNo missing or invalid for resultCode='00' (got {page_no_raw!r})"
        )
    page_no = int(page_no_raw)

    num_of_rows_raw = _text(root, ".//numOfRows")
    if num_of_rows_raw is None or not num_of_rows_raw.isdigit() or int(num_of_rows_raw) < 1:
        raise Ext037ParseError(
            f"numOfRows missing or invalid for resultCode='00' (got {num_of_rows_raw!r})"
        )
    num_of_rows = int(num_of_rows_raw)

    # REPAIR-A FINAL: body/items element must exist for resultCode="00"
    items_el = body_el.find("items")
    if items_el is None:
        raise Ext037ParseError("body/items element missing for resultCode='00'")

    items: list[Ext037Item] = []
    for item_el in items_el.findall("item"):  # REPAIR-A FINAL: strict body/items/item path
        raw: dict[str, Any] = {
            child.tag: child.text for child in item_el if child.text is not None
        }
        datano_raw = raw.get("dataNo") or raw.get("datano") or ""
        # REPAIR-A FINAL: strip whitespace for blank check; preserve original value
        if not datano_raw.strip():
            raise Ext037ParseError("item found with blank/missing dataNo")
        items.append(Ext037Item(datano=datano_raw, raw=raw))

    return PageResult(
        total_count=total_count,
        page_no=page_no,
        num_of_rows=num_of_rows,
        items=items,
        result_code=result_code,
        result_msg=result_msg,
    )


def _text(root: ET.Element, path: str) -> str | None:
    el = root.find(path)
    return el.text if el is not None else None
