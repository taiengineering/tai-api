#!/usr/bin/env python3
"""CLI entry point for OBJ-MSDS-04B OCR PoC benchmark.

Usage:
  python -m tools.msds_ocr_poc.run_poc [--output-dir PATH]

Production guards:
  - No DB writes
  - No external storage writes
  - No customer MSDS transmitted
"""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="OBJ-MSDS-04B OCR PoC Benchmark")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated corpus and report (default: tools/msds_ocr_poc/poc_output)",
    )
    args = parser.parse_args()

    # Import here to allow credentials to be set via env before import
    from tools.msds_ocr_poc.benchmark import run
    report = run(output_dir=args.output_dir)

    # Exit code based on regression
    reg = report.get("regression", {})
    all_pass = all(v.get("status") == "PASS" for v in reg.values() if "status" in v)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
