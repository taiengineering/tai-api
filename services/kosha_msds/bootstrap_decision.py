"""Decision-gate helpers: local sample, XML flatten, no production writer."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

from services.kosha_msds.contract import ALLOWED_SECTIONS, CONTENT_SECONDARY_COMPLETE
from services.kosha_msds.current_index import OfficialCurrentRow

GHS_PICTOGRAMS = {
    "GHS01": "폭발성",
    "GHS02": "인화성",
    "GHS03": "산화성",
    "GHS04": "고압가스",
    "GHS05": "부식성",
    "GHS06": "급성독성",
    "GHS07": "경고(피부자극/호흡기자극)",
    "GHS08": "건강유해성(발암성/생식독성)",
    "GHS09": "수생환경유해성",
}
GHS_GIF_RE = re.compile(r"(GHS\d{2})\.gif")
GHS_CODE_RE = re.compile(r"(GHS\d{2})(?:\.gif)?")
SPECIAL_NAME_RE = re.compile(r"[^\w가-힣\s(),.\-/]")
S6_PREFERRED = ("001008", "000001", "047134")


def flatten_msds_xml(xml_data: str) -> str:
    """Reproduce secondary export_hf_dataset.extract_section_text (measured)."""
    if not xml_data or xml_data.strip() in {"", "-"}:
        return ""
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for item in root.findall(".//item"):
        label = (item.findtext("msdsItemNameKor") or "").strip()
        detail = item.findtext("itemDetail") or ""
        if not detail or detail == "자료없음":
            continue
        cleaned = _clean_msds_text(label, detail)
        parts.append(f"{label}: {cleaned}" if label else cleaned)
    return "\n".join(parts)


def _clean_msds_text(label: str, detail: str) -> str:
    if "그림문자" in label:
        meanings = []
        for part in detail.split("|"):
            part = part.strip()
            match = GHS_CODE_RE.match(part)
            if match:
                meanings.append(GHS_PICTOGRAMS.get(match.group(1), match.group(1)))
            elif part:
                meanings.append(part)
        return ", ".join(meanings)
    detail = GHS_GIF_RE.sub(lambda m: GHS_PICTOGRAMS.get(m.group(1), m.group(1)), detail)
    return detail.replace("|", ", ")


def normalize_compare_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def classify_pair(secondary: Optional[str], official: Optional[str]) -> str:
    sec_raw = secondary if isinstance(secondary, str) else None
    off_raw = official if isinstance(official, str) else None
    sec_empty = not (sec_raw or "").strip()
    off_empty = not (off_raw or "").strip()
    if sec_raw is None and off_raw is None:
        return "UNVERIFIED"
    if sec_raw is None:
        return "SECONDARY_MISSING"
    if off_raw is None:
        return "UNVERIFIED"
    if sec_empty and off_empty:
        return "SECONDARY_EMPTY"
    if sec_empty and not off_empty:
        return "SECONDARY_EMPTY"
    if off_empty and not sec_empty:
        return "OFFICIAL_EMPTY"
    if sec_raw == off_raw:
        return "EXACT"
    if normalize_compare_text(sec_raw) == normalize_compare_text(off_raw):
        return "NORMALIZED_EQUAL"
    return "CONTENT_DIFFERENT"


def load_coverage_map(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                out[rec["chemId"]] = rec
    return out


def structural_holes_by_section(coverage_rows: Iterable[dict]) -> dict[int, int]:
    counts = {n: 0 for n in ALLOWED_SECTIONS}
    for row in coverage_rows:
        for n in ALLOWED_SECTIONS:
            if row.get(f"section{n:02d}_present") == "MISSING":
                counts[n] += 1
    return counts


def _is_complete(cov: Optional[dict]) -> bool:
    return bool(cov) and cov.get("content_status") == CONTENT_SECONDARY_COMPLETE


def select_sample(
    official: list[OfficialCurrentRow],
    coverage: dict[str, dict],
) -> list[dict[str, object]]:
    complete = [
        row for row in official if row.chem_id and _is_complete(coverage.get(row.chem_id))
    ]
    used: set[str] = set()
    picked: list[dict[str, object]] = []

    def add(row: OfficialCurrentRow, stratum: str) -> None:
        if not row.chem_id or row.chem_id in used:
            return
        used.add(row.chem_id)
        cov = coverage[row.chem_id]
        picked.append(
            {
                "chemId": row.chem_id,
                "stratum": stratum,
                "official_cas": row.official_cas,
                "official_name": row.official_name,
                "official_revision_date": row.official_revision_date,
                "content_status": cov["content_status"],
            }
        )

    by_id = {row.chem_id: row for row in complete}
    for cid in S6_PREFERRED:
        if cid in by_id:
            add(by_id[cid], "S6_KNOWN_VALIDATED")
    for row in sorted(complete, key=lambda r: r.chem_id or ""):
        if len([p for p in picked if p["stratum"] == "S2_CAS_NULL"]) >= 3:
            break
        if not row.official_cas:
            add(row, "S2_CAS_NULL")
    for row in sorted(complete, key=lambda r: r.chem_id or ""):
        if len([p for p in picked if p["stratum"] == "S3_SPECIAL_NAME"]) >= 3:
            break
        if SPECIAL_NAME_RE.search(row.official_name or ""):
            add(row, "S3_SPECIAL_NAME")
    dated = [row for row in complete if row.official_revision_date]
    for row in sorted(dated, key=lambda r: (r.official_revision_date or "", r.chem_id or ""), reverse=True):
        if len([p for p in picked if p["stratum"] == "S4_RECENT_OFFICIAL_DATE"]) >= 3:
            break
        add(row, "S4_RECENT_OFFICIAL_DATE")
    for row in sorted(dated, key=lambda r: (r.official_revision_date or "", r.chem_id or "")):
        if len([p for p in picked if p["stratum"] == "S5_OLD_OFFICIAL_DATE"]) >= 3:
            break
        add(row, "S5_OLD_OFFICIAL_DATE")
    for row in sorted(complete, key=lambda r: r.chem_id or ""):
        if len([p for p in picked if p["stratum"] == "S1_GENERAL_COMPLETE"]) >= 5:
            break
        add(row, "S1_GENERAL_COMPLETE")
    picked.sort(key=lambda r: (str(r["stratum"]), str(r["chemId"])))
    return picked


def extract_secondary_sections(train_jsonl: Path, chem_ids: set[str]) -> dict[str, dict[int, str]]:
    found: dict[str, dict[int, str]] = {cid: {} for cid in chem_ids}
    remaining = set(chem_ids)
    with train_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            if not remaining:
                break
            rec = json.loads(line)
            cid = rec.get("chem_id") or rec.get("chemId")
            if cid not in remaining:
                continue
            for item in rec.get("sections") or []:
                if not isinstance(item, dict):
                    continue
                try:
                    n = int(item.get("section_no") or item.get("sectionNo"))
                except (TypeError, ValueError):
                    continue
                text = item.get("text_ko") if isinstance(item.get("text_ko"), str) else ""
                found[cid][n] = text
            remaining.discard(cid)
    return found


def sample_manifest_hash(rows: list[dict]) -> str:
    payload = [{"chemId": r["chemId"], "stratum": r["stratum"]} for r in rows]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
