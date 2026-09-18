"""READ-only Shared Search F2 census CLI.

WO-TAI-SHARED-SEARCH-F2 CO §37. Thin wrapper. All logic in
`services.shared_search.census.run_census` + the production bindings
in `services.shared_search.production_bindings`. Zero writer / zero
RPC / zero deploy.

Usage (Owner-approved):

    railway run --service tai-api-prod \\
        python3 -m tools.shared_search.f2_census \\
        --json > f2_census_$(date +%Y%m%d).json

The command:

    1. imports supabase-py (production Client)
    2. builds all 8 Domain adapters via build_production_adapters
    3. runs services.shared_search.census.run_census over each
    4. emits a JSON blob with the DomainCensus dicts
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from services.shared_search import (
    build_production_adapters,
    run_census,
)


def _build_supabase_client():
    """Import supabase-py lazily so the CLI stays importable in tests
    where the library isn't installed."""
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true",
                        help="emit JSON to stdout (default: text summary)")
    args = parser.parse_args(argv)

    client = _build_supabase_client()
    adapters = build_production_adapters(client)
    results = [run_census(a).to_dict() for a in adapters]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for c in results:
            print(f"{c['domain']:>16s} object_type={c['object_type']:<16s} "
                  f"yielded={c['yielded_count']:>7d} "
                  f"unique={c['unique_canonical_ids']:>7d} "
                  f"dup={c['duplicate_canonical_ids']:>3d} "
                  f"published={c['published']:>7d} "
                  f"public={c['visibility_public']:>7d} "
                  f"blocked={len(c['blocked_subtypes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
