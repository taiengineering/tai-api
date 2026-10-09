#!/usr/bin/env python3
"""
batch_build.py — WO-REF01-059-B7-BATCH-REMEDIATION-002
Common-v1 engine batch runner.

Modes (default: --dry-run):
  --dry-run      Validate schemas via engine validate(); no file writes.
  --verify-only  Regenerate to tmp; verify structure. No writes to output/.
  --build        Generate to output/ — only for BUILD_APPROVED_IDS.

Safety rules:
  - Approved output files CANNOT be overwritten by any operation.
    There is no --force option. Any collision → BLOCKED.
  - --build with no IDs → builds only BUILD_APPROVED_IDS.
  - --build with explicit IDs → only if every ID is in BUILD_APPROVED_IDS.
  - Both PDF and DOCX must succeed in tmp before writing to output/.
    Partial success is NOT reported as BUILT.
  - Any failure in a batch → exit code nonzero.

Usage:
  python3 batch_build.py [--dry-run|--verify-only|--build] [ID ...]
  python3 batch_build.py --list
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

BASE   = Path(__file__).parent
OUTPUT = BASE.parent / "output"

# ── Registry ──────────────────────────────────────────────────────────────────

def _reg(cid, pdf_name=None, docx_name=None):
    code = cid.upper()
    return {
        "id":        cid,
        "json":      BASE / f"{cid}_v1.json",
        "pdf_name":  pdf_name  or f"TAI-FORM-{code}-blank.pdf",
        "docx_name": docx_name or f"TAI-FORM-{code}-blank.docx",
    }

REGISTRY = {
    "c001": _reg("c001"),
    "c003": _reg("c003"),
    "c004": _reg("c004"),
    "c005": _reg("c005"),
    # c012: legacy c012_fields.json schema — not common_v1 batch-compatible
    "c014": _reg("c014"),
    "c015": _reg("c015"),
    "c016": _reg("c016"),
    # New batch targets:
    "c007": _reg("c007"),
    "c008": _reg("c008"),
    "c009": _reg("c009"),
    "c011": _reg("c011"),
    "c013": _reg("c013"),
}

# Outputs that are regression-frozen. --build is permanently blocked.
APPROVED_IDS = frozenset({"c001", "c003", "c004", "c005", "c014", "c015", "c016"})

# Explicit GPT-approved IDs for --build. Must be added here after GPT approval.
BUILD_APPROVED_IDS = frozenset()   # empty until GPT approves new batch


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256_file(path):
    h = hashlib.sha256(Path(path).read_bytes())
    return h.hexdigest()


def validate_schema(entry):
    """
    Two-stage validation:
    1. JSON parse + meta fields check
    2. Engine validate() call
    Returns (ok, data, stage, error).
    """
    p = entry["json"]
    if not p.exists():
        return False, None, "FILE", f"JSON not found: {p.name}"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, None, "JSON_PARSE", str(e)
    if data.get("_meta", {}).get("schema_version") != "common-v1":
        return False, data, "META", "schema_version != common-v1"
    if "sections" not in data:
        return False, data, "META", "missing 'sections' key"
    # Engine validation
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE))
        from common_v1_engine import validate as engine_validate
        engine_validate(data)
    except Exception as e:
        return False, data, "ENGINE", str(e)
    return True, data, "OK", None


def verify_pdf(path):
    """Check PDF opens and has ≥1 page."""
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        n = len(pdf.pages)
        if n < 1:
            raise ValueError(f"PDF has {n} pages")
        return n


def verify_docx(path):
    """Check DOCX is a valid ZIP with OOXML structure."""
    if not zipfile.is_zipfile(str(path)):
        raise ValueError("DOCX is not a valid ZIP file")
    with zipfile.ZipFile(str(path)) as z:
        names = z.namelist()
        if "word/document.xml" not in names:
            raise ValueError("word/document.xml missing in DOCX")
    return True


def generate_pdf(entry, out_path):
    import sys as _sys
    _sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    data = json.loads(entry["json"].read_text(encoding="utf-8"))
    generate_from_dict(data, str(out_path))


def generate_docx(entry, out_path):
    result = subprocess.run(
        ["node", "gen_c002_docx_common.cjs",
         str(entry["json"]), str(out_path)],
        capture_output=True, text=True, cwd=str(BASE),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "node exited non-zero")


def output_collision(entry):
    """Return path if output file already exists in output/, else None."""
    for fname in (entry["pdf_name"], entry["docx_name"]):
        p = OUTPUT / fname
        if p.exists():
            return p
    return None


# ── Mode implementations ───────────────────────────────────────────────────────

def run_dry_run(ids):
    """Engine schema validation; no file generation."""
    print("\n=== DRY-RUN (engine validate) ===")
    results = []
    for cid in ids:
        entry   = REGISTRY[cid]
        approved = cid in APPROVED_IDS
        build_ok = cid in BUILD_APPROVED_IDS
        ok, data, stage, err = validate_schema(entry)
        status = "SCHEMA_VALID" if ok else f"SCHEMA_ERROR[{stage}]: {err}"
        row = {"id": cid, "approved": approved, "build_approved": build_ok,
               "json_exists": entry["json"].exists(), "schema": status}
        results.append(row)
        mark = "✓" if ok else "✗"
        tag  = "APPROVED" if approved else ("BUILD_OK" if build_ok else "NEW")
        print(f"  {mark} {cid.upper():6s} [{tag:8s}]  {status}")
        if ok:
            orient = data.get("document", {}).get("page", {}).get("orientation", "?")
            n_sec  = len(data.get("sections", []))
            print(f"         orientation={orient}  sections={n_sec}")
    return results


def run_verify_only(ids):
    """Regenerate to tmp; structural verification. PDF/DOCX non-deterministic."""
    print("\n=== VERIFY-ONLY ===")
    print("  Regenerating to tmp — structure verification (not SHA comparison)\n")
    results = []
    failures = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for cid in ids:
            entry    = REGISTRY[cid]
            approved = cid in APPROVED_IDS
            tag      = "APPROVED" if approved else "NEW"
            ok, _, stage, err = validate_schema(entry)
            if not ok:
                msg = f"SCHEMA_ERROR[{stage}]: {err}"
                print(f"  ✗ {cid.upper():6s}  {msg}")
                results.append({"id": cid, "status": "SCHEMA_ERROR", "detail": msg})
                failures.append(cid)
                continue

            row = {"id": cid, "approved": approved}
            doc_ok = True

            # PDF
            pdf_tmp = tmp / entry["pdf_name"]
            try:
                generate_pdf(entry, pdf_tmp)
                pages = verify_pdf(pdf_tmp)
                kb = pdf_tmp.stat().st_size / 1024
                row["pdf"] = f"OK  {pages}p {kb:.0f}KB"
                print(f"  ✓ PDF  {cid.upper():6s} [{tag}]  {pages}p {kb:.0f}KB")
            except Exception as e:
                row["pdf"] = f"ERROR: {e}"
                print(f"  ✗ PDF  {cid.upper():6s} [{tag}]  ERROR: {e}")
                doc_ok = False

            # DOCX
            docx_tmp = tmp / entry["docx_name"]
            try:
                generate_docx(entry, docx_tmp)
                verify_docx(docx_tmp)
                kb = docx_tmp.stat().st_size / 1024
                row["docx"] = f"OK  {kb:.0f}KB"
                print(f"  ✓ DOCX {cid.upper():6s} [{tag}]  {kb:.0f}KB")
            except Exception as e:
                row["docx"] = f"ERROR: {e}"
                print(f"  ✗ DOCX {cid.upper():6s} [{tag}]  ERROR: {e}")
                doc_ok = False

            # Frozen-file integrity check for approved forms
            if approved:
                for fname, key in [(entry["pdf_name"], "frozen_pdf"),
                                   (entry["docx_name"], "frozen_docx")]:
                    p = OUTPUT / fname
                    if p.exists():
                        row[key] = f"EXISTS sha8={sha256_file(p)[:8]}"
                    else:
                        row[key] = "MISSING"

            row["status"] = "OK" if doc_ok else "FAILED"
            if not doc_ok:
                failures.append(cid)
            results.append(row)

    return results, failures


def run_build(ids):
    """
    Generate PDF+DOCX to output/. Only BUILD_APPROVED_IDS are allowed.
    Both must succeed in tmp before writing to output/.
    Any failure → that document is not written; batch exits nonzero.
    """
    print("\n=== BUILD ===")
    results = []
    failures = []

    # Pre-flight: verify all requested IDs are BUILD_APPROVED
    for cid in ids:
        if cid in APPROVED_IDS:
            msg = f"BLOCKED — {cid.upper()} is an approved frozen form"
            print(f"  ✗ {cid.upper():6s}  {msg}")
            results.append({"id": cid, "status": "BLOCKED_FROZEN"})
            failures.append(cid)
        elif cid not in BUILD_APPROVED_IDS:
            msg = f"BLOCKED — {cid.upper()} is not in BUILD_APPROVED_IDS"
            print(f"  ✗ {cid.upper():6s}  {msg}")
            results.append({"id": cid, "status": "BLOCKED_NOT_APPROVED"})
            failures.append(cid)
        else:
            # Output collision check
            entry = REGISTRY[cid]
            col = output_collision(entry)
            if col:
                msg = f"BLOCKED — output file already exists: {col.name}"
                print(f"  ✗ {cid.upper():6s}  {msg}")
                results.append({"id": cid, "status": "BLOCKED_COLLISION",
                                 "detail": str(col)})
                failures.append(cid)

    if failures:
        return results, failures

    # Generate in tmp, validate, then copy atomically
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for cid in ids:
            entry = REGISTRY[cid]
            ok, _, stage, err = validate_schema(entry)
            if not ok:
                msg = f"SCHEMA_ERROR[{stage}]: {err}"
                print(f"  ✗ {cid.upper():6s}  {msg}")
                results.append({"id": cid, "status": "SCHEMA_ERROR", "detail": msg})
                failures.append(cid)
                continue

            pdf_tmp  = tmp / entry["pdf_name"]
            docx_tmp = tmp / entry["docx_name"]
            row = {"id": cid}
            doc_ok = True

            # Generate PDF
            try:
                generate_pdf(entry, pdf_tmp)
                pages = verify_pdf(pdf_tmp)
                row["pdf_pages"] = pages
                row["pdf_sha256_tmp"] = sha256_file(pdf_tmp)
                print(f"  ✓ PDF  {cid.upper():6s}  {pages}p  sha={row['pdf_sha256_tmp'][:8]}")
            except Exception as e:
                row["pdf"] = f"ERROR: {e}"
                print(f"  ✗ PDF  {cid.upper():6s}  ERROR: {e}")
                doc_ok = False

            # Generate DOCX
            try:
                generate_docx(entry, docx_tmp)
                verify_docx(docx_tmp)
                row["docx_sha256_tmp"] = sha256_file(docx_tmp)
                print(f"  ✓ DOCX {cid.upper():6s}  sha={row['docx_sha256_tmp'][:8]}")
            except Exception as e:
                row["docx"] = f"ERROR: {e}"
                print(f"  ✗ DOCX {cid.upper():6s}  ERROR: {e}")
                doc_ok = False

            if not doc_ok:
                row["status"] = "FAILED — partial output NOT written to output/"
                print(f"  ✗ {cid.upper():6s}  FAILED — partial output NOT written")
                results.append(row)
                failures.append(cid)
                continue

            # Both succeeded — copy to output/
            pdf_out  = OUTPUT / entry["pdf_name"]
            docx_out = OUTPUT / entry["docx_name"]
            shutil.copy2(str(pdf_tmp),  str(pdf_out))
            shutil.copy2(str(docx_tmp), str(docx_out))
            row["pdf_sha256"]  = sha256_file(pdf_out)
            row["docx_sha256"] = sha256_file(docx_out)
            row["status"] = "BUILT"
            print(f"  ✓ {cid.upper():6s}  BUILT → {entry['pdf_name']}")
            results.append(row)

    return results, failures


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="batch_build.py — common-v1 engine batch runner (B7-REMEDIATION-002)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run",      action="store_true", default=False)
    group.add_argument("--verify-only",  action="store_true")
    group.add_argument("--build",        action="store_true")
    group.add_argument("--list",         action="store_true")
    parser.add_argument("--report", metavar="PATH",
                        help="write batch result JSON to this path")
    parser.add_argument("ids", nargs="*",
                        help="form IDs (default: all registered / BUILD_APPROVED for --build)")
    args = parser.parse_args()

    if not (args.dry_run or args.verify_only or args.build or args.list):
        args.dry_run = True

    if args.list:
        print("Registered forms:")
        for cid, entry in REGISTRY.items():
            tags = []
            if cid in APPROVED_IDS:        tags.append("APPROVED")
            if cid in BUILD_APPROVED_IDS:  tags.append("BUILD_OK")
            tag = "/".join(tags) or "NEW"
            js  = "✓" if entry["json"].exists() else "✗"
            col = "⚠ collision" if output_collision(entry) else ""
            print(f"  {cid.upper():6s} [{tag:10s}] json={js}  {col}")
        return 0

    # Resolve IDs
    if args.build and not args.ids:
        ids = list(BUILD_APPROVED_IDS)
        if not ids:
            print("ERROR: BUILD_APPROVED_IDS is empty. No forms approved for --build.",
                  file=sys.stderr)
            return 1
    elif args.ids:
        ids = [i.lower() for i in args.ids]
    else:
        ids = list(REGISTRY.keys())

    unknown = [i for i in ids if i not in REGISTRY]
    if unknown:
        print(f"ERROR: unknown form IDs: {unknown}", file=sys.stderr)
        return 1

    # Execute
    failures = []
    if args.dry_run:
        results = run_dry_run(ids)
    elif args.verify_only:
        results, failures = run_verify_only(ids)
    elif args.build:
        results, failures = run_build(ids)
    else:
        results = []

    # Report
    report = {
        "mode": ("dry-run" if args.dry_run else
                 "verify-only" if args.verify_only else "build"),
        "ids": ids, "failures": failures, "results": results,
    }
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReport written to {args.report}")

    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
