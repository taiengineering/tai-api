"""
Bulk XLSX builder — WO-REF01-XLS03-BULK-XLSX-BUILD-001 Phase E.
Run from docs/reference-forms/xlsx/ or any directory.

Usage:
    python run_xlsx_build.py [--dry-run] [--only <ID>]
"""
import argparse
import hashlib
import os
import sys
import time
import traceback

# Resolve repo root relative path
_HERE = os.path.dirname(os.path.abspath(__file__))
_FORMS_ROOT = os.path.normpath(os.path.join(_HERE, '..'))
_OUTPUT_DIR = os.path.join(_FORMS_ROOT, 'output', 'xlsx')

sys.path.insert(0, _HERE)

from xlsx_registry import REGISTRY
from xlsx_schema_adapter import load_form_spec
from xlsx_builder import build_xlsx


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def run(dry_run: bool = False, only: str = None) -> dict:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    targets = {k: v for k, v in REGISTRY.items()
               if only is None or k == only}

    results = []
    errors = []

    for rid, meta in targets.items():
        out_path = os.path.join(_OUTPUT_DIR, meta['output_filename'])
        t0 = time.monotonic()
        status = 'SKIP' if dry_run else 'UNKNOWN'
        sha = ''
        err_msg = ''

        if not dry_run:
            try:
                spec = load_form_spec(rid)
                build_xlsx(
                    form_spec=spec,
                    design_type=meta['design_type'],
                    output_path=out_path,
                    research_id=rid,
                )
                sha = sha256_file(out_path)
                status = 'OK'
            except Exception as exc:
                status = 'ERROR'
                err_msg = str(exc)
                errors.append({'research_id': rid, 'error': err_msg,
                                'trace': traceback.format_exc()})

        elapsed = time.monotonic() - t0
        results.append({
            'research_id': rid,
            'output_filename': meta['output_filename'],
            'design_type': meta['design_type'],
            'forbidden_formula': meta['forbidden_formula'],
            'status': status,
            'sha256': sha,
            'elapsed_s': round(elapsed, 3),
            'error': err_msg,
        })
        marker = '✓' if status == 'OK' else ('✗' if status == 'ERROR' else '~')
        print(f'  {marker} {rid:<20} {status}  {meta["output_filename"]}')

    ok = sum(1 for r in results if r['status'] == 'OK')
    err = sum(1 for r in results if r['status'] == 'ERROR')
    print(f'\n  Total: {len(results)} | OK: {ok} | ERROR: {err}')

    return {'results': results, 'errors': errors}


def _write_csv_result(results: list, path: str):
    import csv
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=[
            'research_id', 'output_filename', 'design_type',
            'forbidden_formula', 'status', 'sha256', 'elapsed_s', 'error',
        ])
        w.writeheader()
        w.writerows(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--only', default=None)
    parser.add_argument('--csv-out', default=None)
    args = parser.parse_args()

    outcome = run(dry_run=args.dry_run, only=args.only)

    if args.csv_out and not args.dry_run:
        _write_csv_result(outcome['results'], args.csv_out)
        print(f'  CSV written to {args.csv_out}')

    if outcome['errors']:
        sys.exit(1)
