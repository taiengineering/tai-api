#!/usr/bin/env python3
"""
batch_build.py — WO-REF01-059-B7-FINAL-GATE-FIX-003
Common-v1 engine batch runner.

Modes (default: --dry-run):
  --dry-run      Validate schemas via engine validate(); no file writes.
  --verify-only  Regenerate to tmp; verify structure + frozen SHA. No writes to output/.
  --build        Generate to output/ — only for BUILD_APPROVED_IDS.

Safety rules:
  - Approved output files CANNOT be overwritten by any operation.
    There is no --force option. Any collision → BLOCKED.
  - --build with no IDs → builds only BUILD_APPROVED_IDS.
  - --build with explicit IDs → only if every ID is in BUILD_APPROVED_IDS.
  - Duplicate IDs in a --build request → rejected immediately.
  - Both PDF and DOCX must succeed in tmp before writing to output/.
    Partial success is NOT reported as BUILT.
  - PDF is written first; if DOCX write fails, PDF is rolled back.
  - Any failure in a batch → exit code nonzero.
  - --dry-run schema errors → exit code nonzero.
  - --verify-only: frozen approved-form outputs checked against FROZEN_SHA;
    MISSING or MISMATCH → failure.
  - --report path must not be inside output/ or scripts/.

Usage:
  python3 batch_build.py [--dry-run|--verify-only|--build] [ID ...]
  python3 batch_build.py --list
"""

import argparse
import hashlib
import json
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
    # B7 batch targets (APPROVED, FROZEN — WO-REF01-059-B7-BATCH-BUILD-005):
    "c007": _reg("c007"),
    "c008": _reg("c008"),
    "c009": _reg("c009"),
    "c011": _reg("c011"),
    "c013": _reg("c013"),
    # B8 wave-2 targets (GPT_REVIEW_REQUIRED — WO-REF01-060-B8-WAVE2-BATCH-001):
    "c026": _reg("c026"),
    "c027": _reg("c027"),
    "c028": _reg("c028"),
    "c029": _reg("c029"),
    "c031": _reg("c031"),
    "c033": _reg("c033"),
    "c037": _reg("c037"),
    "c039": _reg("c039"),
    "c040": _reg("c040"),
    "c041": _reg("c041"),
    "c042": _reg("c042"),
    "c043": _reg("c043"),
    "c044": _reg("c044"),
    "gov-01": _reg("gov-01"),
    # B9 batch targets (GPT_REVIEW_REQUIRED — WO-REF01-060-B9-REGISTER-BUILD-001):
    "gov-02": _reg("gov-02"),
    "gov-03": _reg("gov-03"),
    "doc-01": _reg("doc-01"),
    "doc-02": _reg("doc-02"),
    "chw-01": _reg("chw-01"),
}

# Outputs that are regression-frozen. --build is permanently blocked.
APPROVED_IDS = frozenset({
    "c001", "c003", "c004", "c005", "c014", "c015", "c016",  # B6 and earlier
    "c007", "c008", "c009", "c011", "c013",                  # B7-BATCH-BUILD-005
})

# Explicit GPT-approved IDs for --build. Must be added here after GPT approval.
BUILD_APPROVED_IDS = frozenset({          # WO-REF01-060-B8-WAVE2-BUILD-003
    "c026", "c027", "c028", "c029",
    "c031", "c033", "c037",
    "c039", "c040", "c041", "c042",
    "c043", "c044", "gov-01",
    # B9 — WO-REF01-060-B9-REGISTER-BUILD-002 (GPT DESIGN PASS 5/5):
    "gov-02", "gov-03", "doc-01", "doc-02", "chw-01",
})

# SHA256 of regression-frozen output files (full hex). Used by --verify-only.
FROZEN_SHA = {
    # B6 and earlier (7건)
    "c001_pdf":  "27002fc4bc21e6160e697f50c180d8bbf7369b55c27177803f50816afc960599",
    "c001_docx": "64955972e13c83602fb19ff00ee4369d4807041bcc0d5e21fd407f886928786d",
    "c003_pdf":  "5916f14da3d396fb1a2acce731d55a8dc6aafc3ee2ec9c87bb7c89285b0f35ec",
    "c003_docx": "e5167726323827448863d9efb5d73cbcdcd9532231530b1df3fb65d611651420",
    "c004_pdf":  "d2be9950cbdee03d00ec0a9e25d2efd9af643bf6352b0b342ac55ff48dcf99ec",
    "c004_docx": "ca0ef2d3f160b1ae88809c5aa8ceb10cd84be50e8c3ef10a665299dbf408f645",
    "c005_pdf":  "93cff8f970e68278f7c2dc2adc21ce2392d7ad9cbddc58dcbe174799d1d23d88",
    "c005_docx": "39099daa2156afcdaa8bbcc86a6200f91c5e8ca67b921ea2c4af7a9636326967",
    "c014_pdf":  "adbfc9ca8a26b7ad94a73e75d7781ee244d118869bfd553d2ed4559cf4e77ba6",
    "c014_docx": "afe75179f622405955864d2610eb8ad32e096d5b8492d0800907225e402f6583",
    "c015_pdf":  "77481eeae8eff7e27ef2fc50d452eb5cfa9fc018d02b45e7c6aab0ce0578235b",
    "c015_docx": "ec558785f4cec658af9a80134e78dd84a2ad7af88396fe38aa9cb5e9fa9739b9",
    "c016_pdf":  "a12fe50aba41a3bc78d72c176a37ca47099539cb9f229d4e622f0213567f32bd",
    "c016_docx": "bad68d52f6370c8be347a64524ef3de270ec0fad6b87889a3fe125f72cfcbfe5",
    # B7-BATCH-BUILD-005 (5건)
    "c007_pdf":  "2774fdc33f793fe25d3580ff089991f9b96ea2ae9efbb401dce31dd2281c82ad",
    "c007_docx": "73374430fe7624b7eb97b5e6251de02367a726c755574bba315c9dd4233a2ed3",
    "c008_pdf":  "11c4cf4b7612fd9d776de10b29a744a5055a33ffe40137986267b13fa904fe72",
    "c008_docx": "ff6ac9747c6a72f6ca3943778a014953d345bcbf2018e9bcfc5225ae96992cb6",
    "c009_pdf":  "2397559dccc6677dd1bbc646707934bfb34857d8cee8bc6f47651cd371cf5c90",
    "c009_docx": "4c4c34c56b93cfff84d25958789c3218a568284d0c47c6ec960f666eb11c0121",
    "c011_pdf":  "791bec736a92d76ef5b5565f04d0f0585158b231e2a98a7cf58718d14143ac46",
    "c011_docx": "1ca2b8ed58ad42de2aa5ce3894e7a84fd10feb128634e779964fee38957b4d1c",
    "c013_pdf":  "58fe149a510cc942679de0cd10253767b088d1e0d6a8423c344a11d0fdac190e",
    "c013_docx": "a7435672d3cbe8e3f12273579ed41251b8d310e415159d90094e9735928bbd7b",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256_file(path):
    h = hashlib.sha256(Path(path).read_bytes())
    return h.hexdigest()


def _write_exclusive(src: Path, dst: Path):
    """Copy src → dst using exclusive creation.

    - Raises FileExistsError if dst already exists (never overwrites).
    - On write failure after file creation: removes only the newly created partial dst.
    - If removal also fails: raises RuntimeError with RECOVERY_REQUIRED.
    - A dst that pre-existed (FileExistsError) is never touched.
    """
    dst = Path(dst)
    data = src.read_bytes()
    created = False
    try:
        with open(str(dst), 'xb') as f:
            created = True
            f.write(data)
    except FileExistsError:
        raise
    except Exception as write_err:
        if created:
            try:
                dst.unlink(missing_ok=True)
            except Exception as cleanup_err:
                raise RuntimeError(
                    f"RECOVERY_REQUIRED — write failed ({write_err}); "
                    f"cleanup failed ({cleanup_err}): {dst}"
                ) from write_err
        raise


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
    """Engine schema validation; no file generation. Returns (results, failures)."""
    print("\n=== DRY-RUN (engine validate) ===")
    results = []
    failures = []
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
        else:
            failures.append(cid)
    return results, failures


def run_verify_only(ids):
    """Regenerate to tmp; structural + frozen SHA verification. No writes to output/."""
    print("\n=== VERIFY-ONLY ===")
    print("  Regenerating to tmp — structure + frozen SHA verification\n")
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
                for file_type, fname in [("pdf", entry["pdf_name"]),
                                         ("docx", entry["docx_name"])]:
                    p = OUTPUT / fname
                    sha_key = f"{cid}_{file_type}"
                    expected = FROZEN_SHA.get(sha_key)
                    if not p.exists():
                        row[f"frozen_{file_type}"] = "MISSING"
                        doc_ok = False
                    else:
                        actual_sha = sha256_file(p)
                        if expected is None:
                            row[f"frozen_{file_type}"] = "MISSING_BASELINE"
                            doc_ok = False
                        elif actual_sha != expected:
                            row[f"frozen_{file_type}"] = (
                                f"MISMATCH sha8={actual_sha[:8]} exp={expected[:8]}")
                            doc_ok = False
                        else:
                            row[f"frozen_{file_type}"] = f"EXISTS sha8={actual_sha[:8]}"

            row["status"] = "OK" if doc_ok else "FAILED"
            if not doc_ok:
                failures.append(cid)
            results.append(row)

    return results, failures


def run_build(ids):
    """
    Generate PDF+DOCX to output/. Only BUILD_APPROVED_IDS are allowed.
    Both must succeed in tmp before writing to output/.
    PDF written first; DOCX write failure triggers PDF rollback.
    Any failure → that document is not written; batch exits nonzero.
    """
    print("\n=== BUILD ===")
    results = []
    failures = []

    # Duplicate ID guard
    if len(ids) != len(set(ids)):
        seen = set()
        dupes = [i for i in ids if i in seen or seen.add(i)]
        print(f"ERROR: duplicate form IDs in request: {list(set(dupes))}", file=sys.stderr)
        return [], ["DUPLICATE_ID"]

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

    # Generate in tmp, validate, then write exclusively to output/
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

            # Both succeeded — write to output/ exclusively
            pdf_out  = OUTPUT / entry["pdf_name"]
            docx_out = OUTPUT / entry["docx_name"]

            try:
                _write_exclusive(pdf_tmp, pdf_out)
            except FileExistsError:
                msg = f"BLOCKED_COLLISION — {entry['pdf_name']} already exists"
                print(f"  ✗ {cid.upper():6s}  {msg}")
                row["status"] = msg
                results.append(row)
                failures.append(cid)
                continue
            except Exception as e:
                msg = f"PDF_WRITE_FAILED — {e}"
                print(f"  ✗ {cid.upper():6s}  {msg}")
                row["status"] = msg
                results.append(row)
                failures.append(cid)
                continue

            try:
                _write_exclusive(docx_tmp, docx_out)
            except FileExistsError:
                try:
                    pdf_out.unlink()
                    msg = "ROLLED_BACK — DOCX collision; PDF removed"
                except Exception:
                    msg = "RECOVERY_REQUIRED — DOCX collision; PDF rollback failed"
                print(f"  ✗ {cid.upper():6s}  {msg}")
                row["status"] = msg
                results.append(row)
                failures.append(cid)
                continue
            except Exception as e:
                try:
                    pdf_out.unlink()
                    msg = f"ROLLED_BACK — DOCX write failed ({e}); PDF removed"
                except Exception:
                    msg = f"RECOVERY_REQUIRED — DOCX write failed ({e}); PDF may be orphaned"
                print(f"  ✗ {cid.upper():6s}  {msg}")
                row["status"] = msg
                results.append(row)
                failures.append(cid)
                continue

            row["pdf_sha256"]  = sha256_file(pdf_out)
            row["docx_sha256"] = sha256_file(docx_out)
            row["status"] = "BUILT"
            print(f"  ✓ {cid.upper():6s}  BUILT → {entry['pdf_name']}")
            results.append(row)

    return results, failures


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="batch_build.py — common-v1 engine batch runner (B7-FINAL-GATE-FIX-003)"
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

    # --report path protection: must not write into output/ or scripts/
    report_path = None
    if args.report:
        report_path = Path(args.report).resolve()
        for zone_path, zone_name in [(OUTPUT.resolve(), "output"),
                                     (BASE.resolve(), "scripts")]:
            try:
                report_path.relative_to(zone_path)
                print(f"ERROR: --report path must not be inside {zone_name}/",
                      file=sys.stderr)
                return 1
            except ValueError:
                pass

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
        results, failures = run_dry_run(ids)
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
    if report_path:
        report_json = json.dumps(report, indent=2, ensure_ascii=False)
        try:
            with open(str(report_path), 'x', encoding='utf-8') as rf:
                rf.write(report_json)
        except FileExistsError:
            print(f"ERROR: --report target already exists: {report_path}",
                  file=sys.stderr)
            return 1
        except Exception as e:
            print(f"ERROR: --report write failed: {e}", file=sys.stderr)
            return 1
        print(f"\nReport written to {report_path}")

    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
