#!/usr/bin/env python3
"""
TAI REF-C012 안전작업 허가서 PDF 생성기 — WO-058 Phase C-01
Entry point only — assembly and rendering via common_v1_engine.
Usage: python3 gen_c012_pdf.py [blank|all]
"""
import sys
from pathlib import Path

# Engine is in the same directory
import common_v1_engine as eng

if __name__ == '__main__':
    eng.register_fonts()
    base        = Path(__file__).parent
    fields_path = base / 'c012_fields.json'
    out_dir     = base.parent / 'output'
    out_dir.mkdir(exist_ok=True)

    mode = sys.argv[1] if len(sys.argv) > 1 else 'blank'
    if mode in ('blank', 'all'):
        eng.generate(fields_path, out_dir / 'TAI-FORM-C012-blank.pdf')

    print("Done (PDF).")
