"""services/actor_census_shadow.py — Actor Census v1 SHADOW-ONLY lookup.

WO-ACTOR-SHADOW-INTEGRATION-IMPLEMENT-001.
production legal result에 영향 0. 실패는 절대 진단을 깨지 않는다(fail-open).
- flag ACTOR_CENSUS_SHADOW_ENABLED (default false). false/미설정이면 파일 IO 0.
- flag true 첫 호출에서 lazy singleton 로드 + SHA 검증. 검증 실패/파일 부재 → shadow 비활성(app healthy).
- lookup_status: MATCHED_ACTOR_CENSUS / OUTSIDE_ACTOR_CENSUS_SCOPE / ACTOR_CENSUS_ROW_MISSING / ATOM_MAPPING_BROKEN.
  OUTSIDE는 정상이며 NOT_APPLICABLE이 아니다. row_missing/broken은 anomaly로 log만. actor data는 결과를 바꾸지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger("services.actor_census_shadow")

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "actor_census")
_MAP_PATH = os.path.join(_DATA_DIR, "actor_shadow_map_v1.jsonl")
_MANIFEST_PATH = os.path.join(_DATA_DIR, "manifest.json")

_EXPECTED_CENSUS_SHA = "3a6965d07ff156e89c7a9f9ec31adaff49143f6826fdc12666b2a0dad7328628"

MATCHED = "MATCHED_ACTOR_CENSUS"
OUTSIDE = "OUTSIDE_ACTOR_CENSUS_SCOPE"
ROW_MISSING = "ACTOR_CENSUS_ROW_MISSING"
BROKEN = "ATOM_MAPPING_BROKEN"

_STATE: Dict[str, Any] = {"loaded": False, "ok": False, "map": {}, "manifest": {}}


def is_enabled() -> bool:
    return os.getenv("ACTOR_CENSUS_SHADOW_ENABLED", "").lower() in ("1", "true", "yes")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load() -> None:
    """lazy singleton load + SHA verify. 실패해도 예외 전파 없음(shadow 비활성)."""
    _STATE["loaded"] = True
    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        # census SHA anchor 검증
        census_path = os.path.join(_DATA_DIR, "actor_census_v1_final.jsonl")
        census_sha = _sha256_file(census_path)
        if manifest.get("actor_census_sha256") != _EXPECTED_CENSUS_SHA or census_sha != _EXPECTED_CENSUS_SHA:
            log.warning("actor_census_shadow disabled: census SHA mismatch manifest=%s file=%s expected=%s",
                        manifest.get("actor_census_sha256"), census_sha, _EXPECTED_CENSUS_SHA)
            _STATE["ok"] = False
            return
        # mapping SHA 검증
        map_sha = _sha256_file(_MAP_PATH)
        if manifest.get("mapping_sha256") != map_sha:
            log.warning("actor_census_shadow disabled: mapping SHA mismatch manifest=%s file=%s",
                        manifest.get("mapping_sha256"), map_sha)
            _STATE["ok"] = False
            return
        amap: Dict[str, Any] = {}
        with open(_MAP_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                amap[rec["atom_id"]] = rec
        _STATE["map"] = amap
        _STATE["manifest"] = manifest
        _STATE["ok"] = True
        log.info("actor_census_shadow loaded: atoms=%d counts=%s", len(amap), manifest.get("counts"))
    except Exception as e:  # noqa: BLE001 — fail-open
        log.warning("actor_census_shadow disabled: load failed: %s", e)
        _STATE["ok"] = False


def _lookup_one(atom_id: Optional[str]) -> Dict[str, Any]:
    rec = _STATE["map"].get(atom_id) if atom_id else None
    if rec is None:
        # 매핑 아티팩트에 없는 atom = 결정론 체인 밖 → anomaly(정상 아님)
        return {"atom_id": atom_id, "shadow_status": BROKEN, "family_root_id": None}
    status = rec.get("scope_status")
    out: Dict[str, Any] = {
        "atom_id": atom_id,
        "shadow_status": status,
        "family_root_id": rec.get("family_root_id"),
    }
    if status == MATCHED and isinstance(rec.get("actor"), dict):
        a = rec["actor"]
        out["actor_resolution_mode"] = a.get("resolution_mode")
        out["actor_classes"] = a.get("actor_class")
        out["reference_actor_status"] = a.get("reference_actor_status")
        out["source_complete_for_actor"] = a.get("source_complete_for_actor")
    return out


def shadow_lookup(obligations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """SHADOW-ONLY. obligations(runtime)에서 atom_id를 뽑아 census lookup 결과를 반환.
    반환값은 관측용이며 legal result를 바꾸지 않는다. flag off/실패 시 None.
    예외를 절대 밖으로 던지지 않는다(fail-open)."""
    try:
        if not is_enabled():
            return None
        if not _STATE["loaded"]:
            _load()
        if not _STATE["ok"]:
            return None
        records: List[Dict[str, Any]] = []
        counts = {MATCHED: 0, OUTSIDE: 0, ROW_MISSING: 0, BROKEN: 0}
        for o in obligations or []:
            # obligation.atom_id = source_atom_ids[0] (rtm/api.py 계약). 없으면 source_atom_ids 첫 원소.
            atom_id = o.get("atom_id")
            if not atom_id:
                sids = o.get("source_atom_ids") or []
                atom_id = sids[0] if sids else None
            r = _lookup_one(atom_id)
            records.append(r)
            st = r["shadow_status"]
            counts[st] = counts.get(st, 0) + 1
        summary = {
            "actor_census_version": _STATE["manifest"].get("actor_census_version"),
            "actor_census_sha256": _STATE["manifest"].get("actor_census_sha256"),
            "mapping_version": _STATE["manifest"].get("mapping_version"),
            "mapping_sha256": _STATE["manifest"].get("mapping_sha256"),
            "counts": counts,
            "records": records,
        }
        if counts[BROKEN] or counts[ROW_MISSING]:
            log.warning("actor_census_shadow anomaly: broken=%d row_missing=%d", counts[BROKEN], counts[ROW_MISSING])
        else:
            log.info("actor_census_shadow: matched=%d outside=%d", counts[MATCHED], counts[OUTSIDE])
        return summary
    except Exception as e:  # noqa: BLE001 — fail-open: 진단을 절대 깨지 않는다
        log.warning("actor_census_shadow lookup failed (non-blocking): %s", e)
        return None
