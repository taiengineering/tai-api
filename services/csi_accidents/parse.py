"""CSV decode/parse for official CSI file. HTTP charset is ignored."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from typing import Optional

from services.csi_accidents.contract import (
    HEADER_COUNT,
    OFFICIAL_HEADERS,
)


class CsiSyncError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ParseResult:
    headers: list[str]
    rows: list[dict[str, str]]
    malformed_rows: int
    empty_rows: int
    encoding: str = "cp949"


def decode_cp949(data: bytes) -> str:
    """Body decoding is always CP949. HTTP charset=UTF-8 is not used."""
    try:
        return data.decode("cp949")
    except UnicodeDecodeError as e:
        raise CsiSyncError("CP949_DECODE", f"CP949 decode failed: {e}") from e


def parse_csv_text(text: str) -> ParseResult:
    reader = csv.reader(StringIO(text))
    try:
        header = next(reader)
    except StopIteration as e:
        raise CsiSyncError("EMPTY_CSV", "CSV has no header") from e
    if header != list(OFFICIAL_HEADERS):
        raise CsiSyncError(
            "HEADER_MISMATCH",
            f"expected {HEADER_COUNT} official headers, got {len(header)}",
        )
    rows: list[dict[str, str]] = []
    malformed = 0
    empty = 0
    for i, rec in enumerate(reader, start=2):
        if len(rec) == 1 and rec[0] == "":
            empty += 1
            raise CsiSyncError("MALFORMED_CSV", f"empty row at line {i}")
        if len(rec) != HEADER_COUNT:
            malformed += 1
            raise CsiSyncError(
                "MALFORMED_CSV",
                f"width mismatch at line {i}: cols={len(rec)} expected={HEADER_COUNT}",
            )
        rows.append({OFFICIAL_HEADERS[j]: rec[j] for j in range(HEADER_COUNT)})
    if not rows:
        raise CsiSyncError("EMPTY_CSV", "CSV has header but no data rows")
    return ParseResult(
        headers=list(OFFICIAL_HEADERS),
        rows=rows,
        malformed_rows=malformed,
        empty_rows=empty,
        encoding="cp949",
    )


def parse_official_bytes(data: bytes) -> ParseResult:
    return parse_csv_text(decode_cp949(data))


def parse_int_or_none(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    s = raw.strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError:
        return None
