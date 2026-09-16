"""Deterministic master/classification builder from committed authority snapshots.

Mechanical wrap-join only. No LLM, no fuzzy matching, no name-based identity.
Mixture / residual rows are not named materials.
SPECIAL is emitted only for the explicit unconditional in-list marker.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from services.material_source.registry import ALLOWED_CLASSIFICATION_CODES

AUTHORITY_DIR = Path(__file__).resolve().parent / "authority"

WRAP_JOINS: Tuple[Tuple[str, str], ...] = (
    ("특별관리물 질", "특별관리물질"),
    ("특별관리 물질", "특별관리물질"),
    ("경 우만", "경우만"),
    ("화합 물만", "화합물만"),
    ("inorganic co mpounds", "inorganic compounds"),
    ("혼 합물", "혼합물"),
)

CAS_WRAP_A = re.compile(r"(\d{2,7}-\d{1,2})\s+(-\d+)")
CAS_WRAP_B = re.compile(r"(\d{2,7}-\d{2}-)\s+(\d+)")
CAS_RE = re.compile(r"\d{2,7}-\d{2}-\d+")
ITEM_NO_PREFIX = re.compile(r"^\s*\d+\.\s*")

MANAGED = "MANAGED_HAZARDOUS_SUBSTANCE"
PERMIT = "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE"
SPECIAL = "SPECIAL_MANAGEMENT_SUBSTANCE"


def join_wraps(text: str) -> str:
    out = text or ""
    for src, dst in WRAP_JOINS:
        out = out.replace(src, dst)
    out = CAS_WRAP_A.sub(r"\1\2", out)
    out = CAS_WRAP_B.sub(r"\1\2", out)
    return re.sub(r"\s+", " ", out).strip()


def extract_cas_no(text: str) -> Optional[str]:
    match = CAS_RE.search(join_wraps(text))
    return match.group(0) if match else None


def display_name_from_item(text: str) -> str:
    t = join_wraps(text)
    t = ITEM_NO_PREFIX.sub("", t)
    t = re.sub(r"\(특별관리물질.*$", "", t).strip()
    t = re.sub(r"\(벤젠을.*$", "", t).strip()
    t = re.sub(r"\(불용성.*$", "", t).strip()
    t = re.sub(r"\(삼산화.*$", "", t).strip()
    t = re.sub(r"\(6가크롬.*$", "", t).strip()
    t = re.sub(r"\(pH.*$", "", t).strip()
    return t.rstrip(" .")


def special_status(text: str) -> str:
    """Return NONE / UNCONDITIONAL / CONDITIONAL from explicit source markers."""
    t = join_wraps(text)
    if "특별관리" not in t:
        return "NONE"
    if "경우만" in t:
        return "CONDITIONAL"
    if "다만" in t:
        return "CONDITIONAL"
    if re.search(r"만\s*특별관리물질", t):
        return "CONDITIONAL"
    if "pH" in t and "특별관리" in t:
        return "CONDITIONAL"
    if "(특별관리물질)" in t:
        return "UNCONDITIONAL"
    return "CONDITIONAL"


def is_mixture_row(text: str, item_no: int, declared_count: int) -> bool:
    t = join_wraps(text)
    if "함유한 혼합물" in t:
        return True
    if item_no > declared_count:
        return True
    return False


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _class_row(
    material_key: str,
    code: str,
    source_ref: str,
    source_version: str,
    source_hash: str,
) -> Dict[str, Any]:
    if code not in ALLOWED_CLASSIFICATION_CODES:
        raise ValueError("unsupported classification: {}".format(code))
    return {
        "material_key": material_key,
        "classification_code": code,
        "source_ref": source_ref,
        "source_version": source_version,
        "source_hash": source_hash,
        "active": True,
    }


def build_from_snapshots(
    authority_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    root = Path(authority_dir) if authority_dir else AUTHORITY_DIR
    provenance = _load_json(root / "provenance.json")
    app12_items: Sequence[Mapping[str, Any]] = _load_json(
        root / "ishl_rule_app12_items.json"
    )
    art88_items: Sequence[Mapping[str, Any]] = _load_json(
        root / "ishl_enf_art88_items.json"
    )
    app12_meta = provenance["SOURCE_OBJECT"][0]
    art88_meta = provenance["SOURCE_OBJECT"][1]

    materials: List[Dict[str, Any]] = []
    classifications: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    conditional_special: List[Dict[str, Any]] = []

    app12_hash = app12_meta["source_hash"]
    app12_version = app12_meta["version_no"]
    app12_date = app12_meta["enforcement_date"]

    for item in app12_items:
        group_no = int(item["group_no"])
        item_no = int(item["item_no"])
        declared = int(item["declared_count"])
        raw_text = item["item_text"]
        joined = join_wraps(raw_text)
        source_item_key = "G{}-I{:03d}".format(group_no, item_no)
        material_key = "ISHL-RULE-APP12-{}".format(source_item_key)
        source_ref = "law_appendix:{}#{}".format(
            app12_meta["appendix_id"], source_item_key
        )
        if is_mixture_row(raw_text, item_no, declared):
            skipped.append(
                {
                    "material_key": material_key,
                    "reason": "MIXTURE",
                    "source_ref": source_ref,
                }
            )
            continue
        materials.append(
            {
                "material_key": material_key,
                "display_name": display_name_from_item(raw_text),
                "cas_no": extract_cas_no(raw_text),
                "source_system": "LEG_LAW_CORPUS",
                "source_item_key": source_item_key,
                "source_ref": source_ref,
                "source_version": app12_version,
                "source_effective_date": app12_date,
                "source_hash": app12_hash,
                "active": True,
            }
        )
        classifications.append(
            _class_row(material_key, MANAGED, source_ref, app12_version, app12_hash)
        )
        status = special_status(raw_text)
        if status == "UNCONDITIONAL":
            classifications.append(
                _class_row(
                    material_key, SPECIAL, source_ref, app12_version, app12_hash
                )
            )
        elif status == "CONDITIONAL":
            conditional_special.append(
                {
                    "material_key": material_key,
                    "source_ref": source_ref,
                    "item_text": joined,
                }
            )

    art88_concat = "\n".join(
        "{}|{}".format(row["item_internal_key"], row["item_text"])
        for row in art88_items
    )
    art88_hash = _sha256_text(art88_concat)
    art88_version = art88_meta["version_no"]
    art88_date = art88_meta["enforcement_date"]

    for item in art88_items:
        kind = item.get("kind")
        item_key = str(item["item_internal_key"]).rstrip(".")
        material_key = "ISHL-ENF-ART88-{}".format(item_key)
        source_ref = "law_item:{}".format(item_key)
        if kind in ("MIXTURE", "RESIDUAL"):
            skipped.append(
                {
                    "material_key": material_key,
                    "reason": kind,
                    "source_ref": source_ref,
                }
            )
            continue
        if kind != "NAMED":
            raise ValueError("unknown art88 kind: {}".format(kind))
        materials.append(
            {
                "material_key": material_key,
                "display_name": display_name_from_item(item["item_text"]),
                "cas_no": extract_cas_no(item["item_text"]),
                "source_system": "LEG_LAW_CORPUS",
                "source_item_key": item_key,
                "source_ref": source_ref,
                "source_version": art88_version,
                "source_effective_date": art88_date,
                "source_hash": art88_hash,
                "active": True,
            }
        )
        classifications.append(
            _class_row(material_key, PERMIT, source_ref, art88_version, art88_hash)
        )

    materials.sort(key=lambda row: row["material_key"])
    classifications.sort(
        key=lambda row: (row["material_key"], row["classification_code"])
    )

    def _count(code: str) -> int:
        return sum(1 for row in classifications if row["classification_code"] == code)

    catalog = {
        "materials": materials,
        "classifications": classifications,
        "skipped": skipped,
        "conditional_special": conditional_special,
        "counts": {
            "SOURCE_ROW_COUNT": len(app12_items) + len(art88_items),
            "MATERIAL_COUNT": len(materials),
            "MANAGED_COUNT": _count(MANAGED),
            "PERMIT_REQUIRED_COUNT": _count(PERMIT),
            "SPECIAL_MANAGEMENT_COUNT": _count(SPECIAL),
            "SKIPPED_COUNT": len(skipped),
            "CONDITIONAL_SPECIAL_COUNT": len(conditional_special),
        },
    }
    catalog["MATERIAL_MASTER_HASH"] = _sha256_text(_canonical_json(materials))
    catalog["CLASSIFICATION_HASH"] = _sha256_text(_canonical_json(classifications))
    catalog["CATALOG_HASH"] = _sha256_text(
        _canonical_json(
            {
                "materials": materials,
                "classifications": classifications,
                "counts": catalog["counts"],
            }
        )
    )
    return catalog


def write_manifests(authority_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(authority_dir) if authority_dir else AUTHORITY_DIR
    catalog = build_from_snapshots(root)
    (root / "material_master.manifest.json").write_text(
        json.dumps(catalog["materials"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "classifications.manifest.json").write_text(
        json.dumps(catalog["classifications"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = dict(catalog["counts"])
    counts.update(
        {
            "MATERIAL_MASTER_HASH": catalog["MATERIAL_MASTER_HASH"],
            "CLASSIFICATION_HASH": catalog["CLASSIFICATION_HASH"],
            "CATALOG_HASH": catalog["CATALOG_HASH"],
            "APP12_SOURCE_HASH": json.loads(
                (root / "provenance.json").read_text(encoding="utf-8")
            )["SOURCE_OBJECT"][0]["source_hash"],
        }
    )
    (root / "source_provenance.manifest.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sums = []
    for name in (
        "ishl_rule_app12_items.json",
        "ishl_enf_art88_items.json",
        "provenance.json",
        "material_master.manifest.json",
        "classifications.manifest.json",
        "source_provenance.manifest.json",
    ):
        digest = _sha256_bytes((root / name).read_bytes())
        sums.append("{}  {}".format(digest, name))
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return catalog


def load_catalog(authority_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load committed manifests. Rebuilds if manifests are absent (tests)."""
    root = Path(authority_dir) if authority_dir else AUTHORITY_DIR
    master_path = root / "material_master.manifest.json"
    class_path = root / "classifications.manifest.json"
    if master_path.exists() and class_path.exists():
        materials = json.loads(master_path.read_text(encoding="utf-8"))
        classifications = json.loads(class_path.read_text(encoding="utf-8"))
        rebuilt = build_from_snapshots(root)
        if rebuilt["materials"] != materials or rebuilt["classifications"] != classifications:
            raise RuntimeError("committed material manifests drifted from authority snapshots")
        return rebuilt
    return build_from_snapshots(root)


if __name__ == "__main__":
    out = write_manifests()
    print(json.dumps(out["counts"], ensure_ascii=False, indent=2))
    print("MATERIAL_MASTER_HASH", out["MATERIAL_MASTER_HASH"])
    print("CLASSIFICATION_HASH", out["CLASSIFICATION_HASH"])
    print("CATALOG_HASH", out["CATALOG_HASH"])
