"""WO-RISK-01 deterministic 3-way taxonomy measurement. No LLM. No production write."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path("artifacts/risk01")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "")
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"[\s/·ㆍ・,]+", " ", text)
    return text.strip()


def decode_best(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return enc, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return "latin1", raw.decode("latin1", "replace")


def parse_a_works(extracted_text: str) -> list[dict]:
    match = re.search(r"라\.\s*공종분류\(W\)(.*?)(마\.\s*|자재분류|자원분류|\n\s*M\s)", extracted_text, re.S)
    section = match.group(1) if match else ""
    section = re.sub(r"W-\d+", " ", section)
    nodes: list[dict] = []
    seen: set[str] = set()
    for code, name in re.findall(r"(\d{2,4})\.([^0-9]+)", section):
        name = norm_name(name)
        name = re.sub(r"\(공\s*백\).*$", "", name).strip()
        if not name or name.startswith("공란"):
            continue
        if code in seen:
            continue
        seen.add(code)
        level = 1 if len(code) == 2 else (2 if len(code) == 3 else 3)
        parent = None
        if level == 2:
            parent = code[:2]
        elif level == 3:
            parent = code[:3]
        nodes.append({"code": code, "name": name, "level": level, "parent": parent})
    by_code = {n["code"]: n for n in nodes}
    for node in nodes:
        parts: list[str] = []
        cur: dict | None = node
        chain: list[str] = []
        while cur:
            chain.append(cur["name"])
            cur = by_code.get(cur["parent"] or "")
        node["path"] = " > ".join(reversed(chain))
        node["path_norm"] = " > ".join(norm_name(p) for p in reversed(chain))
    return nodes


def read_csv_rows(path: Path) -> tuple[str, list[str], list[list[str]], dict]:
    raw = path.read_bytes()
    enc, text = decode_best(raw)
    physical = text.splitlines()
    blank = sum(1 for line in physical if not line.strip())
    parsed = list(csv.reader(io.StringIO(text)))
    if not parsed:
        return enc, [], [], {"bytes": len(raw), "physical_lines": 0, "blank_rows": blank}
    header = parsed[0]
    data = parsed[1:]
    malformed = [row for row in data if len(row) != len(header)]
    good = [row for row in data if len(row) == len(header)]
    counts = Counter(tuple(row) for row in good)
    stats = {
        "bytes": len(raw),
        "encoding": enc,
        "physical_lines": len(physical),
        "blank_rows": blank,
        "parsed_rows": len(data),
        "malformed_rows": len(malformed),
        "exact_duplicate_groups": sum(1 for n in counts.values() if n > 1),
        "exact_duplicate_extra": sum(n - 1 for n in counts.values() if n > 1),
        "unique_rows": len(counts),
        "sha256": sha256_file(path),
    }
    return enc, header, good, stats


def coverage(source: Iterable[str], target_index: dict[str, list[str]]) -> dict:
    matched = unmatched = ambiguous = one_to_one = one_to_n = 0
    for item in source:
        hits = target_index.get(item) or []
        if not hits:
            unmatched += 1
        elif len(hits) == 1:
            matched += 1
            one_to_one += 1
        else:
            matched += 1
            ambiguous += 1
            one_to_n += 1
    n = matched + unmatched
    return {
        "source_nodes": n,
        "exact_matched": matched,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "one_to_one": one_to_one,
        "one_to_n": one_to_n,
        "exact_pct": round(matched / n * 100.0, 2) if n else None,
        "unmatched_pct": round(unmatched / n * 100.0, 2) if n else None,
        "ambiguous_pct": round(ambiguous / n * 100.0, 2) if n else None,
    }


def index_by_name(nodes: list[dict], name_key: str, id_key: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        name = norm_name(node[name_key])
        if name:
            out[name].append(str(node[id_key]))
    return dict(out)


def index_by_path(nodes: list[dict], path_key: str, id_key: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        path = norm_name(node.get(path_key) or "")
        if path:
            out[path].append(str(node[id_key]))
    return dict(out)


def letter_bucket(values: Counter) -> dict[str, int]:
    buckets = Counter()
    for raw, n in values.items():
        text = (raw or "").strip()
        if not text or text == "NULL":
            buckets["NULL"] += n
            continue
        if re.fullmatch(r"[HML]\(\d+\)", text):
            buckets[text[0]] += n
        else:
            buckets["OTHER"] += n
            buckets[f"OTHER:{text}"] += n
    return dict(buckets)


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def main() -> dict:
    a_text = (ROOT / "source_a/cic_annex_extracted.txt").read_text(encoding="utf-8")
    a_nodes = parse_a_works(a_text)
    a_leaves = [n for n in a_nodes if n["level"] == 3]
    a_roots = [n for n in a_nodes if n["level"] == 1]

    b_enc, b_header, b_rows, b_stats = read_csv_rows(ROOT / "source_b/kosha_construction_process.csv")
    b_nodes = []
    for row in b_rows:
        rec = dict(zip(b_header, row))
        b_nodes.append(
            {
                "id": rec.get("번호") or "",
                "root": rec.get("공사종류") or "",
                "mid": rec.get("공종명") or "",
                "leaf": rec.get("세부공정명") or "",
                "path": " > ".join(
                    [rec.get("공사종류") or "", rec.get("공종명") or "", rec.get("세부공정명") or ""]
                ),
            }
        )
    b_mids = []
    seen_mid = set()
    for node in b_nodes:
        key = (norm_name(node["root"]), norm_name(node["mid"]))
        if key in seen_mid:
            continue
        seen_mid.add(key)
        b_mids.append({"id": f"{key[0]}|{key[1]}", "name": node["mid"], "path": f"{node['root']} > {node['mid']}"})

    c_enc, c_header, c_rows, c_stats = read_csv_rows(ROOT / "source_c/kalis_risk_profile.csv")
    c_work = []
    seen_c = set()
    c_tasks = []
    seen_task = set()
    hm_p = Counter()
    hm_s = Counter()
    for row in c_rows:
        rec = dict(zip(c_header, row))
        big = rec.get("공종분류(대)") or ""
        mid = rec.get("공종분류(중)") or ""
        task = rec.get("작업프로세스명") or ""
        hm_p[rec.get("사고가능성") or "NULL"] += 1
        hm_s[rec.get("사고심각성") or "NULL"] += 1
        wk = (norm_name(big), norm_name(mid))
        if wk not in seen_c and any(wk):
            seen_c.add(wk)
            c_work.append({"id": f"{wk[0]}|{wk[1]}", "name": mid or big, "big": big, "mid": mid, "path": f"{big} > {mid}"})
        tk = (wk[0], wk[1], norm_name(task))
        if tk not in seen_task and tk[2]:
            seen_task.add(tk)
            c_tasks.append({"id": "|".join(tk), "name": task, "path": f"{big} > {mid} > {task}"})

    a_name_idx = index_by_name(a_nodes, "name", "code")
    b_leaf_idx = index_by_name(b_nodes, "leaf", "id")
    b_mid_idx = index_by_name(b_mids, "name", "id")
    c_mid_idx = index_by_name(c_work, "name", "id")
    c_task_idx = index_by_name(c_tasks, "name", "id")
    a_path_idx = index_by_path(a_nodes, "path", "code")
    b_mid_path_idx = index_by_path(b_mids, "path", "id")
    b_leaf_path_idx = index_by_path(b_nodes, "path", "id")
    c_mid_path_idx = index_by_path(c_work, "path", "id")
    c_task_path_idx = index_by_path(c_tasks, "path", "id")

    a_names = [norm_name(n["name"]) for n in a_nodes]
    a_paths = [norm_name(n["path"]) for n in a_nodes]
    b_mid_names = [norm_name(n["name"]) for n in b_mids]
    b_mid_paths = [norm_name(n["path"]) for n in b_mids]
    b_leaf_names = [norm_name(n["leaf"]) for n in b_nodes]
    b_leaf_paths = [norm_name(n["path"]) for n in b_nodes]
    c_mid_names = [norm_name(n["name"]) for n in c_work]
    c_mid_paths = [norm_name(n["path"]) for n in c_work]
    c_task_names = [norm_name(n["name"]) for n in c_tasks]
    c_task_paths = [norm_name(n["path"]) for n in c_tasks]

    def pair(src_names, tgt_idx):
        return coverage(src_names, tgt_idx)

    mapping = {
        "A_to_B_mid": pair(a_names, b_mid_idx),
        "A_to_B_leaf": pair(a_names, b_leaf_idx),
        "B_mid_to_A": pair(b_mid_names, a_name_idx),
        "B_leaf_to_A": pair(b_leaf_names, a_name_idx),
        "A_to_C_mid": pair(a_names, c_mid_idx),
        "A_to_C_task": pair(a_names, c_task_idx),
        "C_mid_to_A": pair(c_mid_names, a_name_idx),
        "C_task_to_A": pair(c_task_names, a_name_idx),
        "B_mid_to_C_mid": pair(b_mid_names, c_mid_idx),
        "B_leaf_to_C_task": pair(b_leaf_names, c_task_idx),
        "C_mid_to_B_mid": pair(c_mid_names, b_mid_idx),
        "C_task_to_B_leaf": pair(c_task_names, b_leaf_idx),
        "A_path_to_B_mid_path": pair(a_paths, b_mid_path_idx),
        "A_path_to_B_leaf_path": pair(a_paths, b_leaf_path_idx),
        "B_mid_path_to_A_path": pair(b_mid_paths, a_path_idx),
        "B_leaf_path_to_A_path": pair(b_leaf_paths, a_path_idx),
        "A_path_to_C_mid_path": pair(a_paths, c_mid_path_idx),
        "A_path_to_C_task_path": pair(a_paths, c_task_path_idx),
        "C_mid_path_to_A_path": pair(c_mid_paths, a_path_idx),
        "C_task_path_to_A_path": pair(c_task_paths, a_path_idx),
        "B_mid_path_to_C_mid_path": pair(b_mid_paths, c_mid_path_idx),
        "B_leaf_path_to_C_task_path": pair(b_leaf_paths, c_task_path_idx),
        "C_mid_path_to_B_mid_path": pair(c_mid_paths, b_mid_path_idx),
        "C_task_path_to_B_leaf_path": pair(c_task_paths, b_leaf_path_idx),
    }

    def matrix_cell(name_cov: dict, path_cov: dict) -> dict:
        return {
            "exact_pct": name_cov["exact_pct"],
            "hierarchical_pct": path_cov["exact_pct"],
            "ambiguous_pct": name_cov["ambiguous_pct"],
            "unmatched_pct": name_cov["unmatched_pct"],
        }

    coverage_matrix = {
        "A_to_B": matrix_cell(mapping["A_to_B_mid"], mapping["A_path_to_B_mid_path"]),
        "B_to_A": matrix_cell(mapping["B_mid_to_A"], mapping["B_mid_path_to_A_path"]),
        "A_to_C": matrix_cell(mapping["A_to_C_mid"], mapping["A_path_to_C_mid_path"]),
        "C_to_A": matrix_cell(mapping["C_mid_to_A"], mapping["C_mid_path_to_A_path"]),
        "B_to_C": matrix_cell(mapping["B_mid_to_C_mid"], mapping["B_mid_path_to_C_mid_path"]),
        "C_to_B": matrix_cell(mapping["C_mid_to_B_mid"], mapping["C_mid_path_to_B_mid_path"]),
        "note": "Primary cells use 공종/mid names. Leaf/task name layers are in mapping.*. Hierarchical = native path exact after NFC/whitespace normalization. No LLM.",
    }

    a_name_counts = Counter(a_names)
    hashes = Counter()
    combo = Counter()
    loc_codes = Counter()
    for row in c_rows:
        hashes[hashlib.sha256("\u241f".join(row).encode("utf-8")).hexdigest()] += 1
        rec = dict(zip(c_header, row))
        loc = (rec.get("위험발생위치코드(중)") or "").strip()
        if loc:
            loc_codes[loc] += 1
        combo[
            (
                rec.get("공종분류(대)") or "",
                rec.get("공종분류(중)") or "",
                rec.get("작업프로세스명") or "",
                rec.get("위험발생객체분류(대)") or "",
                rec.get("위험발생객체분류(중)") or "",
                rec.get("위험발생위치분류(대)") or "",
                rec.get("위험발생위치분류(중)") or "",
                rec.get("위험발생위치분류(소)") or "",
                rec.get("사고원인") or "",
                rec.get("설계단계") or "",
                rec.get("시공단계") or "",
            )
        ] += 1
    identity = {
        "native_row_id_column": None,
        "method": "SHA256 of all 19 source fields joined by U+241F",
        "hashed_distinct": len(hashes),
        "hashed_singleton_rows": sum(1 for n in hashes.values() if n == 1),
        "hashed_collision_groups": sum(1 for n in hashes.values() if n > 1),
        "hashed_duplicate_extra": sum(n - 1 for n in hashes.values() if n > 1),
        "hashed_null": 0,
        "note": "collision groups are exact duplicate rows of the same 19-field tuple, not distinct-content identity collisions",
        "wo23_combo_distinct": len(combo),
        "wo23_combo_groups_with_repeats": sum(1 for n in combo.values() if n > 1),
        "wo23_combo_extra": sum(n - 1 for n in combo.values() if n > 1),
        "location_mid_code_nonempty": sum(loc_codes.values()),
        "location_mid_code_distinct": len(loc_codes),
        "semantic_looking_duplicates": "NOT_AUTO_CLASSIFIED",
    }

    unmatched_samples = {
        "B_mid_unmatched_in_A": sorted({n["name"] for n in b_mids if norm_name(n["name"]) not in a_name_idx})[:20],
        "C_mid_unmatched_in_A": sorted({n["name"] for n in c_work if norm_name(n["name"]) not in a_name_idx})[:20],
        "B_mid_unmatched_in_C": sorted({n["name"] for n in b_mids if norm_name(n["name"]) not in c_mid_idx})[:20],
        "C_mid_unmatched_in_B": sorted({n["name"] for n in c_work if norm_name(n["name"]) not in b_mid_idx})[:20],
    }
    matched_samples = {
        "C_mid_exact_in_A": sorted({n["name"] for n in c_work if norm_name(n["name"]) in a_name_idx}),
        "B_leaf_exact_in_A": sorted({n["leaf"] for n in b_nodes if norm_name(n["leaf"]) in a_name_idx})[:30],
    }

    field_map = [
        {"source_field": "시설물분류(대)", "tai_concept_candidate": "facility"},
        {"source_field": "시설물분류(중)", "tai_concept_candidate": "facility"},
        {"source_field": "시설물분류(소)", "tai_concept_candidate": "facility"},
        {"source_field": "공종분류(대)", "tai_concept_candidate": "construction_type / work_type"},
        {"source_field": "공종분류(중)", "tai_concept_candidate": "work_type"},
        {"source_field": "위험발생객체분류(대)", "tai_concept_candidate": "object / hazard object"},
        {"source_field": "위험발생객체분류(중)", "tai_concept_candidate": "object / hazard object"},
        {"source_field": "위험발생위치분류(대)", "tai_concept_candidate": "location"},
        {"source_field": "위험발생위치코드(중)", "tai_concept_candidate": "location (native code, not work code)"},
        {"source_field": "위험발생위치분류(중)", "tai_concept_candidate": "location"},
        {"source_field": "위험발생위치분류(소)", "tai_concept_candidate": "location"},
        {"source_field": "작업프로세스명", "tai_concept_candidate": "process / task"},
        {"source_field": "물적피해", "tai_concept_candidate": "property_damage"},
        {"source_field": "인적피해", "tai_concept_candidate": "human_damage"},
        {"source_field": "사고원인", "tai_concept_candidate": "cause"},
        {"source_field": "사고가능성", "tai_concept_candidate": "likelihood (source native, not TAI legal score)"},
        {"source_field": "사고심각성", "tai_concept_candidate": "severity (source native, not TAI legal score)"},
        {"source_field": "설계단계", "tai_concept_candidate": "design_control"},
        {"source_field": "시공단계", "tai_concept_candidate": "construction_control"},
    ]

    report = {
        "WO": "WO-RISK-01",
        "A": {
            "official_name": "건설정보분류체계 공종분류(W)",
            "authority": "국토교통부 / 운용 한국건설기술연구원 CALSPIA",
            "nodes": len(a_nodes),
            "roots": len(a_roots),
            "leaves": len(a_leaves),
            "native_code": True,
            "native_code_unique": len({n["code"] for n in a_nodes}) == len(a_nodes),
            "native_code_hierarchical": True,
            "name_distinct": len(a_name_counts),
            "name_collision_groups": sum(1 for n in a_name_counts.values() if n > 1),
            "pdf_sha256": sha256_file(ROOT / "source_a/cic_annex_works.txt"),
            "pdf_bytes": (ROOT / "source_a/cic_annex_works.txt").stat().st_size,
        },
        "B": {
            "dataset_id": "15087828",
            "headers": b_header,
            "encoding": b_enc,
            "native_code": False,
            **b_stats,
            "roots": len({norm_name(n["root"]) for n in b_nodes}),
            "mids": len(b_mids),
            "leaves": len({norm_name(n["leaf"]) for n in b_nodes if n["leaf"]}),
            "root_values": sorted({n["root"] for n in b_nodes}),
        },
        "C": {
            "dataset_id": "15090644",
            "headers": c_header,
            "encoding": c_enc,
            "native_work_code": False,
            "native_location_mid_code_field": "위험발생위치코드(중)",
            **c_stats,
            "work_big_n": len({norm_name(n["big"]) for n in c_work}),
            "work_mid_n": len(c_work),
            "work_mid_name_distinct": len({norm_name(n["name"]) for n in c_work}),
            "task_n": len(c_tasks),
            "portal_file_rows_field": 41239,
            "portal_description_approx": 47000,
            "portal_description_legacy": 55546,
            "COUNT_MATCH_vs_portal_file_rows_field": False,
            "SOURCE_METADATA_DRIFT": True,
            "likelihood": dict(hm_p),
            "severity": dict(hm_s),
            "likelihood_letter": letter_bucket(hm_p),
            "severity_letter": letter_bucket(hm_s),
        },
        "mapping": mapping,
        "coverage_matrix": coverage_matrix,
        "identity": identity,
        "field_map": field_map,
        "matched_samples": matched_samples,
        "unmatched_samples": unmatched_samples,
        "LLM_mapping": 0,
        "fuzzy_auto_accept": 0,
    }
    dest = ROOT / "reports/summary.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "schema").mkdir(parents=True, exist_ok=True)
    (ROOT / "mapping").mkdir(parents=True, exist_ok=True)
    (ROOT / "identity").mkdir(parents=True, exist_ok=True)
    (ROOT / "manifests").mkdir(parents=True, exist_ok=True)
    (ROOT / "schema/a_works.jsonl").write_text(
        "\n".join(json.dumps(n, ensure_ascii=False) for n in a_nodes) + "\n", encoding="utf-8"
    )
    (ROOT / "schema/b_nodes.jsonl").write_text(
        "\n".join(json.dumps(n, ensure_ascii=False) for n in b_nodes) + "\n", encoding="utf-8"
    )
    (ROOT / "schema/c_work.jsonl").write_text(
        "\n".join(json.dumps(n, ensure_ascii=False) for n in c_work) + "\n", encoding="utf-8"
    )
    (ROOT / "schema/c_tasks.jsonl").write_text(
        "\n".join(json.dumps(n, ensure_ascii=False) for n in c_tasks) + "\n", encoding="utf-8"
    )
    (ROOT / "schema/c_field_map.json").write_text(
        json.dumps(field_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "mapping/coverage_matrix.json").write_text(
        json.dumps(coverage_matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "mapping/unmatched_samples.json").write_text(
        json.dumps(unmatched_samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "identity/c_row_hash.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifests = {
        "A": {
            "filename": "cic_annex_works.txt",
            "note": "PDF bytes saved with .txt suffix; 법제처 건설사업정보운용지침 별표",
            "source_url": "https://www.calspia.go.kr/portal/intro/introStandard04.do",
            "downloaded_at": iso_mtime(ROOT / "source_a/cic_annex_works.txt"),
            "bytes": (ROOT / "source_a/cic_annex_works.txt").stat().st_size,
            "SHA256": sha256_file(ROOT / "source_a/cic_annex_works.txt"),
            "row_count": len(a_nodes),
        },
        "B": {
            "filename": "kosha_construction_process.csv",
            "portal_filename": "한국산업안전보건공단_건설업 공종별 세부공정 목록_20210910",
            "source_url": "https://www.data.go.kr/data/15087828/fileData.do",
            "downloaded_at": iso_mtime(ROOT / "source_b/kosha_construction_process.csv"),
            "bytes": b_stats["bytes"],
            "SHA256": b_stats["sha256"],
            "row_count": b_stats["parsed_rows"],
        },
        "C": {
            "filename": "kalis_risk_profile.csv",
            "portal_filename": "국토안전관리원_위험요소프로파일_20260814",
            "source_url": "https://www.data.go.kr/data/15090644/fileData.do",
            "downloaded_at": iso_mtime(ROOT / "source_c/kalis_risk_profile.csv"),
            "bytes": c_stats["bytes"],
            "SHA256": c_stats["sha256"],
            "row_count": c_stats["parsed_rows"],
        },
    }
    (ROOT / "manifests/source_snapshots.json").write_text(
        json.dumps(manifests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    out = main()
    print(json.dumps({k: out[k] for k in ("A", "B", "C")}, ensure_ascii=False, indent=2))
    print(json.dumps(out["coverage_matrix"], ensure_ascii=False, indent=2))
    print(json.dumps(out["identity"], ensure_ascii=False, indent=2))
    print(json.dumps(out["matched_samples"], ensure_ascii=False, indent=2))
