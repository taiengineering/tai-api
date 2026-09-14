"""PATCH-4 secondary bootstrap identity seed.

Official source is not this dataset. Role = BOOTSTRAP IDENTITY SEED.
Section/braille/translated body never go to a production writer.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from services.kosha_msds.identity import format_numeric_chem_id, normalize_chem_id
from services.time import now_kst, serialize_external_utc

CHEM_ID_RE = re.compile(r"^\d{6}$")
IDENTITY_FIELDS = ("chem_id", "name_ko", "cas_no", "name_en")
BLOCKED_CONTENT_FIELDS = ("sections", "text_ko", "braille", "total_text_chars", "total_braille_chars")
ProductionWriter = Callable[..., object]


class BootstrapSeedError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BootstrapIdentity:
    chem_id: str
    cas_no: Optional[str]
    name_ko: Optional[str]
    name_en: Optional[str]
    source_dataset_revision: str

    def as_row(self) -> dict[str, Optional[str]]:
        return {
            "chemId": self.chem_id,
            "casNo": self.cas_no,
            "nameKo": self.name_ko,
            "nameEn": self.name_en,
            "sourceDatasetRevision": self.source_dataset_revision,
        }


def optional_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def require_padded_chem_id(value: object) -> str:
    cid = normalize_chem_id(str(value) if value is not None else None)
    if not cid:
        raise BootstrapSeedError("CHEM_ID_NULL", "chemId is null")
    if not CHEM_ID_RE.fullmatch(cid):
        raise BootstrapSeedError("CHEM_ID_INVALID", f"chemId is not 6-digit: {cid}")
    if cid != format_numeric_chem_id(int(cid)):
        raise BootstrapSeedError("CHEM_ID_LEADING_ZERO", f"chemId lost leading zeros: {cid}")
    return cid


def identity_from_raw(raw: dict, *, revision: str) -> BootstrapIdentity:
    for blocked in BLOCKED_CONTENT_FIELDS:
        # Content may exist on the source record; it is dropped, never forwarded.
        raw.get(blocked)
    return BootstrapIdentity(
        chem_id=require_padded_chem_id(raw.get("chem_id") or raw.get("chemId")),
        cas_no=optional_text(raw.get("cas_no") or raw.get("casNo")),
        name_ko=optional_text(raw.get("name_ko") or raw.get("nameKo")),
        name_en=optional_text(raw.get("name_en") or raw.get("nameEn")),
        source_dataset_revision=revision,
    )


def load_identity_rows(path: Path, *, revision: str) -> list[BootstrapIdentity]:
    rows: list[BootstrapIdentity] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            identity = identity_from_raw(rec, revision=revision)
            if identity.chem_id in seen:
                raise BootstrapSeedError("DUPLICATE_CHEM_ID", f"duplicate chemId={identity.chem_id}")
            seen.add(identity.chem_id)
            rows.append(identity)
    return rows


def seed_stats(rows: list[BootstrapIdentity]) -> dict[str, int]:
    cas_values = [r.cas_no for r in rows if r.cas_no]
    cas_dup = len(cas_values) - len(set(cas_values))
    return {
        "total_rows": len(rows),
        "unique_chem_id": len({r.chem_id for r in rows}),
        "duplicate_chem_id": 0,
        "invalid_chem_id": 0,
        "null_chem_id": 0,
        "cas_null": sum(1 for r in rows if not r.cas_no),
        "cas_duplicate": cas_dup,
        "name_null": sum(1 for r in rows if not r.name_ko),
    }


def extract_identity_jsonl(
    source_lines: Iterable[bytes | str],
    dest: Path,
    *,
    revision: str,
    production_writer: Optional[ProductionWriter] = None,
) -> tuple[int, dict[str, int]]:
    del production_writer  # identity bootstrap never calls a production writer
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    hasher = hashlib.sha256()
    with dest.open("w", encoding="utf-8") as out:
        for raw_line in source_lines:
            if isinstance(raw_line, bytes):
                hasher.update(raw_line if raw_line.endswith(b"\n") else raw_line + b"\n")
                line = raw_line.decode("utf-8")
            else:
                hasher.update((raw_line if raw_line.endswith("\n") else raw_line + "\n").encode("utf-8"))
                line = raw_line
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            identity = identity_from_raw(rec, revision=revision)
            row = identity.as_row()
            if any(key in row for key in ("sections", "text_ko", "braille")):
                raise BootstrapSeedError("CONTENT_LEAK", "section content leaked into identity seed")
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count, {"sha256_streamed_lines": 1}


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload.setdefault("written_at", serialize_external_utc(now_kst()))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = unicodedata.normalize("NFC", value).strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def crosscheck_live_discovered(live_ids: Iterable[str], seed_ids: set[str]) -> tuple[int, tuple[str, ...]]:
    live = [cid for cid in live_ids]
    missing = tuple(sorted(cid for cid in live if cid not in seed_ids))
    return len(live) - len(missing), missing


def extract_identity_from_url(
    url: str,
    dest: Path,
    *,
    revision: str,
    expected_sha256: Optional[str] = None,
    production_writer: Optional[ProductionWriter] = None,
) -> dict[str, object]:
    del production_writer
    from urllib.request import Request, urlopen

    dest.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    count = 0
    invalid = 0
    seen: set[str] = set()
    observed_keys: Optional[list[str]] = None
    req = Request(url, headers={"User-Agent": "TAI-CHEM04-bootstrap/1.0"})
    with urlopen(req, timeout=120) as resp, dest.open("w", encoding="utf-8") as out:
        buf = b""
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                rec = json.loads(line)
                if observed_keys is None:
                    observed_keys = sorted(rec.keys())
                try:
                    ident = identity_from_raw(rec, revision=revision)
                except BootstrapSeedError as exc:
                    if exc.code in {"CHEM_ID_INVALID", "CHEM_ID_NULL", "CHEM_ID_LEADING_ZERO", "DUPLICATE_CHEM_ID"}:
                        invalid += 1
                        continue
                    raise
                if ident.chem_id in seen:
                    invalid += 1
                    continue
                seen.add(ident.chem_id)
                out.write(json.dumps(ident.as_row(), ensure_ascii=False) + "\n")
                count += 1
                if count % 5000 == 0:
                    print(f"SEED rows={count} invalid={invalid}", flush=True)
        if buf.strip():
            rec = json.loads(buf)
            if observed_keys is None:
                observed_keys = sorted(rec.keys())
            try:
                ident = identity_from_raw(rec, revision=revision)
            except BootstrapSeedError as exc:
                if exc.code in {"CHEM_ID_INVALID", "CHEM_ID_NULL", "CHEM_ID_LEADING_ZERO"}:
                    invalid += 1
                    ident = None
                else:
                    raise
            else:
                if ident.chem_id in seen:
                    invalid += 1
                    ident = None
            if ident is not None:
                seen.add(ident.chem_id)
                out.write(json.dumps(ident.as_row(), ensure_ascii=False) + "\n")
                count += 1
    digest = hasher.hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise BootstrapSeedError("SHA256_MISMATCH", "downloaded dataset hash mismatch")
    return {
        "rows": count,
        "invalid": invalid,
        "sha256": digest,
        "observed_fields": observed_keys or [],
        "artifact_path": str(dest),
    }


def _accept_identity(rec: dict, *, revision: str, seen: set[str]) -> tuple[Optional[BootstrapIdentity], bool]:
    try:
        ident = identity_from_raw(rec, revision=revision)
    except BootstrapSeedError as exc:
        if exc.code in {"CHEM_ID_INVALID", "CHEM_ID_NULL", "CHEM_ID_LEADING_ZERO"}:
            return None, True
        raise
    if ident.chem_id in seen:
        return None, True
    seen.add(ident.chem_id)
    return ident, False


def extract_identity_from_path(
    src: Path,
    dest: Path,
    *,
    revision: str,
    expected_sha256: Optional[str] = None,
    max_rows: Optional[int] = None,
    production_writer: Optional[ProductionWriter] = None,
) -> dict[str, object]:
    """Local-file extract. Cursor probe uses a fixture + max_rows. Full 48k is LOCAL."""
    del production_writer
    dest.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    count = 0
    invalid = 0
    seen: set[str] = set()
    observed_keys: Optional[list[str]] = None
    reached_end = False
    with src.open("rb") as fh, dest.open("w", encoding="utf-8") as out:
        buf = b""
        while True:
            chunk = fh.read(256 * 1024)
            if not chunk:
                reached_end = True
                break
            hasher.update(chunk)
            buf += chunk
            stop = False
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                rec = json.loads(line)
                if observed_keys is None:
                    observed_keys = sorted(rec.keys())
                ident, skipped = _accept_identity(rec, revision=revision, seen=seen)
                if skipped:
                    invalid += 1
                elif ident is not None:
                    out.write(json.dumps(ident.as_row(), ensure_ascii=False) + "\n")
                    count += 1
                    if count % 5000 == 0:
                        print(f"SEED rows={count} invalid={invalid}", flush=True)
                if max_rows is not None and (count + invalid) >= max_rows:
                    stop = True
                    break
            if stop:
                break
        if reached_end and buf.strip() and (max_rows is None or (count + invalid) < max_rows):
            rec = json.loads(buf)
            if observed_keys is None:
                observed_keys = sorted(rec.keys())
            ident, skipped = _accept_identity(rec, revision=revision, seen=seen)
            if skipped:
                invalid += 1
            elif ident is not None:
                out.write(json.dumps(ident.as_row(), ensure_ascii=False) + "\n")
                count += 1
    digest = hasher.hexdigest() if reached_end and max_rows is None else None
    if expected_sha256 and digest and digest != expected_sha256:
        raise BootstrapSeedError("SHA256_MISMATCH", "local dataset hash mismatch")
    return {
        "rows": count,
        "invalid": invalid,
        "sha256": digest,
        "observed_fields": observed_keys or [],
        "artifact_path": str(dest),
        "source_path": str(src),
        "partial": max_rows is not None and not reached_end,
    }
