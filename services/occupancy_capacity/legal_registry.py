"""
H02 legal density ruleset loader and integrity guard.

RULESET_VERSION = "H02-2026-10-06-v1"
Covers TABLE A (초고층재난관리법 시행령 별표1, effective 2026-07-01)
     and TABLE B (피난방화구조규칙 별표1의2 제1호, effective 2026-10-06).
"""

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RULESET_VERSION = "H02-2026-10-06-v1"

_DATA_PATH = Path(__file__).parent / "data" / "legal_density_rules_2026_10_06.json"


@lru_cache(maxsize=1)
def _load_raw() -> tuple[dict[str, Any], str]:
    raw = _DATA_PATH.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    return data, sha256


def get_ruleset_sha256() -> str:
    _, sha256 = _load_raw()
    return sha256


def get_table_a_rows() -> list[dict[str, Any]]:
    data, _ = _load_raw()
    return data["table_a"]["rows"]


def get_table_b_ga_formulas() -> list[dict[str, Any]]:
    data, _ = _load_raw()
    return data["table_b_section_1_ga"]["formulas"]


def get_table_b_na_rows() -> list[dict[str, Any]]:
    data, _ = _load_raw()
    return data["table_b_section_1_na"]["rows"]


def get_full_ruleset() -> dict[str, Any]:
    data, _ = _load_raw()
    return data
