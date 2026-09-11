"""WP-1C-5A storage probe. Default dry-run: KOSHA GET 0, R2 PUT 0, version DML 0."""
from __future__ import annotations

import json
import os

from services.kosha_safety_materials.enrichment import snapshot_precondition
from services.kosha_safety_materials.storage.r2_store import R2Error, credentials_from_env
from services.kosha_safety_materials.writer import SupabaseStore


def dry_run_probe(store) -> dict:
    pre = snapshot_precondition(store)
    return {
        "status": "DRY_RUN",
        "run_snapshot_id": pre["snapshot"]["id"],
        "membership": pre["membership_count"],
        "kosha_binary_get": 0,
        "r2_put": 0,
        "version_dml": 0,
        "wrangler": 0,
    }


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if not os.getenv("SUPABASE_SERVICE_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_SERVICE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    store = SupabaseStore()
    out = dry_run_probe(store)
    try:
        credentials_from_env()
        out["r2_credentials"] = "present"
    except R2Error as e:
        out["r2_credentials"] = e.code
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
