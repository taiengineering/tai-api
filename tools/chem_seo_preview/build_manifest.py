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

WO_CODE = "WO-CHEM-SEO-PREVIEW-LIVE-001"
GENERATOR_VERSION = "1"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_bytes(obj) -> bytes:
    """Canonical JSON encoding: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _canonical_section_hash(items: list) -> str:
    """SHA256 over the canonical items array of one section response.

    The KOSHA v1.2 items array is a list of {msdsItemCode, msdsItemNameKor,
    itemDetail, ordrIdx, lev, upMsdsItemCode} objects. To be deterministic
    across producer/consumer we sort each item's keys and take the array
    order as-is (the API returns items in a stable ordrIdx order).
    """
    canonical = _canonical_bytes(items if isinstance(items, list) else [])
    return hashlib.sha256(canonical).hexdigest()


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


def build_manifest(responses_path: Path) -> dict:
    """Build the SEO preview manifest.

    Returns a dict with:
      * wo, generator_version, publication_scope
      * source: {responses_path, source_responses, responses_sha256}
      * census: {unique_chemicals, complete_chemicals, preview_sections,
                 excluded_chemicals, excluded_chem_ids, section_count_distribution}
      * chemicals: sorted list of {chem_id, section_count, section_hashes_sha256}
      * manifest_sha256: self-hash over the canonicalized dict with the
                        manifest_sha256 field held at empty string
    """
    if not responses_path.exists():
        raise SystemExit(f"BLOCKED: responses path not found: {responses_path}")

    responses_sha = _file_sha256(responses_path)

    # (chem_id, section_no) → items array (last write wins; artifact is expected
    # to have no duplicates but we defensively de-dup by (chem_id, section_no)).
    per_pair_items: dict[tuple[str, int], list] = {}
    result_bad = 0
    authv_bad = 0
    total = 0
    for row in _iter_jsonl(responses_path):
        total += 1
        cid = row.get("chemId")
        sno = row.get("sectionNo")
        if not isinstance(cid, str) or not isinstance(sno, int):
            continue
        if sno not in ALLOWED_SECTIONS:
            continue
        rc = row.get("result_code")
        if rc is not None and rc not in SUCCESS_RESULT_CODES:
            result_bad += 1
            continue
        if row.get("authoritative_verified") is False:
            authv_bad += 1
            continue
        per_pair_items[(cid, sno)] = row.get("items") or []

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
            "result_code_dropped": result_bad,
            "authoritative_verified_dropped": authv_bad,
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
