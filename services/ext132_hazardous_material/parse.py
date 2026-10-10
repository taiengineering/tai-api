"""EXT-132 파서 — XML 및 JSON 응답 지원.

실측(2026-10-10): API는 type=xml 파라미터 무관 JSON 반환.
PK 원본 필드명: chemaicalno (API 측 오타). 내부 속성 chemicalno 유지.
정상 resultCode: "0" (JSON 실측) 또는 "00" (XML 문서 기준).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any


class Ext132ParseError(Exception):
    """파싱 실패 또는 예상 구조와 다를 때."""


@dataclass(frozen=True)
class Ext132Item:
    """원본 API 응답의 단일 위험물 레코드.

    chemicalno: 내부 source PK. JSON 응답 원본 필드명은 chemaicalno.
    raw: 원본 필드 전체 보존 (원본 필드명 그대로 유지).
    """
    chemicalno: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageResult:
    total_count: int | None
    page_no: int
    num_of_rows: int
    items: list[Ext132Item]
    result_code: str | None = None
    result_msg: str | None = None


# 정상 resultCode 집합 — _parse_json 내 필수 필드 검증 조건
_JSON_NORMAL_CODES: frozenset[str] = frozenset({"0", "00"})


def parse_page(content: bytes) -> PageResult:
    """XML 또는 JSON 바이트 → PageResult.

    응답 형식을 자동 감지한다.
    Raises Ext132ParseError on malformed input or unexpected structure.
    total_count=None when API does not include totalCount.
    """
    stripped = content.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        return _parse_json(content)
    return _parse_xml(content)


def _req_nonneg(body: dict[str, Any], key: str) -> int:
    """body[key]를 비음수 정수로 반환. 없거나 잘못된 값이면 Ext132ParseError."""
    val = body.get(key)
    if isinstance(val, int) and not isinstance(val, bool):
        n = val
    elif isinstance(val, str) and val.isdigit():
        n = int(val)
    else:
        raise Ext132ParseError(
            f"JSON normal response requires non-negative integer 'body.{key}', got {val!r}"
        )
    if n < 0:
        raise Ext132ParseError(f"JSON 'body.{key}' must be non-negative, got {n}")
    return n


def _req_pos(body: dict[str, Any], key: str) -> int:
    """body[key]를 양의 정수로 반환. 없거나 0 이하이면 Ext132ParseError."""
    n = _req_nonneg(body, key)
    if n < 1:
        raise Ext132ParseError(f"JSON 'body.{key}' must be positive, got {n}")
    return n


def _parse_json(content: bytes) -> PageResult:
    """JSON 응답 파싱 — 실측 구조: {"header": {...}, "body": {...}}."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise Ext132ParseError(f"JSON parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise Ext132ParseError(f"JSON root must be object, got {type(data).__name__}")

    header = data.get("header")
    body = data.get("body")
    if not isinstance(header, dict):
        raise Ext132ParseError("JSON response missing 'header' object")
    if not isinstance(body, dict):
        raise Ext132ParseError("JSON response missing 'body' object")

    # resultCode: 정상/오류 구분 전에 반드시 존재해야 한다
    rc_raw = header.get("resultCode")
    if rc_raw is None:
        raise Ext132ParseError("JSON response missing 'header.resultCode'")
    result_code = str(rc_raw)
    result_msg = str(header["resultMsg"]) if "resultMsg" in header else None

    is_normal = result_code in _JSON_NORMAL_CODES

    if is_normal:
        # 정상 응답: 필수 필드 누락은 Fail-closed
        total_count: int | None = _req_nonneg(body, "totalCount")
        page_no = _req_pos(body, "pageNo")
        num_of_rows = _req_pos(body, "numOfRows")
        raw_items = body.get("items")
        if raw_items is None:
            raise Ext132ParseError("JSON normal response missing 'body.items'")
        if not isinstance(raw_items, list):
            raise Ext132ParseError(
                f"JSON 'body.items' expected list, got {type(raw_items).__name__}"
            )
    else:
        # 오류 응답: 필드 누락 허용 — sync.py가 API_ERROR_CODE로 처리
        total_count_raw = body.get("totalCount")
        if isinstance(total_count_raw, int) and not isinstance(total_count_raw, bool):
            total_count = total_count_raw
        elif isinstance(total_count_raw, str) and total_count_raw.isdigit():
            total_count = int(total_count_raw)
        else:
            total_count = None

        page_no_raw = body.get("pageNo")
        if isinstance(page_no_raw, int) and not isinstance(page_no_raw, bool):
            page_no = page_no_raw
        elif isinstance(page_no_raw, str) and page_no_raw.isdigit():
            page_no = int(page_no_raw)
        else:
            page_no = 0

        num_of_rows_raw = body.get("numOfRows")
        if isinstance(num_of_rows_raw, int) and not isinstance(num_of_rows_raw, bool):
            num_of_rows = num_of_rows_raw
        elif isinstance(num_of_rows_raw, str) and num_of_rows_raw.isdigit():
            num_of_rows = int(num_of_rows_raw)
        else:
            num_of_rows = 0

        raw_items = body.get("items")
        if raw_items is not None and not isinstance(raw_items, list):
            raw_items = None

    items: list[Ext132Item] = []
    for i, raw_item in enumerate(raw_items or []):
        if not isinstance(raw_item, dict):
            raise Ext132ParseError(
                f"JSON item[{i}] expected object, got {type(raw_item).__name__}"
            )
        raw: dict[str, Any] = {
            k: (str(v) if v is not None else "") for k, v in raw_item.items()
        }
        # PK 매핑: chemaicalno = API 원본 오타 필드, chemicalno = XML 호환 필드
        pk_a = raw.get("chemaicalno") or ""
        pk_b = raw.get("chemicalno") or ""
        if pk_a and pk_b and pk_a != pk_b:
            raise Ext132ParseError(
                f"JSON item[{i}]: conflicting PK chemaicalno={pk_a!r} vs chemicalno={pk_b!r}"
            )
        chemicalno = pk_a or pk_b
        if not chemicalno:
            raise Ext132ParseError(
                f"JSON item[{i}]: required PK (chemaicalno/chemicalno) missing or empty"
            )
        items.append(Ext132Item(chemicalno=chemicalno, raw=raw))

    return PageResult(
        total_count=total_count,
        page_no=page_no,
        num_of_rows=num_of_rows,
        items=items,
        result_code=result_code,
        result_msg=result_msg,
    )


def _parse_xml(content: bytes) -> PageResult:
    """XML 응답 파싱 — 기존 구현 유지."""
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
