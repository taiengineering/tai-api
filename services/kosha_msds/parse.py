"""Fail-closed XML parser for KOSHA MSDS OpenAPI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from xml.etree import ElementTree as ET

from services.kosha_msds.contract import SUCCESS_RESULT_CODES


class KoshaMsdsParseError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class KoshaMsdsResultError(Exception):
    def __init__(self, result_code: str, result_msg: str):
        super().__init__(f"KOSHA MSDS resultCode={result_code}")
        self.result_code = result_code
        self.result_msg = result_msg


def _local(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or el.text is None:
        return None
    return el.text


def parse_xml_root(text: str) -> ET.Element:
    if not (text or "").strip():
        raise KoshaMsdsParseError("XML_EMPTY", "empty XML body")
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise KoshaMsdsParseError("XML_MALFORMED", str(exc)) from exc


def _items(root: ET.Element) -> list[dict[str, Optional[str]]]:
    rows: list[dict[str, Optional[str]]] = []
    for items_el in root.findall(".//items"):
        for item_el in list(items_el):
            if _local(item_el.tag) != "item":
                continue
            row: dict[str, Optional[str]] = {}
            for child in list(item_el):
                row[_local(child.tag)] = child.text
            rows.append(row)
    return rows


@dataclass(frozen=True)
class MsdsListResponse:
    result_code: str
    result_msg: str
    total_count: int
    page_no: int
    num_of_rows: int
    items: list[dict[str, Optional[str]]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.result_code in SUCCESS_RESULT_CODES


@dataclass(frozen=True)
class MsdsSectionResponse:
    result_code: str
    result_msg: str
    items: list[dict[str, Optional[str]]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.result_code in SUCCESS_RESULT_CODES

    @property
    def empty_but_valid(self) -> bool:
        return self.ok and len(self.items) == 0


def _require_header(root: ET.Element) -> tuple[str, str]:
    if _local(root.tag) not in {"response", "OpenAPI_ServiceResponse"}:
        raise KoshaMsdsParseError("XML_ROOT", f"unexpected root={_local(root.tag)}")
    code = root.findtext(".//resultCode")
    msg = root.findtext(".//resultMsg") or root.findtext(".//errMsg") or ""
    if code is None or code == "":
        # gateway envelope
        code = root.findtext(".//returnReasonCode") or ""
        msg = root.findtext(".//returnAuthMsg") or msg
    if code == "":
        raise KoshaMsdsParseError("RESULT_CODE_MISSING", "resultCode missing")
    return code, msg


def parse_list_xml(text: str, *, require_success: bool = True) -> MsdsListResponse:
    root = parse_xml_root(text)
    code, msg = _require_header(root)
    parsed = MsdsListResponse(
        result_code=code,
        result_msg=msg,
        total_count=_parse_int(root.findtext(".//totalCount"), 0),
        page_no=_parse_int(root.findtext(".//pageNo"), 1),
        num_of_rows=_parse_int(root.findtext(".//numOfRows"), 0),
        items=_items(root),
    )
    if require_success and not parsed.ok:
        raise KoshaMsdsResultError(parsed.result_code, parsed.result_msg)
    return parsed


def parse_section_xml(text: str, *, require_success: bool = True) -> MsdsSectionResponse:
    root = parse_xml_root(text)
    code, msg = _require_header(root)
    parsed = MsdsSectionResponse(result_code=code, result_msg=msg, items=_items(root))
    if require_success and not parsed.ok:
        raise KoshaMsdsResultError(parsed.result_code, parsed.result_msg)
    return parsed


def _parse_int(raw: Optional[str], default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise KoshaMsdsParseError("INT_INVALID", f"not an int: {raw}") from exc


def normalize_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def canonical_section_items(items: list[dict[str, Optional[str]]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        rows.append(
            {
                "msdsItemCode": normalize_optional(item.get("msdsItemCode")),
                "upMsdsItemCode": normalize_optional(item.get("upMsdsItemCode")),
                "msdsItemNameKor": normalize_optional(item.get("msdsItemNameKor")),
                "msdsItemNo": normalize_optional(item.get("msdsItemNo")),
                "lev": normalize_optional(item.get("lev")),
                "ordrIdx": normalize_optional(item.get("ordrIdx")),
                "itemDetail": item.get("itemDetail") if item.get("itemDetail") is not None else None,
            }
        )
    rows.sort(
        key=lambda r: (
            r["ordrIdx"] or "",
            r["msdsItemCode"] or "",
            r["msdsItemNameKor"] or "",
        )
    )
    return rows
