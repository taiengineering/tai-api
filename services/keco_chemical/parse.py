"""KECO 15149420 JSON 응답 파서. fail-closed, raw 원본 보존."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


class KecoParseError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class KecoResultError(Exception):
    def __init__(self, result_code: str, result_msg: str):
        super().__init__(f"KECO resultCode={result_code}")
        self.result_code = result_code
        self.result_msg = result_msg


@dataclass
class KecoRegulatoryFact:
    """typeList[] 내 단일 규제 사실 항목."""
    sbstn_clsf_type_nm: Optional[str]
    unq_no: Optional[str]
    cont_info: Optional[str]
    excp_info: Optional[str]
    ancmnt_ymd: Optional[str]   # raw string — date cast 금지
    ancmnt_info: Optional[str]


@dataclass
class KecoChemicalItem:
    """단일 화학물질 항목."""
    sbstn_id: Optional[str]
    cas_no: Optional[str]
    korexst_raw: Optional[str]   # korexst 원문 — KE번호 확정 변환 금지
    sbstn_nm_kor: Optional[str]
    sbstn_nm_eng: Optional[str]
    sbstn_nm2_kor: Optional[str]
    sbstn_nm2_eng: Optional[str]
    mlcfrm: Optional[str]
    mlcwgt: Optional[str]
    type_list: list[KecoRegulatoryFact] = field(default_factory=list)


@dataclass
class KecoSearchResponse:
    """전체 검색 응답 envelope."""
    result_code: str
    result_msg: str
    page_no: Optional[str]
    num_of_rows: Optional[str]
    total_count: Optional[str]
    items: list[KecoChemicalItem]


def _optional_str(val: object) -> Optional[str]:
    """None이거나 빈 문자열이면 None 반환. 원본 그대로 보존."""
    if val is None:
        return None
    s = str(val)
    return s if s else None


def _parse_regulatory_fact(raw: dict) -> KecoRegulatoryFact:
    return KecoRegulatoryFact(
        sbstn_clsf_type_nm=_optional_str(raw.get("sbstnClsfTypeNm")),
        unq_no=_optional_str(raw.get("unqNo")),
        cont_info=_optional_str(raw.get("contInfo")),
        excp_info=_optional_str(raw.get("excpInfo")),
        ancmnt_ymd=_optional_str(raw.get("ancmntYmd")),   # raw string 보존
        ancmnt_info=_optional_str(raw.get("ancmntInfo")),
    )


def _parse_chemical_item(raw: dict) -> KecoChemicalItem:
    type_list_raw = raw.get("typeList")
    if not isinstance(type_list_raw, list):
        type_list_raw = []
    type_list = [_parse_regulatory_fact(t) for t in type_list_raw if isinstance(t, dict)]

    return KecoChemicalItem(
        sbstn_id=_optional_str(raw.get("sbstnId")),
        cas_no=_optional_str(raw.get("casNo")),
        korexst_raw=_optional_str(raw.get("korexst")),   # 원문 보존
        sbstn_nm_kor=_optional_str(raw.get("sbstnNmKor")),
        sbstn_nm_eng=_optional_str(raw.get("sbstnNmEng")),
        sbstn_nm2_kor=_optional_str(raw.get("sbstnNm2Kor")),
        sbstn_nm2_eng=_optional_str(raw.get("sbstnNm2Eng")),
        mlcfrm=_optional_str(raw.get("mlcfrm")),
        mlcwgt=_optional_str(raw.get("mlcwgt")),
        type_list=type_list,
    )


def parse_keco_response(text: str) -> KecoSearchResponse:
    """JSON 응답 → KecoSearchResponse. items absent/null/[] 모두 0건으로 처리."""
    if not (text or "").strip():
        raise KecoParseError("JSON_EMPTY", "empty response body")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise KecoParseError("JSON_MALFORMED", str(exc)) from exc

    if not isinstance(data, dict):
        raise KecoParseError("JSON_ROOT_NOT_OBJECT", "root must be JSON object")

    header = data.get("header") or {}
    if not isinstance(header, dict):
        raise KecoParseError("JSON_HEADER_MISSING", "header field missing or not object")

    result_code = _optional_str(header.get("resultCode")) or ""
    result_msg = _optional_str(header.get("resultMsg")) or ""

    body = data.get("body") or {}
    if not isinstance(body, dict):
        # body 없는 경우 — 빈 결과로 처리
        return KecoSearchResponse(
            result_code=result_code,
            result_msg=result_msg,
            page_no=None,
            num_of_rows=None,
            total_count=None,
            items=[],
        )

    page_no = _optional_str(body.get("pageNo"))
    num_of_rows = _optional_str(body.get("numOfRows"))
    total_count = _optional_str(body.get("totalCount"))

    raw_items = body.get("items")
    # items absent, null, [] 모두 0건으로 처리
    if raw_items is None or not isinstance(raw_items, list):
        items = []
    else:
        items = [_parse_chemical_item(i) for i in raw_items if isinstance(i, dict)]

    return KecoSearchResponse(
        result_code=result_code,
        result_msg=result_msg,
        page_no=page_no,
        num_of_rows=num_of_rows,
        total_count=total_count,
        items=items,
    )
