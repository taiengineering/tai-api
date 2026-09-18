"""WO-CHEM-SEO-PREVIEW-LIVE-001 PATCH-A — CHEM-05 plan → SEO preview plan bridge.

Deterministic bridge that filters an existing CHEM-05 materialize plan
(from `artifacts/chem05/`) down to the SEO preview membership defined in
`docs/chem/seo-preview-manifest.json`, then emits a NEW materialize plan
that CHEM-08 can consume with `publication_scope=SEO_PREVIEW`.

The bridge is a pure filter over the existing CHEM-05 output — no new
canonical writer, no new plan builder, no new schema. Every preview
plan chemical row is copied verbatim from the CHEM-05 plan; only the
manifest snapshot metadata and execute_eligible derivation are new.

Design (WO §7 "existing materializer reused"):

  responses.jsonl  ──build_materialize_plan──►  chem05 plan
                                                     │
  responses.jsonl  ──build_manifest──►  SEO manifest │
                                            │        │
                                            └─┬──────┘
                                              ▼
                            build_preview_plan (this tool)
                                              │
                                              ▼
                     preview materialize plan (JSONL + manifest + report)
                                              │
                                              ▼
                                     materialize_writer.preflight(
                                       publication_scope=SEO_PREVIEW)
                                              │
                                              ▼
                                     can_execute = True

Every binding must line up:

  * chem05 manifest.responses_sha256  ==  SEO manifest.source.responses_sha256
  * SEO manifest.chemicals set ⊆ chem05 plan chemicals
  * for each SEO chem_id: chem05 plan bundle has all 16 sections,
                          detail_status == COMPLETE,
                          no duplicate section_no,
                          section_hashes recompute to the same
                          section_hashes_sha256 as the SEO manifest
  * no partial chemical (chemId 432377) may appear

Any mismatch → non-zero exit and NO output files.

Preview manifest metrics_json bindings (WO §7):

    snapshot.metrics_json = {
        "publication_scope": "SEO_PREVIEW",
        "seo_preview_manifest_sha256": "<from SEO manifest>",
        "responses_sha256":            "<from SEO manifest>",
        "seo_preview_expected_chemical_count": <complete_chemicals>,
        "seo_preview_expected_section_count":  <preview_sections>,
        "plan_semantic_sha256": "<self>",        # preview plan's own semantic sha
        "plan_file_sha256":     "<self>",        # preview plan JSONL sha
        "source_plan_semantic_sha256": "<chem05 plan_semantic_sha256>",
        "source_plan_file_sha256":     "<chem05 plan_file_sha256>",
    }

CHEM-10 preflight_publish then passes
    expected_materialize_binding={
        "publication_scope": "SEO_PREVIEW",
        "seo_preview_manifest_sha256": <expected>,
        "responses_sha256":            <expected>,
    }
and BLOCK_MATERIALIZE_BINDING_MISMATCH fires if the runtime snapshot
metrics_json disagrees.

CLI:
    python -m tools.chem_seo_preview.build_preview_plan \\
        --chem05-plan-jsonl artifacts/chem05/materialize_plan.jsonl \\
        --chem05-manifest artifacts/chem05/materialize_manifest.json \\
        --chem05-report artifacts/chem05/materialize_report.json \\
        --seo-manifest docs/chem/seo-preview-manifest.json \\
        --out-dir artifacts/chem_seo_preview/

Output (three files, deterministic):
    <out_dir>/preview_materialize_plan.jsonl
    <out_dir>/preview_materialize_manifest.json
    <out_dir>/preview_materialize_report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Iterable

from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    DETAIL_COMPLETE,
    ENUMERATION_FULL_OFFICIAL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLISH_NOT_PUBLISHED,
    SEO_PREVIEW_REQUIRED_SECTION_COUNT,
)

WO_CODE = "WO-CHEM-SEO-PREVIEW-LIVE-001"
GENERATOR_VERSION = "1"

BLOCK_RESPONSES_SHA_MISMATCH = "RESPONSES_SHA_MISMATCH"
BLOCK_MANIFEST_MEMBER_NOT_IN_PLAN = "MANIFEST_MEMBER_NOT_IN_PLAN"
BLOCK_MEMBER_INCOMPLETE_SECTIONS = "MEMBER_INCOMPLETE_SECTIONS"
BLOCK_MEMBER_DUPLICATE_SECTION = "MEMBER_DUPLICATE_SECTION"
BLOCK_MEMBER_DETAIL_STATUS_NOT_COMPLETE = "MEMBER_DETAIL_STATUS_NOT_COMPLETE"
BLOCK_MEMBER_HASH_MISMATCH = "MEMBER_HASH_MISMATCH"
BLOCK_EXCLUDED_ID_PRESENT = "EXCLUDED_ID_PRESENT_IN_PLAN"
BLOCK_MANIFEST_SHA_INTEGRITY = "MANIFEST_SHA_INTEGRITY_FAILURE"
# PATCH-2: CHEM-05 source-plan integrity guards.
BLOCK_SOURCE_PLAN_FILE_SHA_MISMATCH = "SOURCE_PLAN_FILE_SHA_MISMATCH"
BLOCK_SOURCE_PLAN_SEMANTIC_SHA_MISMATCH = "SOURCE_PLAN_SEMANTIC_SHA_MISMATCH"


class PreviewPlanBuildError(SystemExit):
    """Non-zero exit for fail-closed preview plan build failures."""


def _canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise PreviewPlanBuildError(
                    f"BLOCKED: {path}:{lineno} invalid JSON: {exc}"
                ) from exc


def _canonical_section_hash(items) -> str:
    """Match tools/chem_seo_preview/build_manifest.py._canonical_section_hash."""
    canonical = _canonical_bytes(items if isinstance(items, list) else [])
    return hashlib.sha256(canonical).hexdigest()


def _preview_semantic_hash(chemicals: list[dict]) -> str:
    """Deterministic content sha over the preview plan chemicals.

    Uses the section_hash values already computed by CHEM-05 (canonical
    hash of items after result_code/authoritative_verified checks), so
    the preview plan's semantic hash is stable across producer/consumer.
    """
    projection = []
    for c in sorted(chemicals, key=lambda x: x.get("chem_id") or ""):
        sec_projection = [
            {"section_no": int(s.get("section_no")),
             "section_hash": s.get("section_hash")}
            for s in sorted(c.get("sections") or [], key=lambda s: int(s.get("section_no")))
        ]
        projection.append({
            "chem_id": c.get("chem_id"),
            "source_id": c.get("source_id"),
            "source_key": c.get("source_key"),
            "source_content_hash": c.get("source_content_hash"),
            "identity_status": c.get("identity_status"),
            "detail_status": c.get("detail_status"),
            "sections": sec_projection,
        })
    return hashlib.sha256(_canonical_bytes(projection)).hexdigest()


def _verify_seo_manifest_integrity(seo_manifest: dict) -> None:
    """Recompute the SEO manifest's own SHA to catch on-disk tampering."""
    on_disk_sha = seo_manifest.get("manifest_sha256")
    without = dict(seo_manifest)
    without["manifest_sha256"] = ""
    recomputed = hashlib.sha256(_canonical_bytes(without)).hexdigest()
    if on_disk_sha != recomputed:
        raise PreviewPlanBuildError(
            f"BLOCKED {BLOCK_MANIFEST_SHA_INTEGRITY}: SEO manifest self-SHA "
            f"disagrees. on_disk={on_disk_sha} recomputed={recomputed}"
        )


def build_preview_plan(
    *,
    chem05_plan_jsonl: Path,
    chem05_manifest_json: Path,
    chem05_report_json: Path,
    seo_manifest_json: Path,
) -> dict:
    """Return a dict with the three preview artifacts, without writing.

    Emits:
        {"plan_chemicals": [...],  # sorted by chem_id, only preview members
         "manifest":       {...},  # includes execute_eligible + snapshot.metrics_json
         "report":         {...}}

    Fail-closed on ANY binding mismatch — no partial output.
    """
    for p in (chem05_plan_jsonl, chem05_manifest_json, chem05_report_json, seo_manifest_json):
        if not p.exists():
            raise PreviewPlanBuildError(f"BLOCKED: input not found: {p}")

    chem05_manifest = json.loads(chem05_manifest_json.read_text(encoding="utf-8"))
    chem05_report = json.loads(chem05_report_json.read_text(encoding="utf-8"))
    seo_manifest = json.loads(seo_manifest_json.read_text(encoding="utf-8"))

    _verify_seo_manifest_integrity(seo_manifest)

    # ── PATCH-2 Binding 0: CHEM-05 source-plan file integrity.
    # SHA256 of the plan.jsonl on disk must match the SHA the CHEM-05 producer
    # recorded in materialize_manifest.json. Without this, an attacker (or a
    # dev accident) could edit chemical rows in the JSONL and the bridge's
    # per-section hash check would only catch violations for chem_ids that
    # appear in the SEO manifest — chemicals outside the SEO membership would
    # slip through unnoticed.
    manifest_plan_file_sha = chem05_manifest.get("plan_file_sha256")
    actual_plan_file_sha = _file_sha256(chem05_plan_jsonl)
    if not manifest_plan_file_sha or manifest_plan_file_sha != actual_plan_file_sha:
        raise PreviewPlanBuildError(
            f"BLOCKED {BLOCK_SOURCE_PLAN_FILE_SHA_MISMATCH}: "
            f"actual={actual_plan_file_sha!r} manifest={manifest_plan_file_sha!r}"
        )

    # ── PATCH-2 Binding 0.5: CHEM-05 semantic-hash consistency.
    # The report's plan_sha256 and the manifest's plan_semantic_sha256 refer
    # to the same value produced by services.kosha_msds.materialize.build_plan.
    # If they disagree, the two artifacts describe different plans and we
    # cannot trust either one as source.
    m_semantic = chem05_manifest.get("plan_semantic_sha256")
    r_semantic = chem05_report.get("plan_sha256") or chem05_report.get("plan_semantic_sha256")
    if m_semantic and r_semantic and m_semantic != r_semantic:
        raise PreviewPlanBuildError(
            f"BLOCKED {BLOCK_SOURCE_PLAN_SEMANTIC_SHA_MISMATCH}: "
            f"manifest.plan_semantic_sha256={m_semantic!r} "
            f"report.plan_sha256={r_semantic!r}"
        )

    # ── Binding 1: responses_sha256 must line up between CHEM-05 and SEO manifests.
    chem05_responses_sha = chem05_manifest.get("responses_sha256")
    seo_responses_sha = (seo_manifest.get("source") or {}).get("responses_sha256")
    if not chem05_responses_sha or chem05_responses_sha != seo_responses_sha:
        raise PreviewPlanBuildError(
            f"BLOCKED {BLOCK_RESPONSES_SHA_MISMATCH}: "
            f"chem05={chem05_responses_sha!r} seo={seo_responses_sha!r}"
        )

    # ── Load CHEM-05 plan JSONL into a chem_id-keyed dict for O(1) lookup.
    plan_by_chem: dict[str, dict] = {}
    for row in _iter_jsonl(chem05_plan_jsonl):
        cid = row.get("chem_id")
        if isinstance(cid, str):
            plan_by_chem[cid] = row

    # Excluded chems must NOT appear in the plan-filtered preview membership.
    # (They may appear in the CHEM-05 partial plan — we drop them here.)
    excluded_ids = set((seo_manifest.get("census") or {}).get("excluded_chem_ids") or [])

    preview_chemicals: list[dict] = []
    reasons: list[dict] = []
    seo_chemicals = seo_manifest.get("chemicals") or []

    for member in seo_chemicals:
        cid = member.get("chem_id")
        if not isinstance(cid, str):
            reasons.append({"chem_id": cid, "reason": BLOCK_MANIFEST_MEMBER_NOT_IN_PLAN})
            continue
        if cid in excluded_ids:
            # SEO manifest cannot contradict its own excluded set — hard fail.
            reasons.append({"chem_id": cid, "reason": BLOCK_EXCLUDED_ID_PRESENT})
            continue
        bundle = plan_by_chem.get(cid)
        if bundle is None:
            reasons.append({"chem_id": cid, "reason": BLOCK_MANIFEST_MEMBER_NOT_IN_PLAN})
            continue
        detail_status = bundle.get("detail_status")
        if detail_status != DETAIL_COMPLETE:
            reasons.append({
                "chem_id": cid,
                "reason": BLOCK_MEMBER_DETAIL_STATUS_NOT_COMPLETE,
                "detail_status": detail_status,
            })
            continue
        sections = bundle.get("sections") or []
        seen_secs: set[int] = set()
        section_hashes: dict[int, str] = {}
        for s in sections:
            n = s.get("section_no")
            if not isinstance(n, int) or n not in ALLOWED_SECTIONS:
                continue
            if n in seen_secs:
                reasons.append({
                    "chem_id": cid,
                    "reason": BLOCK_MEMBER_DUPLICATE_SECTION,
                    "section_no": n,
                })
                seen_secs = set()   # mark this chem invalid
                break
            seen_secs.add(n)
            section_hashes[n] = s.get("section_hash") or ""
        else:
            if len(seen_secs) != SEO_PREVIEW_REQUIRED_SECTION_COUNT:
                reasons.append({
                    "chem_id": cid,
                    "reason": BLOCK_MEMBER_INCOMPLETE_SECTIONS,
                    "have": sorted(seen_secs),
                })
                continue
            # Recompute the per-chemical binding using CHEM-05's section_hash
            # values (which are canonical hashes of raw items). This must
            # match the SEO manifest's section_hashes_sha256, or the two
            # producers disagree.
            expected_chem_hash = member.get("section_hashes_sha256")
            parts = [section_hashes[n] for n in ALLOWED_SECTIONS]
            recomputed = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
            if expected_chem_hash and recomputed != expected_chem_hash:
                # Section hashes disagree between the two producers. Note:
                # CHEM-05's section_hash is defined by services.kosha_msds.hash;
                # the SEO manifest builder uses the same canonical items
                # encoding, so this should match under a clean artifact.
                # If it doesn't, that's an integrity failure between the two
                # tools and we fail-closed rather than silently proceed.
                reasons.append({
                    "chem_id": cid,
                    "reason": BLOCK_MEMBER_HASH_MISMATCH,
                    "expected": expected_chem_hash,
                    "recomputed": recomputed,
                })
                continue
            preview_chemicals.append(bundle)
            continue
        # If the for-else path was NOT taken, we broke out due to duplicate;
        # do NOT append the bundle.

    # If ANY reason accumulated, fail-closed with details.
    if reasons:
        raise PreviewPlanBuildError(
            "BLOCKED: preview plan build failed. reasons=" +
            json.dumps({"count": len(reasons), "sample": reasons[:10]}, ensure_ascii=False)
        )

    preview_chemicals.sort(key=lambda c: c.get("chem_id") or "")

    chemical_count = len(preview_chemicals)
    section_count = chemical_count * SEO_PREVIEW_REQUIRED_SECTION_COUNT
    seo_census = seo_manifest.get("census") or {}
    if chemical_count != seo_census.get("complete_chemicals"):
        raise PreviewPlanBuildError(
            f"BLOCKED: preview chemical count mismatch. plan={chemical_count} "
            f"seo_manifest.complete_chemicals={seo_census.get('complete_chemicals')}"
        )
    if section_count != seo_census.get("preview_sections"):
        raise PreviewPlanBuildError(
            f"BLOCKED: preview section count mismatch. plan={section_count} "
            f"seo_manifest.preview_sections={seo_census.get('preview_sections')}"
        )

    plan_semantic_sha = _preview_semantic_hash(preview_chemicals)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ── Emit CHEM-05-shaped manifest so materialize_writer.load_plan_inputs
    # can consume it verbatim. The additive snapshot.metrics_json fields carry
    # the SEO preview scope + manifest binding for CHEM-10.
    manifest = {
        "wo": WO_CODE,
        "generator_version": GENERATOR_VERSION,
        "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
        "adapter_version": "CHEM_SEO_PREVIEW_BRIDGE_V1",
        "responses_path": chem05_manifest.get("responses_path"),
        "responses_sha256": chem05_responses_sha,
        "seo_manifest_sha256": seo_manifest.get("manifest_sha256"),
        "plan_path": None,     # populated by caller when writing to disk
        "plan_semantic_sha256": plan_semantic_sha,
        "plan_file_sha256": None,   # populated after JSONL write
        "snapshot": {
            "run_type": "SEO_PREVIEW_MATERIALIZE",
            "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
            "publish_state": PUBLISH_NOT_PUBLISHED,
            "expected_count": chemical_count,
            "discovered_count": chemical_count,
            "started_at": started_at,
            "source_contract_version": chem05_manifest.get("source_contract_version"),
            "metrics_json": {
                "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
                "seo_preview_manifest_sha256": seo_manifest.get("manifest_sha256"),
                "responses_sha256": chem05_responses_sha,
                "seo_preview_expected_chemical_count": chemical_count,
                "seo_preview_expected_section_count": section_count,
                "source_plan_semantic_sha256": chem05_manifest.get("plan_semantic_sha256"),
                "source_plan_file_sha256": chem05_manifest.get("plan_file_sha256"),
                "source_manifest_sha256": chem05_manifest.get("manifest_sha256"),
            },
        },
        "counts": {
            "chemicals": chemical_count,
            "sections": section_count,
            "incomplete": 0,
            "duplicates": 0,
            "source_contract_failures": 0,
        },
        "execute_eligible": True,   # derived, all binding checks passed
        "execute_block_reasons": [],
        "started_at": started_at,
    }

    report = {
        "wo": WO_CODE,
        "adapter_version": "CHEM_SEO_PREVIEW_BRIDGE_V1",
        "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
        "responses_sha256": chem05_responses_sha,
        "seo_manifest_sha256": seo_manifest.get("manifest_sha256"),
        "plan_sha256": plan_semantic_sha,
        "counts": manifest["counts"],
        "execute_eligible": True,
        "started_at": started_at,
    }

    return {
        "plan_chemicals": preview_chemicals,
        "manifest": manifest,
        "report": report,
    }


def _write_plan_jsonl(chemicals: list[dict], out_path: Path) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for c in chemicals:
            fh.write(json.dumps(c, sort_keys=True, ensure_ascii=False) + "\n")
    return _file_sha256(out_path)


def write_preview_plan_artifacts(built: dict, out_dir: Path) -> dict:
    """Materialize the three preview files. Returns updated manifest dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "preview_materialize_plan.jsonl"
    manifest_path = out_dir / "preview_materialize_manifest.json"
    report_path = out_dir / "preview_materialize_report.json"

    plan_file_sha = _write_plan_jsonl(built["plan_chemicals"], plan_path)

    manifest = dict(built["manifest"])
    manifest["plan_path"] = str(plan_path)
    manifest["plan_file_sha256"] = plan_file_sha
    # Refresh metrics_json copy so both places carry the SHA.
    snap = dict(manifest.get("snapshot") or {})
    metrics = dict(snap.get("metrics_json") or {})
    metrics["preview_plan_file_sha256"] = plan_file_sha
    metrics["preview_plan_semantic_sha256"] = manifest["plan_semantic_sha256"]
    snap["metrics_json"] = metrics
    manifest["snapshot"] = snap

    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = dict(built["report"])
    report["plan_file_sha256"] = plan_file_sha
    report["plan_path"] = str(plan_path)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--chem05-plan-jsonl", required=True,
                   help="Path to CHEM-05 materialize_plan.jsonl.")
    p.add_argument("--chem05-manifest", required=True,
                   help="Path to CHEM-05 materialize_manifest.json.")
    p.add_argument("--chem05-report", required=True,
                   help="Path to CHEM-05 materialize_report.json.")
    p.add_argument("--seo-manifest", required=True,
                   help="Path to docs/chem/seo-preview-manifest.json.")
    p.add_argument("--out-dir", required=True,
                   help="Output directory for the three preview artifacts.")
    args = p.parse_args(argv)

    built = build_preview_plan(
        chem05_plan_jsonl=Path(args.chem05_plan_jsonl),
        chem05_manifest_json=Path(args.chem05_manifest),
        chem05_report_json=Path(args.chem05_report),
        seo_manifest_json=Path(args.seo_manifest),
    )
    manifest = write_preview_plan_artifacts(built, Path(args.out_dir))
    print(json.dumps({
        "action": "write",
        "out_dir": args.out_dir,
        "chemicals": manifest["counts"]["chemicals"],
        "sections": manifest["counts"]["sections"],
        "plan_semantic_sha256": manifest["plan_semantic_sha256"],
        "plan_file_sha256": manifest["plan_file_sha256"],
        "seo_manifest_sha256": manifest["seo_manifest_sha256"],
        "responses_sha256": manifest["responses_sha256"],
        "execute_eligible": manifest["execute_eligible"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
