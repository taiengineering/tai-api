"""WO-CHEM-SEO-PREVIEW-LIVE-001 — deterministic preview manifest builder.

Reads the CHEM-04 hydration artifact (responses.jsonl — one JSON record
per (chemId, sectionNo)) and produces a deterministic membership manifest
listing only chemicals that have all 16 sections. Partial chemicals are
excluded whole (WO §5 "부분 section 노출 금지"). The manifest is signed
with SHA256 so downstream steps (CHEM-08 materialize / CHEM-10 promote)
can bind against a fixed input.

No DB I/O. No live API. No artifact mutation. Read-only.

Usage:
    python -m tools.chem_seo_preview.build_manifest \\
        --responses-jsonl /path/to/responses.jsonl \\
        --out docs/chem/seo-preview-manifest.json

    # verify a previously-written manifest against the current artifact
    python -m tools.chem_seo_preview.build_manifest \\
        --responses-jsonl /path/to/responses.jsonl \\
        --check docs/chem/seo-preview-manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    SEO_PREVIEW_REQUIRED_SECTION_COUNT,
    SUCCESS_RESULT_CODES,
)
from services.kosha_msds.hash import section_hash as _chem05_section_hash

WO_CODE = "WO-CHEM-SEO-PREVIEW-LIVE-001"
# PATCH-1 rev: fail-closed on duplicate (chem_id, section_no) and on source
# contract failures. Manifest is not written when either occurs. Bumped so
# consumers can detect the semantic change from generator_version=1.
GENERATOR_VERSION = "2"


class ManifestBuildError(SystemExit):
    """Non-zero exit for fail-closed manifest build failures.

    PATCH-1 (WO-CHEM-SEO-PREVIEW-LIVE-001 §4/§21): the builder MUST refuse
    to produce a manifest whenever the source hydration artifact violates
    the SEO publication source contract. No silent skip, no last-write-wins.
    """


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_bytes(obj) -> bytes:
    """Canonical JSON encoding: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _canonical_section_hash(items) -> str:
    """SHA256 over the canonical items array of one section response.

    PATCH-1: delegates to services.kosha_msds.hash.section_hash so the
    SEO manifest and CHEM-05's plan compute the same value for the same
    items. Without this, the two producers disagree and the bridge cannot
    bind SEO membership to a materialize plan.
    """
    return _chem05_section_hash(list(items) if isinstance(items, list) else [])


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"BLOCKED: {path}:{lineno} is not valid JSON: {exc}"
                ) from exc


def _classify_row(row: dict) -> tuple[str | None, int | None, list | None, str | None]:
    """Return (chem_id, section_no, items, contract_failure_reason).

    PATCH-1: any contract violation is surfaced as a reason string;
    build_manifest counts these and refuses to emit when any are found.
    Silent skip is no longer permitted (WO §21 P4 + Source Contract Defense).
    """
    cid = row.get("chemId")
    sno = row.get("sectionNo")
    if not isinstance(cid, str) or not cid:
        return None, None, None, "INVALID_CHEM_ID"
    if not isinstance(sno, int) or isinstance(sno, bool):
        return cid, None, None, "INVALID_SECTION_NO"
    if sno not in ALLOWED_SECTIONS:
        return cid, sno, None, "INVALID_SECTION_NO"
    rc = row.get("result_code")
    if rc is not None and rc not in SUCCESS_RESULT_CODES:
        return cid, sno, None, "INVALID_RESULT_CODE"
    if row.get("authoritative_verified") is False:
        return cid, sno, None, "NOT_AUTHORITATIVE_VERIFIED"
    items = row.get("items") or []
    if not isinstance(items, list):
        return cid, sno, None, "INVALID_ITEMS_TYPE"
    return cid, sno, items, None


def build_manifest(responses_path: Path) -> dict:
    """Build the SEO preview manifest — fail-closed.

    Raises ManifestBuildError (SystemExit) whenever the source hydration
    artifact violates the SEO publication source contract:
      * duplicate (chem_id, section_no) pairs → BLOCK
      * invalid chemId / sectionNo / result_code → BLOCK
      * authoritative_verified == false → BLOCK
      * malformed items type → BLOCK

    Returns a dict with:
      * wo, generator_version, publication_scope
      * source: {responses_path, source_responses, responses_sha256}
      * census: {unique_chemicals, complete_chemicals, preview_sections,
                 excluded_chemicals, excluded_chem_ids,
                 section_count_distribution,
                 duplicate_pairs, source_contract_failures}
      * chemicals: sorted list of {chem_id, section_count, section_hashes_sha256}
      * manifest_sha256: self-hash over the canonicalized dict with the
                        manifest_sha256 field held at empty string
    """
    if not responses_path.exists():
        raise SystemExit(f"BLOCKED: responses path not found: {responses_path}")

    responses_sha = _file_sha256(responses_path)

    per_pair_items: dict[tuple[str, int], list] = {}
    duplicate_pairs: list[tuple[str, int]] = []
    contract_failures: list[dict] = []
    total = 0
    for lineno, row in enumerate(_iter_jsonl(responses_path), start=1):
        total += 1
        cid, sno, items, failure = _classify_row(row)
        if failure is not None:
            contract_failures.append({
                "lineno": lineno,
                "reason": failure,
                "chem_id": cid,
                "section_no": sno,
            })
            continue
        key = (cid, sno)
        if key in per_pair_items:
            duplicate_pairs.append(key)
            continue  # do NOT overwrite; last-write-wins is forbidden
        per_pair_items[key] = items

    # Fail-closed: if either duplicate pairs or source contract failures were
    # found, refuse to emit a manifest. This is the PATCH-B/§21-P4 contract.
    if duplicate_pairs or contract_failures:
        detail = {
            "duplicate_pairs": [
                {"chem_id": c, "section_no": s} for (c, s) in duplicate_pairs[:10]
            ],
            "duplicate_pair_count": len(duplicate_pairs),
            "source_contract_failures_sample": contract_failures[:10],
            "source_contract_failure_count": len(contract_failures),
        }
        raise ManifestBuildError(
            "BLOCKED: SEO preview manifest cannot be built from an artifact with "
            "duplicate (chem_id, section_no) pairs or source contract failures. "
            f"details={json.dumps(detail, ensure_ascii=False)}"
        )

    # Regroup by chemical.
    sections_by_chem: dict[str, dict[int, list]] = defaultdict(dict)
    for (cid, sno), items in per_pair_items.items():
        sections_by_chem[cid][sno] = items

    complete: list[dict] = []
    excluded_ids: list[str] = []
    section_count_distribution: dict[int, int] = defaultdict(int)

    for cid, sec_map in sections_by_chem.items():
        section_count_distribution[len(sec_map)] += 1
        has_all = all(n in sec_map for n in ALLOWED_SECTIONS)
        if not has_all or len(sec_map) != SEO_PREVIEW_REQUIRED_SECTION_COUNT:
            excluded_ids.append(cid)
            continue
        # Deterministic per-chemical binding: concat section hashes 1..16.
        parts = []
        for n in ALLOWED_SECTIONS:
            parts.append(_canonical_section_hash(sec_map[n]))
        chem_hash = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        complete.append({
            "chem_id": cid,
            "section_count": SEO_PREVIEW_REQUIRED_SECTION_COUNT,
            "section_hashes_sha256": chem_hash,
        })

    complete.sort(key=lambda r: r["chem_id"])
    excluded_ids.sort()

    manifest = {
        "wo": WO_CODE,
        "generator_version": GENERATOR_VERSION,
        "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
        "source": {
            "responses_path": str(responses_path.name),
            "source_responses": total,
            "responses_sha256": responses_sha,
        },
        "census": {
            "unique_chemicals": len(sections_by_chem),
            "complete_chemicals": len(complete),
            "preview_sections": len(complete) * SEO_PREVIEW_REQUIRED_SECTION_COUNT,
            "excluded_chemicals": len(excluded_ids),
            "excluded_chem_ids": excluded_ids,
            "section_count_distribution": {
                str(k): section_count_distribution[k]
                for k in sorted(section_count_distribution)
            },
            "duplicate_pairs": 0,           # PATCH-1: fail-closed if > 0
            "source_contract_failures": 0,  # PATCH-1: fail-closed if > 0
        },
        "chemicals": complete,
        "manifest_sha256": "",  # placeholder for self-hash
    }
    self_hash = hashlib.sha256(_canonical_bytes(manifest)).hexdigest()
    manifest["manifest_sha256"] = self_hash
    return manifest


def _write_manifest(manifest: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Canonical write: sort keys, no whitespace but include trailing newline.
    payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    out_path.write_text(payload + "\n", encoding="utf-8")


def _cmd_write(args) -> int:
    manifest = build_manifest(Path(args.responses_jsonl))
    _write_manifest(manifest, Path(args.out))
    print(json.dumps({
        "action": "write",
        "out": args.out,
        "manifest_sha256": manifest["manifest_sha256"],
        "complete_chemicals": manifest["census"]["complete_chemicals"],
        "preview_sections": manifest["census"]["preview_sections"],
        "excluded_chem_ids": manifest["census"]["excluded_chem_ids"],
    }, ensure_ascii=False, indent=2))
    return 0


def _cmd_check(args) -> int:
    fresh = build_manifest(Path(args.responses_jsonl))
    on_disk = json.loads(Path(args.check).read_text(encoding="utf-8"))
    if fresh["manifest_sha256"] != on_disk.get("manifest_sha256"):
        print(json.dumps({
            "action": "check",
            "verdict": "MISMATCH",
            "computed_sha256": fresh["manifest_sha256"],
            "on_disk_sha256": on_disk.get("manifest_sha256"),
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({
        "action": "check",
        "verdict": "MATCH",
        "manifest_sha256": fresh["manifest_sha256"],
        "complete_chemicals": fresh["census"]["complete_chemicals"],
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--responses-jsonl", required=True,
                   help="Path to CHEM-04 responses.jsonl (read-only).")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--out", help="Write manifest JSON to this path.")
    grp.add_argument("--check", help="Verify an existing manifest against the artifact.")
    args = p.parse_args(argv)
    if args.out:
        return _cmd_write(args)
    return _cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
