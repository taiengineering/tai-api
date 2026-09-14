"""Synthetic TAI-native DRAFT fixtures. Not a production canonical seed."""
from __future__ import annotations

from tools.risk01.analyze_3way import norm_name
from tools.risk03.contract import (
    FIXTURE_PROCESS_ID,
    FIXTURE_TASK_ALT_ID,
    FIXTURE_TASK_ID,
)


def synthetic_canonical_nodes() -> list[dict]:
    process = {
        "id": FIXTURE_PROCESS_ID,
        "canonical_code": "TAI.PROCESS.EARTHWORK",
        "node_kind": "PROCESS",
        "parent_id": None,
        "name": "토공사",
        "name_normalized": norm_name("토공사"),
        "description": "RISK-03 synthetic fixture PROCESS. Not production seed.",
        "status": "DRAFT",
        "origin_type": "TAI_NATIVE",
        "metadata": {"fixture": True, "production_seed": False},
    }
    task = {
        "id": FIXTURE_TASK_ID,
        "canonical_code": "TAI.TASK.TRENCHING",
        "node_kind": "TASK",
        "parent_id": FIXTURE_PROCESS_ID,
        "name": "터파기",
        "name_normalized": norm_name("터파기"),
        "description": "RISK-03 synthetic fixture TASK. Not production seed.",
        "status": "DRAFT",
        "origin_type": "TAI_NATIVE",
        "metadata": {"fixture": True, "production_seed": False},
    }
    return [process, task]


def ambiguity_canonical_nodes() -> list[dict]:
    nodes = synthetic_canonical_nodes()
    alt_process = {
        "id": "dddddddd-4444-4444-8444-000000000004",
        "canonical_code": "TAI.PROCESS.EARTHWORK.ALT",
        "node_kind": "PROCESS",
        "parent_id": None,
        "name": "굴착공사",
        "name_normalized": norm_name("굴착공사"),
        "description": "Ambiguity fixture PROCESS. Not production seed.",
        "status": "DRAFT",
        "origin_type": "TAI_NATIVE",
        "metadata": {"fixture": True, "production_seed": False},
    }
    alt_task = {
        "id": FIXTURE_TASK_ALT_ID,
        "canonical_code": "TAI.TASK.TRENCHING.ALT",
        "node_kind": "TASK",
        "parent_id": alt_process["id"],
        "name": "터파기",
        "name_normalized": norm_name("터파기"),
        "description": "Ambiguity fixture TASK with a different parent. Not production seed.",
        "status": "DRAFT",
        "origin_type": "TAI_NATIVE",
        "metadata": {"fixture": True, "production_seed": False},
    }
    return nodes + [alt_process, alt_task]
