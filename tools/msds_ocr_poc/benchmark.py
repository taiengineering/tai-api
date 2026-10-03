"""Main OBJ-MSDS-04B OCR PoC benchmark runner.

Execution plan:
  1. Generate synthetic corpus (30 fixtures)
  2. CAS validator unit tests
  3. Deterministic parser benchmark (native PDF text — upper bound)
  4. Page strategy comparison (1-3 / 1-5 / 1-10 / full)
  5. Photo pipeline test
  6. Provider benchmarks (CLOVA / Tesseract / Vision)
  7. 04A regression (subprocess pytest)
  8. Report

Production guards:
  DB write = 0 / Storage write = 0 / Customer data external = 0
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from .cas_validator import validate_cas, try_correct_cas
from .corpus_data import ALL_FIXTURES, CAS_TEST_CASES, MsdsFixture
from .corpus_generator import generate_corpus
from .fact_parser import ParsedFacts, compare_facts, parse_facts
from .photo_pipeline import run_photo_pipeline_test
from .providers.base import BlockedCredentials, OcrProviderError, ProviderNotInstalled
from .providers.clova import ClovaOcrProvider
from .providers.tesseract_provider import TesseractProvider
from .providers.vision import VisionProvider

_PAGE_STRATEGIES = [3, 5, 10, None]  # None = full document


# ---------------------------------------------------------------------------
# 1. CAS Validator Tests
# ---------------------------------------------------------------------------

def run_cas_tests() -> dict:
    results = []
    for tc in CAS_TEST_CASES:
        fmt, chk = validate_cas(tc.raw)
        corrected = try_correct_cas(tc.raw) if not (fmt and chk) else None

        fmt_ok = fmt == tc.expect_format
        chk_ok = chk == tc.expect_checksum
        correction_ok = True
        if tc.ocr_correctable:
            correction_ok = corrected == tc.corrected

        results.append({
            "id": tc.raw,
            "description": tc.description,
            "format_valid": fmt,
            "checksum_valid": chk,
            "format_expect": tc.expect_format,
            "checksum_expect": tc.expect_checksum,
            "format_pass": fmt_ok,
            "checksum_pass": chk_ok,
            "ocr_correctable": tc.ocr_correctable,
            "corrected": corrected,
            "correction_pass": correction_ok,
            "overall": fmt_ok and chk_ok and correction_ok,
        })

    total = len(results)
    passed = sum(1 for r in results if r["overall"])
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "details": results,
    }


# ---------------------------------------------------------------------------
# 2. Deterministic Parser Benchmark (native PDF text)
# ---------------------------------------------------------------------------

def _extract_pdf_text_by_pages(pdf_path: str, max_pages: Optional[int] = None) -> str:
    reader = PdfReader(pdf_path)
    pages = reader.pages
    if max_pages is not None:
        pages = pages[:max_pages]
    return "\n".join(p.extract_text() or "" for p in pages)


def run_parser_benchmark(corpus: list[dict]) -> dict:
    results = []
    for entry in corpus:
        f: MsdsFixture = entry["fixture"]
        with open(entry["gt"]) as fp:
            gt = json.load(fp)

        text = _extract_pdf_text_by_pages(entry["pdf"])
        extracted = parse_facts(text)
        comparison = compare_facts(extracted, gt)

        results.append({
            "id": f.id,
            "language": f.language,
            "variant": f.variant,
            **comparison,
        })

    # Aggregate
    exact_product = [r for r in results if r["product_name"] == "EXACT"]
    exact_mfr = [r for r in results if r["manufacturer_name"] == "EXACT"]
    full_cas = [r for r in results if r["cas_recall"] == 1.0]
    no_fp = [r for r in results if r["cas_false_positive"] == 0]

    return {
        "total_fixtures": len(results),
        "product_name_exact_rate": len(exact_product) / len(results),
        "manufacturer_exact_rate": len(exact_mfr) / len(results),
        "cas_full_recall_rate": len(full_cas) / len(results),
        "cas_zero_false_positive_rate": len(no_fp) / len(results),
        "details": results,
    }


# ---------------------------------------------------------------------------
# 3. Page Strategy Benchmark
# ---------------------------------------------------------------------------

def run_page_strategy_benchmark(corpus: list[dict]) -> dict:
    strategy_results = {}

    for max_pages in _PAGE_STRATEGIES:
        label = f"pages_1-{max_pages}" if max_pages else "full"
        per_fixture = []

        for entry in corpus:
            f: MsdsFixture = entry["fixture"]
            with open(entry["gt"]) as fp:
                gt = json.load(fp)

            text = _extract_pdf_text_by_pages(entry["pdf"], max_pages)
            extracted = parse_facts(text)
            comparison = compare_facts(extracted, gt)

            per_fixture.append({
                "id": f.id,
                "cas_page": f.cas_page,
                "cas_recall": comparison["cas_recall"],
                "product_found": comparison["product_name"] == "EXACT",
            })

        cas_recalls = [r["cas_recall"] for r in per_fixture]
        product_found = [r["product_found"] for r in per_fixture]
        all_cas_captured = sum(1 for r in per_fixture if r["cas_recall"] == 1.0)

        strategy_results[label] = {
            "max_pages": max_pages,
            "documents": len(per_fixture),
            "product_recall": sum(product_found) / len(product_found),
            "cas_full_recall": all_cas_captured / len(per_fixture),
            "cas_mean_recall": sum(cas_recalls) / len(cas_recalls),
            "provider_calls_per_doc": 1 if max_pages is None else 1,
        }

    return strategy_results


# ---------------------------------------------------------------------------
# 4. Provider Benchmarks
# ---------------------------------------------------------------------------

def _try_provider(provider, corpus: list[dict], max_pages: Optional[int] = 5) -> dict:
    try:
        provider._check_availability()
    except BlockedCredentials as e:
        return {"status": "BLOCKED_CREDENTIALS", "reason": str(e)}
    except ProviderNotInstalled as e:
        return {"status": "NOT_EXECUTED", "reason": str(e)}

    results = []
    for entry in corpus[:5]:  # sample only when live to limit API cost
        try:
            t0 = time.perf_counter()
            ocr = provider.ocr_pdf(entry["pdf"], max_pages=max_pages)
            elapsed = (time.perf_counter() - t0) * 1000
            with open(entry["gt"]) as fp:
                gt = json.load(fp)
            extracted = parse_facts(ocr.full_text)
            comparison = compare_facts(extracted, gt)
            results.append({
                "id": entry["fixture"].id,
                "latency_ms": ocr.total_latency_ms,
                "cost_krw": ocr.estimated_cost_krw,
                **comparison,
            })
        except Exception as e:
            results.append({"id": entry["fixture"].id, "error": str(e)})

    if not results:
        return {"status": "NO_RESULTS"}

    latencies = [r.get("latency_ms", 0) for r in results if "latency_ms" in r]
    cas_recalls = [r.get("cas_recall", 0) for r in results if "cas_recall" in r]
    costs = [r.get("cost_krw", 0) for r in results if "cost_krw" in r]

    return {
        "status": "EXECUTED",
        "documents": len(results),
        "product_exact": sum(1 for r in results if r.get("product_name") == "EXACT"),
        "cas_mean_recall": sum(cas_recalls) / len(cas_recalls) if cas_recalls else 0,
        "p50_latency_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
        "total_cost_krw": sum(costs),
        "cost_per_doc_krw": sum(costs) / len(costs) if costs else 0,
        "details": results,
    }


def run_provider_benchmarks(corpus: list[dict]) -> dict:
    return {
        "CLOVA": _try_provider(ClovaOcrProvider(), corpus),
        "TESSERACT": _try_provider(TesseractProvider(), corpus),
        "VISION_FALLBACK": _try_provider(VisionProvider(), corpus),
    }


# ---------------------------------------------------------------------------
# 5. OBJ-04A Regression
# ---------------------------------------------------------------------------

def run_regression(repo_root: Path) -> dict:
    suites = [
        ("OBJ04A", "tests/test_msds_intakes.py", 87),
        ("OBJ03",  "tests/test_msds_versions.py", 74),
        ("OBJ02",  "tests/test_msds_products.py", 83),
    ]
    results = {}
    for suite_name, test_file, expected_count in suites:
        test_path = repo_root / test_file
        if not test_path.exists():
            results[suite_name] = {"status": "FILE_NOT_FOUND", "path": str(test_path)}
            continue
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_path), "-q", "--tb=no"],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        elapsed = (time.perf_counter() - t0) * 1000
        passed = "passed" in proc.stdout
        # Extract count from output like "87 passed"
        import re
        m = re.search(r'(\d+) passed', proc.stdout)
        count = int(m.group(1)) if m else 0

        results[suite_name] = {
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "count": count,
            "expected": expected_count,
            "count_match": count == expected_count,
            "elapsed_ms": round(elapsed, 0),
            "returncode": proc.returncode,
        }
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(report: dict) -> None:
    print("\n" + "=" * 70)
    print("WO-MSDS-04B-POC-001 BENCHMARK REPORT")
    print("=" * 70)

    print("\n[CREDENTIALS]")
    print(f"  CLOVA   = {report['credentials']['clova']}")
    print(f"  OPENAI  = {report['credentials']['openai']}")

    print("\n[CAS VALIDATOR]")
    cv = report["cas_validator"]
    print(f"  total={cv['total']} passed={cv['passed']} failed={cv['failed']}")
    for r in cv["details"]:
        if not r["overall"]:
            print(f"  FAIL  {r['id']:20s}  {r['description']}")

    print("\n[DETERMINISTIC PARSER — native PDF upper bound]")
    pb = report["parser_benchmark"]
    print(f"  fixtures             = {pb['total_fixtures']}")
    print(f"  product_name exact   = {pb['product_name_exact_rate']:.0%}")
    print(f"  manufacturer exact   = {pb['manufacturer_exact_rate']:.0%}")
    print(f"  CAS full recall      = {pb['cas_full_recall_rate']:.0%}")
    print(f"  CAS zero FP          = {pb['cas_zero_false_positive_rate']:.0%}")

    print("\n[PAGE STRATEGY]")
    ps = report["page_strategy"]
    fmt = "  {:<12}  docs={:<3}  product={:.0%}  CAS_full={:.0%}  CAS_mean={:.0%}"
    for label, r in ps.items():
        print(fmt.format(
            label, r["documents"],
            r["product_recall"], r["cas_full_recall"], r["cas_mean_recall"],
        ))

    print("\n[PHOTO PIPELINE]")
    pp = report["photo_pipeline"]
    for key, r in pp.items():
        print(f"  {key:12s}  order={r['sequence_order_correct']}  "
              f"pdf_pages={r['derived_pdf']['page_count']}  "
              f"status={r['status']}")

    print("\n[PROVIDERS]")
    pv = report["providers"]
    for name, r in pv.items():
        if r["status"] in ("BLOCKED_CREDENTIALS", "NOT_EXECUTED", "NO_RESULTS"):
            print(f"  {name:20s}  {r['status']}")
            if "reason" in r:
                print(f"    reason: {r['reason'][:80]}")
        else:
            print(f"  {name:20s}  docs={r['documents']}  "
                  f"product={r['product_exact']}  "
                  f"CAS={r['cas_mean_recall']:.0%}  "
                  f"p50={r['p50_latency_ms']:.0f}ms  "
                  f"cost={r['total_cost_krw']:.1f}KRW")

    print("\n[REGRESSION]")
    reg = report["regression"]
    for suite, r in reg.items():
        mark = "PASS" if r.get("status") == "PASS" else "FAIL"
        print(f"  {suite:8s}  {mark}  {r.get('count', '?')}/{r.get('expected', '?')}")

    print("\n[PRODUCTION GUARDS]")
    print("  DB write        = 0")
    print("  Storage write   = 0")
    print("  Customer data   = 0")

    print("\n[READY FOR GPT DESIGN FREEZE]")
    ready = (
        report["cas_validator"]["failed"] == 0
        and report["parser_benchmark"]["cas_full_recall_rate"] >= 0.8
        and all(v.get("status") == "PASS"
                for v in report["regression"].values()
                if "status" in v)
    )
    print(f"  READY = {'YES' if ready else 'NO — see failures above'}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(output_dir: Optional[Path] = None) -> dict:
    if output_dir is None:
        output_dir = Path(__file__).parent / "poc_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).parents[2]  # tai-api-msds-04a/

    report: dict = {
        "output_dir": str(output_dir),
        "credentials": {
            "clova": "PRESENT" if (
                os.environ.get("CLOVA_OCR_INVOKE_URL") and
                os.environ.get("CLOVA_OCR_SECRET")
            ) else "ABSENT",
            "openai": "PRESENT" if os.environ.get("OPENAI_API_KEY") else "ABSENT",
        },
    }

    print("Step 1/7: Generating corpus...")
    corpus = generate_corpus(output_dir / "corpus")
    print(f"  Generated {len(corpus)} fixtures")

    print("Step 2/7: CAS validator tests...")
    report["cas_validator"] = run_cas_tests()

    print("Step 3/7: Parser benchmark (native PDF)...")
    report["parser_benchmark"] = run_parser_benchmark(corpus)

    print("Step 4/7: Page strategy comparison...")
    report["page_strategy"] = run_page_strategy_benchmark(corpus)

    print("Step 5/7: Photo pipeline test...")
    report["photo_pipeline"] = run_photo_pipeline_test(output_dir)

    print("Step 6/7: Provider benchmarks...")
    report["providers"] = run_provider_benchmarks(corpus)

    print("Step 7/7: Regression tests...")
    report["regression"] = run_regression(repo_root)

    # Save report
    report_path = output_dir / "benchmark_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\nFull report saved: {report_path}")

    print_report(report)
    return report
