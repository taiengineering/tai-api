"""OBJ-BZI-002 — Bizinfo Canonical Source Normalizer.

Converts a single raw 기업마당 API item dict into NormalizedSourceRecord.
Pure function — no DB, no network, no storage.

Confirmed source fields (SRC-A):
  PROGRAM: pblancId, pblancNm, pblancUrl, reqstBeginEndDe, jrsdInsttNm
  EVENT:   eventInfoId, nttNm, bizinfoUrl, eventBeginEndDe, rceptPd, originOrg

EVIDENCE_PENDING fields (field name unverified in independent review):
  PROGRAM: origin_url field name
  EVENT:   orginlUrlAdres (Claude Code SRC-A report, GPT independent confirm pending)
  Both:    source_updated_at (no API field confirmed)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Format → expected length map (strict digit count enforcement)
# ---------------------------------------------------------------------------

_FMT_LENGTHS: dict[str, int] = {"%Y-%m-%d": 10, "%Y%m%d": 8}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BIZINFO_ALLOWED_SCHEME = "https"
_BIZINFO_ALLOWED_HOST = "www.bizinfo.go.kr"
_BIZINFO_BASE = "https://www.bizinfo.go.kr"

_ALLOWED_EXTERNAL_SCHEMES = frozenset({"https", "http"})


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DateRange:
    """A parsed date pair. Either or both sides may be None."""
    start: Optional[date]
    end:   Optional[date]
    # "start_missing" | "end_missing" | "format_error" | "date_reversed"
    parse_note: Optional[str] = None


@dataclass(frozen=True)
class ParseFailure:
    """Returned instead of NormalizedSourceRecord when mandatory fields are absent."""
    source_kind: Literal["PROGRAM", "EVENT"]
    raw_key:     Optional[str]   # pblancId / eventInfoId if present
    reasons:     tuple[str, ...]


@dataclass
class NormalizedSourceRecord:
    # -- Required fields (no defaults) -------------------------------------
    source_kind:  Literal["PROGRAM", "EVENT"]
    source_id:    Literal["BIZINFO_PROGRAM", "BIZINFO_EVENT"]
    source_key:   str            # pblancId / eventInfoId verbatim
    title:        str
    source_org:   Optional[str]
    origin_url:   Optional[str]  # validated external origin URL or None
    bizinfo_url:  Optional[str]  # validated absolute bizinfo.go.kr URL or None
    retrieved_at: datetime       # injected by caller — never fabricated

    # -- Optional fields (defaults allowed after retrieved_at) --------------
    application_period: Optional[DateRange] = None   # PROGRAM only
    event_period:       Optional[DateRange] = None   # EVENT only
    reception_period:   Optional[DateRange] = None   # EVENT only

    # Set only when API explicitly provides a modification timestamp.
    # NEVER substitute retrieved_at here.
    source_updated_at:  Optional[datetime] = None

    parse_errors:     list[str] = field(default_factory=list)
    evidence_pending: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def normalize_bizinfo_record(
    kind: Literal["PROGRAM", "EVENT"],
    raw: dict,
    retrieved_at: datetime,
) -> NormalizedSourceRecord | ParseFailure:
    """Normalize one raw bizinfo API item.

    Returns ParseFailure when source_key or title is missing/blank.
    Returns NormalizedSourceRecord (possibly with parse_errors) otherwise.

    raw must be a single item dict — list handling is the caller's responsibility.
    retrieved_at must be supplied by the caller; never substituted for source_updated_at.
    """
    # R1-01: reject unknown kind — never silently fall through to EVENT
    if kind not in ("PROGRAM", "EVENT"):
        return ParseFailure(
            source_kind="PROGRAM",
            raw_key=None,
            reasons=("invalid_source_kind",),
        )
    if kind == "PROGRAM":
        return _normalize_program(raw, retrieved_at)
    return _normalize_event(raw, retrieved_at)


# ---------------------------------------------------------------------------
# Internal normalizers
# ---------------------------------------------------------------------------


def _normalize_program(raw: dict, retrieved_at: datetime) -> NormalizedSourceRecord | ParseFailure:
    source_key = _str_or_none(raw.get("pblancId"))
    title      = _str_or_none(raw.get("pblancNm"))

    if not source_key or not title:
        reasons = []
        if not source_key:
            reasons.append("missing_source_key:pblancId")
        if not title:
            reasons.append("missing_title:pblancNm")
        return ParseFailure(
            source_kind="PROGRAM",
            raw_key=source_key,
            reasons=tuple(reasons),
        )

    errors:   list[str] = []
    evidence: list[str] = []

    # pblancUrl: SRC-A confirmed as absolute URL
    bizinfo_url, url_err = _validate_bizinfo_url(raw.get("pblancUrl"), allow_relative=False)
    if url_err:
        errors.append(f"bizinfo_url:{url_err}")

    # PROGRAM origin URL field name not independently confirmed
    raw_origin = raw.get("orginlUrlAdres") or raw.get("originUrl")
    origin_url, origin_err = _validate_external_url(raw_origin)
    if raw_origin and origin_err:
        errors.append(f"origin_url:{origin_err}")
    evidence.append("program_origin_url_field_unverified")

    application_period = _parse_date_range_hyphened(raw.get("reqstBeginEndDe"), errors)

    source_org = _str_or_none(raw.get("jrsdInsttNm")) or _str_or_none(raw.get("excInsttNm"))

    # source_updated_at: no confirmed API field
    evidence.append("source_updated_at_field_not_verified")

    return NormalizedSourceRecord(
        source_kind="PROGRAM",
        source_id="BIZINFO_PROGRAM",
        source_key=source_key,
        title=title,
        source_org=source_org,
        origin_url=origin_url,
        bizinfo_url=bizinfo_url,
        retrieved_at=retrieved_at,
        application_period=application_period,
        source_updated_at=None,
        parse_errors=errors,
        evidence_pending=evidence,
    )


def _normalize_event(raw: dict, retrieved_at: datetime) -> NormalizedSourceRecord | ParseFailure:
    source_key = _str_or_none(raw.get("eventInfoId"))
    title      = _str_or_none(raw.get("nttNm"))

    if not source_key or not title:
        reasons = []
        if not source_key:
            reasons.append("missing_source_key:eventInfoId")
        if not title:
            reasons.append("missing_title:nttNm")
        return ParseFailure(
            source_kind="EVENT",
            raw_key=source_key,
            reasons=tuple(reasons),
        )

    errors:   list[str] = []
    evidence: list[str] = []

    # bizinfoUrl: SRC-A confirmed as relative path
    bizinfo_url, url_err = _validate_bizinfo_url(raw.get("bizinfoUrl"), allow_relative=True)
    if url_err:
        errors.append(f"bizinfo_url:{url_err}")

    # orginlUrlAdres: field name unverified by GPT independent review
    raw_origin = raw.get("orginlUrlAdres")
    origin_url, origin_err = _validate_external_url(raw_origin)
    if raw_origin and origin_err:
        errors.append(f"origin_url:{origin_err}")
    evidence.append("event_origin_url_field_name_unverified")

    event_period     = _parse_date_range_compact(raw.get("eventBeginEndDe"), errors)
    reception_period = _parse_date_range_mixed(raw.get("rceptPd"), errors)

    source_org = _str_or_none(raw.get("originOrg"))

    evidence.append("source_updated_at_field_not_verified")

    return NormalizedSourceRecord(
        source_kind="EVENT",
        source_id="BIZINFO_EVENT",
        source_key=source_key,
        title=title,
        source_org=source_org,
        origin_url=origin_url,
        bizinfo_url=bizinfo_url,
        retrieved_at=retrieved_at,
        event_period=event_period,
        reception_period=reception_period,
        source_updated_at=None,
        parse_errors=errors,
        evidence_pending=evidence,
    )


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def _validate_bizinfo_url(
    raw: object,
    *,
    allow_relative: bool,
) -> tuple[Optional[str], Optional[str]]:
    """Validate and normalize a bizinfo.go.kr URL.

    Returns (url_or_None, error_code_or_None).
    Error codes are fixed strings — never include the raw URL value.
    """
    if not raw or not isinstance(raw, str):
        return None, None
    raw = raw.strip()
    if not raw:
        return None, None

    if allow_relative and raw.startswith("/"):
        absolute = _BIZINFO_BASE + raw
        return absolute, None

    # R1-03: guard against malformed URLs that urlsplit cannot parse
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None, "malformed_url"

    # Block userinfo (user@host) — possible credential exposure
    if parsed.username or parsed.password:
        return None, "userinfo_in_url"

    if parsed.scheme != _BIZINFO_ALLOWED_SCHEME:
        return None, "non_https_scheme"

    # Exact host match — prevents subdomain hijack and lookalike attacks
    if parsed.netloc != _BIZINFO_ALLOWED_HOST:
        return None, "unexpected_host"

    if not parsed.path:
        return None, "empty_path"

    return raw, None


def _validate_external_url(raw: object) -> tuple[Optional[str], Optional[str]]:
    """Validate an external origin URL (not restricted to bizinfo domain).

    Allows http/https only. Blocks userinfo, non-web schemes.
    Error codes are fixed strings — never include raw URL value.
    """
    if not raw or not isinstance(raw, str):
        return None, None
    raw = raw.strip()
    if not raw:
        return None, None

    # R1-03: guard against malformed URLs that urlsplit cannot parse
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None, "malformed_url"

    if parsed.username or parsed.password:
        return None, "userinfo_in_url"

    if parsed.scheme not in _ALLOWED_EXTERNAL_SCHEMES:
        return None, "non_web_scheme"

    # R1-03: require a real domain (netloc must contain a dot)
    if not parsed.netloc or "." not in parsed.netloc:
        return None, "missing_host"

    return raw, None


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def _parse_date_range_hyphened(
    raw: object,
    errors: list[str],
) -> Optional[DateRange]:
    """Parse 'YYYY-MM-DD ~ YYYY-MM-DD' (PROGRAM reqstBeginEndDe)."""
    if raw is None or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        # R1-02: record an error — empty application period is noteworthy
        errors.append("reqstBeginEndDe:empty")
        return None
    return _split_and_parse(raw, errors, fmt="%Y-%m-%d", field_tag="reqstBeginEndDe")


def _parse_date_range_compact(
    raw: object,
    errors: list[str],
) -> Optional[DateRange]:
    """Parse 'YYYYMMDD ~ YYYYMMDD' (EVENT eventBeginEndDe, no hyphens)."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    return _split_and_parse(raw, errors, fmt="%Y%m%d", field_tag="eventBeginEndDe")


def _parse_date_range_mixed(
    raw: object,
    errors: list[str],
) -> Optional[DateRange]:
    """Parse rceptPd. Tolerates missing start ('~ YYYY-MM-DD') or end.

    Tries both hyphenated and compact formats for each side independently.
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None

    parts = [p.strip() for p in raw.split("~")]
    if len(parts) != 2:
        errors.append("rceptPd:unexpected_format")
        return DateRange(None, None, parse_note="format_error")

    left, right = parts

    start: Optional[date] = None
    end:   Optional[date]   = None
    note:  Optional[str]  = None

    if left:
        start = _try_parse_date(left)
        if start is None:
            errors.append("rceptPd:start_parse_error")
            note = "format_error"
    else:
        note = "start_missing"

    if right:
        end = _try_parse_date(right)
        if end is None:
            errors.append("rceptPd:end_parse_error")
            note = "format_error"
    else:
        if note != "format_error":
            note = "end_missing"

    if start and end and end < start:
        note = "date_reversed"

    return DateRange(start=start, end=end, parse_note=note)


def _split_and_parse(
    raw: str,
    errors: list[str],
    *,
    fmt: str,
    field_tag: str,
) -> Optional[DateRange]:
    parts = [p.strip() for p in raw.split("~")]
    if len(parts) != 2:
        errors.append(f"{field_tag}:unexpected_format")
        return DateRange(None, None, parse_note="format_error")

    left, right = parts
    start = _try_parse_date(left, fmt)
    end   = _try_parse_date(right, fmt)

    if start is None:
        errors.append(f"{field_tag}:start_parse_error")
    if end is None:
        errors.append(f"{field_tag}:end_parse_error")

    if start is None or end is None:
        return DateRange(start, end, parse_note="format_error")

    if end < start:
        return DateRange(start, end, parse_note="date_reversed")

    return DateRange(start=start, end=end)


def _try_parse_date(s: str, fmt: str = "") -> Optional[date]:
    s = s.strip()
    if not s:
        return None
    candidates = [fmt] if fmt else ["%Y-%m-%d", "%Y%m%d"]
    for f in candidates:
        # R1-04: enforce exact character length before strptime
        # Python parses "2026111" as 2026-11-01 with %Y%m%d — reject it
        expected_len = _FMT_LENGTHS.get(f)
        if expected_len is not None and len(s) != expected_len:
            continue
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _str_or_none(value: object) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
