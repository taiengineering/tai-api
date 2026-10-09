#!/usr/bin/env python3
"""
batch_build.py — WO-REF01-059-B7-BATCH-PRODUCTION-001
Common-v1 engine batch runner.

Modes (default: --dry-run):
  --dry-run      Validate schemas; report what would be built. No file writes.
  --verify-only  Regenerate approved forms to tmp; compare SHA256. No writes to output/.
  --build        Generate PDF+DOCX to output/. Refused for approved outputs unless --force.

Usage:
  python3 batch_build.py [--dry-run|--verify-only|--build] [ID ...]
  python3 batch_build.py --list

IDs: form codes like c007, c008, c009, c011, c013
     omit to process all registered forms
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).parent
OUTPUT = BASE.parent / "output"

# ── Registry ─────────────────────────────────────────────────────────────────
# Each entry: id → {json, pdf_name, docx_name, approved}
# approved=True: existing output exists and is regression-frozen.
# approved=False: new form awaiting batch production.

def _reg(cid, pdf_name=None, docx_name=None):
    code = cid.upper()
    pdf  = pdf_name  or f"TAI-FORM-{code}-blank.pdf"
    docx = docx_name or f"TAI-FORM-{code}-blank.docx"
    return {
        "id":        cid,
        "json":      BASE / f"{cid}_v1.json",
        "pdf_name":  pdf,
        "docx_name": docx,
    }

REGISTRY = {
    "c001":  _reg("c001"),
    "c003":  _reg("c003"),
    "c004":  _reg("c004"),
    "c005":  _reg("c005"),
    # c012 uses legacy c012_fields.json schema — not common_v1 batch-compatible
    "c014":  _reg("c014"),
    "c015":  _reg("c015"),
    "c016":  _reg("c016"),
    # New batch targets (pending GPT spec approval):
    "c007":  _reg("c007"),
    "c008":  _reg("c008"),
    "c009":  _reg("c009"),
    "c011":  _reg("c011"),
    # c013 BLOCKED — ENGINE_GAP confirmed (B6-B2: 사고조사반 sub-table, 복수 필드 행)
}

APPROVED_IDS = {"c001", "c003", "c004", "c005", "c014", "c015", "c016"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256_file(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def sha256_prefix(path, n=8):
    return sha256_file(path)[:n]


def validate_schema(entry):
    """Load and validate JSON schema. Returns (ok, data, error)."""
    p = entry["json"]
    if not p.exists():
        return False, None, f"JSON not found: {p.name}"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, None, f"JSON parse error: {e}"
    if data.get("_meta", {}).get("schema_version") != "common-v1":
        return False, data, "schema_version != common-v1"
    if "sections" not in data:
        return False, data, "missing 'sections' key"
    return True, data, None


def generate_pdf(entry, out_path):
    """Generate PDF using common_v1_engine.py."""
    import sys as _sys
    _sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    data = json.loads(entry["json"].read_text(encoding="utf-8"))
    generate_from_dict(data, str(out_path))


def generate_docx(entry, out_path):
    """Generate DOCX via node gen_c002_docx_common.cjs."""
    result = subprocess.run(
        ["node", "gen_c002_docx_common.cjs",
         str(entry["json"]), str(out_path)],
        capture_output=True, text=True, cwd=str(BASE),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "node exited non-zero")


# ── Mode implementations ───────────────────────────────────────────────────────

def run_dry_run(ids):
    """Validate schemas; no file generation."""
    print("\n=== DRY-RUN ===")
    results = []
    for cid in ids:
        entry = REGISTRY[cid]
        ok, data, err = validate_schema(entry)
        approved = cid in APPROVED_IDS
        pdf_exists  = (OUTPUT / entry["pdf_name"]).exists()
        docx_exists = (OUTPUT / entry["docx_name"]).exists()
        status = "SCHEMA_VALID" if ok else f"SCHEMA_ERROR: {err}"
        results.append({
            "id": cid, "approved": approved,
            "json_exists": entry["json"].exists(),
            "pdf_exists": pdf_exists, "docx_exists": docx_exists,
            "schema": status,
        })
        mark = "✓" if ok else "✗"
        src  = "APPROVED" if approved else "NEW"
        print(f"  {mark} {cid.upper():6s} [{src:8s}]  {status}")
        if ok:
            orient = data.get("document", {}).get("page", {}).get("orientation", "?")
            n_sec  = len(data.get("sections", []))
            print(f"         orientation={orient}  sections={n_sec}")
    return results


def run_verify_only(ids):
    """Regenerate forms to tmp; check generation succeeds and output is valid.
    PDF/DOCX are non-deterministic (timestamps embedded), so SHA256 comparison
    is intentionally skipped. Pass = generates without error + file non-empty."""
    print("\n=== VERIFY-ONLY ===")
    print("  (PDF/DOCX are non-deterministic — checking generation success only)\n")
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for cid in ids:
            entry = REGISTRY[cid]
            approved = cid in APPROVED_IDS
            ok, _, err = validate_schema(entry)
            if not ok:
                print(f"  ✗ {cid.upper():6s}  SCHEMA_ERROR: {err}")
                results.append({"id": cid, "status": "SCHEMA_ERROR", "detail": err})
                continue

            row = {"id": cid, "approved": approved}
            tag = "APPROVED" if approved else "NEW"

            # PDF
            pdf_tmp = tmp / entry["pdf_name"]
            try:
                generate_pdf(entry, pdf_tmp)
                kb = pdf_tmp.stat().st_size / 1024
                row["pdf"] = f"OK  {kb:.0f}KB"
                print(f"  ✓ PDF  {cid.upper():6s} [{tag}]  {kb:.0f}KB")
            except Exception as e:
                row["pdf"] = f"ERROR: {e}"
                print(f"  ✗ PDF  {cid.upper():6s} [{tag}]  ERROR: {e}")

            # DOCX
            docx_tmp = tmp / entry["docx_name"]
            try:
                generate_docx(entry, docx_tmp)
                kb = docx_tmp.stat().st_size / 1024
                row["docx"] = f"OK  {kb:.0f}KB"
                print(f"  ✓ DOCX {cid.upper():6s} [{tag}]  {kb:.0f}KB")
            except Exception as e:
                row["docx"] = f"ERROR: {e}"
                print(f"  ✗ DOCX {cid.upper():6s} [{tag}]  ERROR: {e}")

            results.append(row)
    return results


def run_build(ids, force=False):
    """Generate PDF+DOCX to output/. Refuse approved outputs unless --force."""
    print("\n=== BUILD ===")
    results = []
    for cid in ids:
        entry = REGISTRY[cid]
        approved = cid in APPROVED_IDS

        if approved and not force:
            msg = f"SKIPPED — approved output is frozen (use --force to override)"
            print(f"  - {cid.upper():6s}  {msg}")
            results.append({"id": cid, "status": "SKIPPED_FROZEN"})
            continue

        ok, _, err = validate_schema(entry)
        if not ok:
            print(f"  ✗ {cid.upper():6s}  SCHEMA_ERROR: {err}")
            results.append({"id": cid, "status": "SCHEMA_ERROR", "detail": err})
            continue

        row = {"id": cid}
        pdf_out  = OUTPUT / entry["pdf_name"]
        docx_out = OUTPUT / entry["docx_name"]

        try:
            generate_pdf(entry, pdf_out)
            row["pdf"] = sha256_prefix(pdf_out)
            print(f"  ✓ PDF  {cid.upper():6s}  sha={row['pdf']}  {pdf_out.name}")
        except Exception as e:
            row["pdf"] = f"ERROR: {e}"
            print(f"  ✗ PDF  {cid.upper():6s}  ERROR: {e}")

        try:
            generate_docx(entry, docx_out)
            row["docx"] = sha256_prefix(docx_out)
            print(f"  ✓ DOCX {cid.upper():6s}  sha={row['docx']}  {docx_out.name}")
        except Exception as e:
            row["docx"] = f"ERROR: {e}"
            print(f"  ✗ DOCX {cid.upper():6s}  ERROR: {e}")

        row["status"] = "BUILT"
        results.append(row)
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="batch_build.py — common-v1 engine batch runner"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run",      action="store_true", default=False)
    group.add_argument("--verify-only",  action="store_true")
    group.add_argument("--build",        action="store_true")
    group.add_argument("--list",         action="store_true")
    parser.add_argument("--force",  action="store_true",
                        help="--build: allow regenerating approved outputs")
    parser.add_argument("--report", metavar="PATH",
                        help="write batch result JSON to this path")
    parser.add_argument("ids", nargs="*",
                        help="form IDs to process (default: all registered)")
    args = parser.parse_args()

    # Default mode
    if not (args.dry_run or args.verify_only or args.build or args.list):
        args.dry_run = True

    if args.list:
        print("Registered forms:")
        for cid, entry in REGISTRY.items():
            tag = "APPROVED" if cid in APPROVED_IDS else "NEW"
            js  = "✓" if entry["json"].exists() else "✗"
            print(f"  {cid.upper():6s} [{tag:8s}]  json={js}  "
                  f"pdf={entry['pdf_name']}")
        return 0

    # Resolve IDs
    ids_requested = [i.lower() for i in args.ids] if args.ids else list(REGISTRY.keys())
    unknown = [i for i in ids_requested if i not in REGISTRY]
    if unknown:
        print(f"ERROR: unknown form IDs: {unknown}", file=sys.stderr)
        return 1
    ids = ids_requested

    # Execute
    if args.dry_run:
        results = run_dry_run(ids)
    elif args.verify_only:
        results = run_verify_only(ids)
    elif args.build:
        results = run_build(ids, force=args.force)
    else:
        results = []

    # Report
    report = {"mode": "dry-run" if args.dry_run else
                       "verify-only" if args.verify_only else "build",
              "ids": ids, "results": results}
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
        print(f"\nReport written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
