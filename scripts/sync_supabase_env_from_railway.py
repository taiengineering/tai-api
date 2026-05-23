#!/usr/bin/env python3
"""Railway tai-api-prod 변수 → .env 의 SUPABASE_* 3개만 동기화."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def main() -> int:
    try:
        proc = subprocess.run(
            ["railway", "variables", "--json"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
    except subprocess.CalledProcessError as e:
        print("railway variables failed:", e.stderr or e)
        return 1

    data = json.loads(proc.stdout)
    updates = {
        "SUPABASE_URL": data.get("SUPABASE_URL"),
        "SUPABASE_KEY": data.get("SUPABASE_KEY"),
        "SUPABASE_SERVICE_ROLE_KEY": data.get("SUPABASE_SERVICE_ROLE_KEY")
        or data.get("SUPABASE_SERVICE_KEY"),
    }
    missing = [k for k, v in updates.items() if not v]
    if missing:
        print("Railway에 없음:", ", ".join(missing))
        return 1

    if not ENV_PATH.exists():
        print(f".env 없음: {ENV_PATH}")
        return 1

    lines = ENV_PATH.read_text().splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line.strip() and not line.strip().startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)

    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(out) + "\n")
    print("Synced from Railway:", ", ".join(updates))
    for k, v in updates.items():
        print(f"  {k}: len={len(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
