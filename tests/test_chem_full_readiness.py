"""WO-CHEM-FULL-READINESS-001 — incremental writer tests.

F1..F8 fixture tests that verify the shared execute_incremental_write
helper preserves canonical identity while enabling NEW / UNCHANGED /
CHANGED / CONFLICT semantics against an already-populated DB.
"""
from __future__ import annotations

import uuid

import pytest

from services.kosha_msds import materialize_writer as w


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _plan_bundle(
    chem_id: str,
    *,
    source_content_hash: str,
    detail_status: str = "COMPLETE",
    section_hashes: dict[int, str] | None = None,
    chemical_name_ko: str | None = None,
    chemical_name_en: str | None = None,
    cas_no: str | None = None,
    last_date: str | None = None,
) -> dict:
    """Shape of a single line in materialize_plan.jsonl."""
    section_hashes = section_hashes or {n: f"H-{chem_id}-{n}" for n in range(1, 17)}
    return {
        "chem_id": chem_id,
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "identity_status": "READY",
        "identity_reason": None,
        "chemical_name_ko": chemical_name_ko or f"화학{chem_id}",
        "chemical_name_en": chemical_name_en or f"Chem{chem_id}",
        "cas_no": cas_no,
        "ke_no": None,
        "en_no": None,
        "un_no": None,
        "last_date": last_date,
        "source_content_hash": source_content_hash,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "detail_status": detail_status,
        "sections": [
            {
                "section_no": n,
                "section_hash": section_hashes[n],
                "result_code": "00",
                "result_message": "NORMAL SERVICE.",
                "fetched_at": "2026-09-18T00:00:00Z",
                "item_count": 1,
                "payload_json": [{"msdsItemCode": f"C{n:02d}"}],
            }
            for n in sorted(section_hashes.keys())
        ],
    }


def _plan_inputs(chemicals: list[dict]) -> w.MaterializePlanInputs:
    manifest = {
        "wo": "WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001",
        "adapter_version": "CHEM05_V1",
        "responses_sha256": "resp-sha",
        "plan_file_sha256": "plan-file-sha",
        "plan_semantic_sha256": "plan-sem-sha",
        "execute_eligible": True,
        "execute_block_reasons": [],
        "snapshot": {"metrics_json": {}},
    }
    report = {"plan_sha256": "plan-sem-sha", "responses_sha256": "resp-sha",
              "execute_eligible": True}
    return w.MaterializePlanInputs(
        manifest=manifest, report=report, chemicals=tuple(chemicals),
    )


def _existing_chem_row(chem_id: str, *, id: str, content_id: str,
                       source_content_hash: str,
                       chemical_name_ko: str | None = None,
                       cas_no: str | None = None) -> dict:
    return {
        "id": id,
        "content_id": content_id,
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": chemical_name_ko,
        "chemical_name_en": f"Chem{chem_id}",
        "cas_no": cas_no,
        "ke_no": None, "en_no": None, "un_no": None,
        "last_date": None,
        "source_content_hash": source_content_hash,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "is_current": False,
    }


def _existing_section_row(chemical_id: str, section_no: int,
                          section_hash: str) -> dict:
    return {
        "chemical_id": chemical_id,
        "section_no": section_no,
        "payload_json": [{"msdsItemCode": f"C{section_no:02d}"}],
        "section_hash": section_hash,
        "result_code": "00",
        "result_message": "NORMAL SERVICE.",
        "fetched_at": "2026-09-17T00:00:00Z",
    }


def _deterministic_id_factory():
    """Deterministic UUID + content_id sequence so test assertions can
    reason about which new UUID a NEW chemical received."""
    counter = {"n": 0}
    def _next() -> tuple[str, str]:
        counter["n"] += 1
        chem_uuid = f"11111111-1111-1111-1111-{counter['n']:012d}"
        return chem_uuid, f"CHEM:{chem_uuid}"
    return _next


# ---------------------------------------------------------------------------
# F1 — empty DB
# ---------------------------------------------------------------------------


def test_F1_empty_db_all_new():
    """Empty DB, 3 plan chemicals → all NEW; 3 chemical inserts + 48 section
    inserts + 3 memberships. Identical semantics to the pre-refactor SEO
    preview executor's empty-DB behavior on 1,997 chemicals."""
    inputs = _plan_inputs([
        _plan_bundle(f"P{i:05d}", source_content_hash=f"H{i}")
        for i in range(1, 4)
    ])
    store = w.MemoryMaterializeStore()
    report = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-F1",
        id_factory=_deterministic_id_factory(),
    )
    assert report.chemicals_new == 3
    assert report.chemicals_unchanged == 0
    assert report.chemicals_changed == 0
    assert report.chemicals_conflict == 0
    assert report.sections_new == 3 * 16
    assert report.sections_unchanged == 0
    assert report.sections_changed == 0
    assert report.membership_rows == 3
    # Each chemical got a fresh CHEM:<uuid> content_id.
    for row in store._chemicals_by_key.values():
        assert row["content_id"].startswith("CHEM:")


# ---------------------------------------------------------------------------
# F2 — exact replay
# ---------------------------------------------------------------------------


def test_F2_exact_replay_all_unchanged_zero_writes():
    """DB already has the same 1,997 (fixture-scaled to 3). Replay must
    produce 0 chemical inserts + 0 section inserts + 0 UPDATEs, but 3
    membership rows for the new snapshot."""
    ids = [
        ("P00001", "uu-P00001"),
        ("P00002", "uu-P00002"),
        ("P00003", "uu-P00003"),
    ]
    chems_existing = [
        _existing_chem_row(cid, id=uid, content_id=f"CHEM:{uid}",
                           source_content_hash=f"H-{cid}")
        for cid, uid in ids
    ]
    sections_existing = [
        _existing_section_row(uid, n, f"H-{cid}-{n}")
        for cid, uid in ids for n in range(1, 17)
    ]

    plan = [
        _plan_bundle(cid, source_content_hash=f"H-{cid}",
                     section_hashes={n: f"H-{cid}-{n}" for n in range(1, 17)})
        for cid, _ in ids
    ]
    inputs = _plan_inputs(plan)
    store = w.MemoryMaterializeStore(
        chemicals=chems_existing, sections=sections_existing,
    )

    # Instrument the store to count writes.
    calls = {"insert_chem": 0, "insert_sec": 0, "insert_mem": 0,
             "update_chem": 0, "update_sec": 0}
    orig_ic = store.insert_chemicals
    orig_is_ = store.insert_sections
    orig_im = store.insert_snapshot_items
    orig_uc = store.update_chemical
    orig_us = store.update_section

    def _ic(rows):
        calls["insert_chem"] += len(rows)
        orig_ic(rows)

    def _is(rows):
        calls["insert_sec"] += len(rows)
        orig_is_(rows)

    def _im(rows):
        calls["insert_mem"] += len(rows)
        orig_im(rows)

    def _uc(*a, **kw):
        calls["update_chem"] += 1
        orig_uc(*a, **kw)

    def _us(*a, **kw):
        calls["update_sec"] += 1
        orig_us(*a, **kw)

    store.insert_chemicals = _ic
    store.insert_sections = _is
    store.insert_snapshot_items = _im
    store.update_chemical = _uc
    store.update_section = _us

    report = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-F2",
        id_factory=_deterministic_id_factory(),
    )
    assert report.chemicals_new == 0
    assert report.chemicals_unchanged == 3
    assert report.chemicals_changed == 0
    assert report.sections_new == 0
    assert report.sections_unchanged == 3 * 16
    assert report.sections_changed == 0
    assert report.membership_rows == 3
    # Exactly zero chemical / section writes; membership only.
    assert calls["insert_chem"] == 0
    assert calls["insert_sec"] == 0
    assert calls["update_chem"] == 0
    assert calls["update_sec"] == 0
    assert calls["insert_mem"] == 3
    # And critically, the pre-existing chemicals kept their id + content_id.
    for cid, uid in ids:
        row = store.get_chemical_by_natural_key("KOSHA_MSDS", cid)
        assert row["id"] == uid
        assert row["content_id"] == f"CHEM:{uid}"


# ---------------------------------------------------------------------------
# F3 — Preview → expanded corpus
# ---------------------------------------------------------------------------


def test_F3_preview_to_expanded_corpus():
    """DB has 3 (preview). Plan has 5 (preview + 2 new). Expected:
    3 UNCHANGED + 2 NEW; membership=5."""
    existing_ids = [("E00001", "uu-E00001"),
                    ("E00002", "uu-E00002"),
                    ("E00003", "uu-E00003")]
    chems_existing = [
        _existing_chem_row(cid, id=uid, content_id=f"CHEM:{uid}",
                           source_content_hash=f"H-{cid}")
        for cid, uid in existing_ids
    ]
    sections_existing = [
        _existing_section_row(uid, n, f"H-{cid}-{n}")
        for cid, uid in existing_ids for n in range(1, 17)
    ]

    plan = [
        _plan_bundle(cid, source_content_hash=f"H-{cid}",
                     section_hashes={n: f"H-{cid}-{n}" for n in range(1, 17)})
        for cid, _ in existing_ids
    ] + [
        _plan_bundle("N00001", source_content_hash="H-N00001"),
        _plan_bundle("N00002", source_content_hash="H-N00002"),
    ]
    inputs = _plan_inputs(plan)
    store = w.MemoryMaterializeStore(
        chemicals=chems_existing, sections=sections_existing,
    )

    report = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-F3",
        id_factory=_deterministic_id_factory(),
    )
    assert report.chemicals_unchanged == 3
    assert report.chemicals_new == 2
    assert report.chemicals_changed == 0
    assert report.membership_rows == 5
    # Existing chemicals kept their identity.
    for cid, uid in existing_ids:
        row = store.get_chemical_by_natural_key("KOSHA_MSDS", cid)
        assert row["id"] == uid
        assert row["content_id"] == f"CHEM:{uid}"


# ---------------------------------------------------------------------------
# F4 — CHANGED chemical
# ---------------------------------------------------------------------------


def test_F4_changed_chemical_preserves_identity_updates_mutables():
    """Existing chemical has old source_content_hash + old cas_no.
    Plan carries new source_content_hash + new cas_no. Result:
    UPDATE mutable fields; id + content_id + source_key + chem_id preserved.
    """
    existing = _existing_chem_row("C00001", id="uu-C00001",
                                  content_id="CHEM:uu-C00001",
                                  source_content_hash="H_OLD",
                                  cas_no="00-00-0")
    plan = [_plan_bundle("C00001", source_content_hash="H_NEW",
                         cas_no="71-43-2",
                         section_hashes={n: f"H_OLD-{n}" for n in range(1, 17)})]
    inputs = _plan_inputs(plan)
    store = w.MemoryMaterializeStore(
        chemicals=[existing],
        sections=[_existing_section_row("uu-C00001", n, f"H_OLD-{n}")
                  for n in range(1, 17)],
    )
    report = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-F4",
        id_factory=_deterministic_id_factory(),
    )
    assert report.chemicals_changed == 1
    assert report.chemicals_new == 0
    assert report.chemicals_unchanged == 0
    row = store.get_chemical_by_natural_key("KOSHA_MSDS", "C00001")
    # Canonical identity — unchanged.
    assert row["id"] == "uu-C00001"
    assert row["content_id"] == "CHEM:uu-C00001"
    assert row["source_id"] == "KOSHA_MSDS"
    assert row["source_key"] == "C00001"
    assert row["chem_id"] == "C00001"
    # Mutable columns — updated.
    assert row["source_content_hash"] == "H_NEW"
    assert row["cas_no"] == "71-43-2"


# ---------------------------------------------------------------------------
# F5 — CHANGED section
# ---------------------------------------------------------------------------


def test_F5_changed_section_preserves_identity_updates_payload():
    existing = _existing_chem_row("C00002", id="uu-C00002",
                                  content_id="CHEM:uu-C00002",
                                  source_content_hash="H_SAME")
    # Section 3 is CHANGED; sections 1,2,4..16 are UNCHANGED.
    plan_section_hashes = {n: f"H_OLD-{n}" for n in range(1, 17)}
    plan_section_hashes[3] = "H_NEW_SEC3"

    plan = [_plan_bundle("C00002", source_content_hash="H_SAME",
                         section_hashes=plan_section_hashes)]
    inputs = _plan_inputs(plan)
    existing_sections = [
        _existing_section_row("uu-C00002", n, f"H_OLD-{n}")
        for n in range(1, 17)
    ]
    store = w.MemoryMaterializeStore(
        chemicals=[existing], sections=existing_sections,
    )
    report = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-F5",
        id_factory=_deterministic_id_factory(),
    )
    assert report.sections_changed == 1
    assert report.sections_unchanged == 15
    assert report.sections_new == 0
    row = store.get_section("uu-C00002", 3)
    assert row["chemical_id"] == "uu-C00002"  # identity preserved
    assert row["section_no"] == 3              # identity preserved
    assert row["section_hash"] == "H_NEW_SEC3"


# ---------------------------------------------------------------------------
# F6 — identity conflict
# ---------------------------------------------------------------------------


def test_F6_identity_conflict_blocks_before_any_write():
    """Existing row shares the natural key (source_id, source_key) but
    disagrees on chem_id. Writer must raise IncrementalWriteBlocked
    without emitting any INSERT or UPDATE."""
    bad_existing = _existing_chem_row("C00001", id="uu-C00001",
                                      content_id="CHEM:uu-C00001",
                                      source_content_hash="H")
    bad_existing["chem_id"] = "999999"  # identity mismatch
    plan = [_plan_bundle("C00001", source_content_hash="H")]
    inputs = _plan_inputs(plan)
    store = w.MemoryMaterializeStore(chemicals=[bad_existing])

    calls = {"insert": 0, "update": 0}
    orig_ic = store.insert_chemicals
    orig_uc = store.update_chemical
    store.insert_chemicals = lambda rows: (calls.__setitem__("insert", calls["insert"] + len(rows)), orig_ic(rows))[1]
    store.update_chemical = lambda *a, **kw: (calls.__setitem__("update", calls["update"] + 1), orig_uc(*a, **kw))[1]

    with pytest.raises(w.IncrementalWriteBlocked):
        w.execute_incremental_write(
            inputs, store=store, snapshot_id="snap-F6",
            id_factory=_deterministic_id_factory(),
        )
    assert calls["insert"] == 0
    assert calls["update"] == 0


# ---------------------------------------------------------------------------
# F7 — partial failure replay
# ---------------------------------------------------------------------------


def test_F7_partial_failure_replay_no_duplicate_key_errors():
    """Simulate a crash after some NEW rows landed but before the whole
    batch finished. Re-running the same plan against the resulting DB must
    reclassify the landed rows as UNCHANGED (no duplicate-key INSERT).
    Deterministic id_factory ensures the resulting DB matches the fresh
    execution."""
    # Full plan: 5 chemicals, all NEW on empty DB.
    plan = [_plan_bundle(f"P{i:05d}", source_content_hash=f"H{i}")
            for i in range(1, 6)]
    inputs = _plan_inputs(plan)

    # First run: pretend the writer crashed after inserting only the
    # first 2 chemicals. Simulate by directly inserting them into a
    # fresh store with deterministic UUIDs.
    idf1 = _deterministic_id_factory()
    partial_store = w.MemoryMaterializeStore()
    partial_chems: list[dict] = []
    partial_secs: list[dict] = []
    for bundle in plan[:2]:
        chem_uuid, content_id = idf1()
        partial_chems.append({
            "id": chem_uuid, "content_id": content_id,
            "source_id": "KOSHA_MSDS", "source_key": bundle["chem_id"],
            "chem_id": bundle["chem_id"],
            "identity_status": "READY",
            "chemical_name_ko": bundle["chemical_name_ko"],
            "chemical_name_en": bundle["chemical_name_en"],
            "cas_no": None, "ke_no": None, "en_no": None, "un_no": None,
            "last_date": None,
            "source_content_hash": bundle["source_content_hash"],
            "source_dataset_url": bundle["source_dataset_url"],
            "is_current": False,
        })
        for section in bundle["sections"]:
            partial_secs.append({
                "chemical_id": chem_uuid,
                "section_no": section["section_no"],
                "payload_json": section["payload_json"],
                "section_hash": section["section_hash"],
                "result_code": section["result_code"],
                "result_message": section["result_message"],
                "fetched_at": section["fetched_at"],
            })
    partial_store.insert_chemicals(partial_chems)
    partial_store.insert_sections(partial_secs)

    # Now replay. Expected: 2 UNCHANGED + 3 NEW; no duplicate key error.
    report = w.execute_incremental_write(
        inputs, store=partial_store, snapshot_id="snap-F7",
        id_factory=_deterministic_id_factory(),  # fresh sequence
    )
    assert report.chemicals_unchanged == 2
    assert report.chemicals_new == 3
    assert report.chemicals_changed == 0
    # The 2 pre-existing chemicals kept their original ids.
    for i, bundle in enumerate(plan[:2], start=1):
        row = partial_store.get_chemical_by_natural_key("KOSHA_MSDS",
                                                       bundle["chem_id"])
        assert row["id"] == f"11111111-1111-1111-1111-{i:012d}"


# ---------------------------------------------------------------------------
# F8 — Preview publication untouched (no PUBLISHED_FULL emission)
# ---------------------------------------------------------------------------


def test_F8_preview_publication_untouched():
    """The incremental writer produces snapshot_items for a plain
    RUNNING snapshot; it never emits PUBLISHED_FULL. The snapshot state
    stays RUNNING; the caller controls transition to COMPLETED /
    PUBLISHED_*."""
    plan = [_plan_bundle("P00001", source_content_hash="H1")]
    inputs = _plan_inputs(plan)
    store = w.MemoryMaterializeStore()

    # Open a snapshot as the SEO preview executor would.
    snap = w.open_snapshot(
        snapshot_id="snap-F8", manifest={"snapshot": {"metrics_json": {}}},
        discovered_count=1, expected_count=1,
    )
    store.insert_snapshot(snap)

    _ = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-F8",
        id_factory=_deterministic_id_factory(),
    )
    # Snapshot state — unchanged by the writer.
    after = store.get_snapshot("snap-F8")
    assert after["status"] == "RUNNING"
    assert after["publish_state"] == "NOT_PUBLISHED"


# ---------------------------------------------------------------------------
# Extra safety checks
# ---------------------------------------------------------------------------


def test_immutable_chemical_field_refused():
    """update_chemical must refuse to touch any immutable identity field."""
    row = _existing_chem_row("C00001", id="uu-1",
                             content_id="CHEM:uu-1",
                             source_content_hash="H")
    store = w.MemoryMaterializeStore(chemicals=[row])
    for bad in ("id", "content_id", "source_id", "source_key", "chem_id"):
        with pytest.raises(ValueError):
            store.update_chemical("KOSHA_MSDS", "C00001", {bad: "x"})
    # Mutable field succeeds.
    store.update_chemical("KOSHA_MSDS", "C00001",
                          {"chemical_name_ko": "새이름"})
    assert store.get_chemical_by_natural_key("KOSHA_MSDS",
                                             "C00001")["chemical_name_ko"] == "새이름"
    # Even after successful update, canonical identity is byte-identical.
    row_after = store.get_chemical_by_natural_key("KOSHA_MSDS", "C00001")
    assert row_after["id"] == "uu-1"
    assert row_after["content_id"] == "CHEM:uu-1"


def test_immutable_section_field_refused():
    row = _existing_section_row("uu-1", 5, "H")
    store = w.MemoryMaterializeStore(sections=[row])
    for bad in ("chemical_id", "section_no"):
        with pytest.raises(ValueError):
            store.update_section("uu-1", 5, {bad: 999})
    store.update_section("uu-1", 5, {"section_hash": "H_NEW"})
    assert store.get_section("uu-1", 5)["section_hash"] == "H_NEW"


# ---------------------------------------------------------------------------
# PATCH-A — bulk read (query-count scaling)
# ---------------------------------------------------------------------------


class _CountingStore(w.MemoryMaterializeStore):
    """Memory store that counts every DB read for scaling assertions.

    - `chem_point_reads` and `sec_point_reads` fire on the pre-PATCH-A
      per-row lookup path (get_chemical_by_natural_key / get_section).
    - `chem_bulk_reads` and `sec_bulk_reads` fire on the PATCH-A bulk
      path (get_chemicals_by_natural_keys / get_sections_by_chemical_ids).
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.chem_point_reads = 0
        self.sec_point_reads = 0
        self.chem_bulk_reads = 0
        self.sec_bulk_reads = 0

    def get_chemical_by_natural_key(self, source_id, source_key):
        self.chem_point_reads += 1
        return super().get_chemical_by_natural_key(source_id, source_key)

    def get_section(self, chemical_id, section_no):
        self.sec_point_reads += 1
        return super().get_section(chemical_id, section_no)

    def get_chemicals_by_natural_keys(self, pairs):
        self.chem_bulk_reads += 1
        return super().get_chemicals_by_natural_keys(pairs)

    def get_sections_by_chemical_ids(self, chemical_ids):
        self.sec_bulk_reads += 1
        return super().get_sections_by_chemical_ids(chemical_ids)


def test_A1_bulk_read_replaces_point_reads_in_execute():
    """execute_incremental_write MUST use the bulk-read helpers exactly
    once each and MUST NOT issue per-row point reads during classify+write.
    """
    # 5 existing chemicals + 3 new ones in the plan (mixed workload).
    ids = [(f"E{i:05d}", f"uu-E{i:05d}") for i in range(1, 6)]
    chems_existing = [
        _existing_chem_row(cid, id=uid, content_id=f"CHEM:{uid}",
                           source_content_hash=f"H-{cid}")
        for cid, uid in ids
    ]
    sections_existing = [
        _existing_section_row(uid, n, f"H-{cid}-{n}")
        for cid, uid in ids for n in range(1, 17)
    ]
    plan = [
        _plan_bundle(cid, source_content_hash=f"H-{cid}",
                     section_hashes={n: f"H-{cid}-{n}" for n in range(1, 17)})
        for cid, _ in ids
    ] + [_plan_bundle(f"N{i:05d}", source_content_hash=f"H-N{i}")
         for i in range(1, 4)]
    inputs = _plan_inputs(plan)
    store = _CountingStore(
        chemicals=chems_existing, sections=sections_existing,
    )

    report = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-A1",
        id_factory=_deterministic_id_factory(),
    )

    # PATCH-2: (1) preload feeds classify + write-phase decision, and
    # (2) NEW-post-insert verification is a single bulk fetch — total
    # 2 chemical bulk reads and 1 section bulk read for the whole run.
    assert store.chem_bulk_reads == 2   # preload + NEW verify
    assert store.sec_bulk_reads == 1    # preload only; write uses the map
    # PATCH-2 §2: NEW verification is bulk, not per-row — zero chemical
    # point reads even with 3 NEW chemicals.
    assert store.chem_point_reads == 0
    assert store.sec_point_reads == 0


def test_A2_bulk_read_query_count_scales_with_chunks_not_rows():
    """Prove that adding more rows does NOT proportionally increase the
    number of DB round-trips. Two runs — one with 5 existing chemicals
    and one with 400 — must both make exactly 1 bulk chemical read
    and 1 bulk section read for the classify+write pipeline."""
    def _run(existing_count):
        ids = [(f"P{i:05d}", f"uu-P{i:05d}") for i in range(1, existing_count + 1)]
        chems_existing = [
            _existing_chem_row(cid, id=uid, content_id=f"CHEM:{uid}",
                               source_content_hash=f"H-{cid}")
            for cid, uid in ids
        ]
        sections_existing = [
            _existing_section_row(uid, n, f"H-{cid}-{n}")
            for cid, uid in ids for n in range(1, 17)
        ]
        plan = [
            _plan_bundle(cid, source_content_hash=f"H-{cid}",
                         section_hashes={n: f"H-{cid}-{n}" for n in range(1, 17)})
            for cid, _ in ids
        ]
        inputs = _plan_inputs(plan)
        store = _CountingStore(
            chemicals=chems_existing, sections=sections_existing,
        )
        w.execute_incremental_write(
            inputs, store=store, snapshot_id="snap-A2",
            id_factory=_deterministic_id_factory(),
        )
        return store

    small = _run(5)
    large = _run(400)
    # Bulk call count is invariant across scale.
    assert small.chem_bulk_reads == large.chem_bulk_reads == 1
    assert small.sec_bulk_reads == large.sec_bulk_reads == 1
    # And absolutely no per-row section point reads scaled with row count.
    assert small.sec_point_reads == 0
    assert large.sec_point_reads == 0


# ---------------------------------------------------------------------------
# PATCH-2 — preflight preload sharing + NEW bulk verify
# ---------------------------------------------------------------------------


def test_B1_preflight_plus_writer_zero_point_reads_end_to_end():
    """The full preflight → writer chain (as invoked by the executor)
    must issue zero per-row point reads. Under PATCH-2, the executor
    calls preload_existing_state once and passes the ExistingState to
    both preflight and execute_incremental_write, so no matter how
    many existing rows there are, no chemical/section point read
    scales with row count."""
    ids = [(f"E{i:05d}", f"uu-E{i:05d}") for i in range(1, 51)]
    chems_existing = [
        _existing_chem_row(cid, id=uid, content_id=f"CHEM:{uid}",
                           source_content_hash=f"H-{cid}")
        for cid, uid in ids
    ]
    sections_existing = [
        _existing_section_row(uid, n, f"H-{cid}-{n}")
        for cid, uid in ids for n in range(1, 17)
    ]
    plan = [
        _plan_bundle(cid, source_content_hash=f"H-{cid}",
                     section_hashes={n: f"H-{cid}-{n}" for n in range(1, 17)})
        for cid, _ in ids
    ]
    # Give the plan the eligibility fields preflight needs.
    inputs = w.MaterializePlanInputs(
        manifest={"execute_eligible": True,
                  "responses_sha256": "resp-sha",
                  "plan_file_sha256": "plan-file-sha",
                  "plan_semantic_sha256": "plan-sem-sha",
                  "snapshot": {"metrics_json": {}}},
        report={"plan_sha256": "plan-sem-sha",
                "responses_sha256": "resp-sha",
                "execute_eligible": True},
        chemicals=tuple(plan),
    )
    store = _CountingStore(
        chemicals=chems_existing, sections=sections_existing,
    )

    # Executor-shaped call chain:
    state = w.preload_existing_state(inputs, store)
    _ = w.preflight(inputs, store=store, preloaded=state)
    _ = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-B1",
        id_factory=_deterministic_id_factory(),
        preloaded=state,
    )

    # PATCH-2: exactly ONE bulk chemical read + ONE bulk section read
    # for the whole preflight+writer chain. No NEW verify call because
    # there are 0 NEW chemicals in this plan.
    assert store.chem_bulk_reads == 1
    assert store.sec_bulk_reads == 1
    # Absolutely zero point reads across preflight + write.
    assert store.chem_point_reads == 0
    assert store.sec_point_reads == 0


def test_B2_new_verification_is_bulk_not_per_row():
    """400 NEW chemicals should be verified via a single bulk fetch,
    not 400 per-row point reads. Under PATCH-2 §2 the executor's
    chem_bulk_reads increments once for the preload and once for the
    post-insert verification — 2 total — regardless of NEW count."""
    plan = [_plan_bundle(f"N{i:05d}", source_content_hash=f"H-N{i}")
            for i in range(1, 401)]
    inputs = w.MaterializePlanInputs(
        manifest={"execute_eligible": True,
                  "responses_sha256": "resp-sha",
                  "plan_file_sha256": "plan-file-sha",
                  "plan_semantic_sha256": "plan-sem-sha",
                  "snapshot": {"metrics_json": {}}},
        report={"plan_sha256": "plan-sem-sha",
                "responses_sha256": "resp-sha",
                "execute_eligible": True},
        chemicals=tuple(plan),
    )
    store = _CountingStore()  # empty DB → 400 NEW

    state = w.preload_existing_state(inputs, store)
    report = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-B2",
        id_factory=_deterministic_id_factory(),
        preloaded=state,
    )

    assert report.chemicals_new == 400
    # 2 chemical bulk reads: preload + NEW verify. No 400-way point reads.
    assert store.chem_bulk_reads == 2
    assert store.chem_point_reads == 0
    # No existing chemicals → no existing chemical UUIDs → the section
    # preload optimization skips the bulk fetch. This is the correct
    # empty-DB behavior; both A1 (partial existing) and B1 (all existing)
    # cover the sec_bulk_reads == 1 case.
    assert store.sec_bulk_reads == 0
    assert store.sec_point_reads == 0


def test_B3_preflight_regression_still_passes():
    """The existing PATCH-1 regressions (CONFLICT fail-closed, identity
    preservation, expanded corpus, deterministic replay) must all still
    hold under PATCH-2. This test walks the same shape as F2 and F6
    plus F4 under the new preload path to prove nothing regressed."""
    # F2-style: replay against DB seeded with same rows → all UNCHANGED.
    ids = [("P00001", "uu-P00001"), ("P00002", "uu-P00002")]
    chems = [
        _existing_chem_row(cid, id=uid, content_id=f"CHEM:{uid}",
                           source_content_hash=f"H-{cid}")
        for cid, uid in ids
    ]
    secs = [_existing_section_row(uid, n, f"H-{cid}-{n}")
            for cid, uid in ids for n in range(1, 17)]
    plan = [_plan_bundle(cid, source_content_hash=f"H-{cid}",
                         section_hashes={n: f"H-{cid}-{n}" for n in range(1, 17)})
            for cid, _ in ids]
    inputs = _plan_inputs(plan)
    store = w.MemoryMaterializeStore(chemicals=chems, sections=secs)
    state = w.preload_existing_state(inputs, store)
    r = w.execute_incremental_write(
        inputs, store=store, snapshot_id="snap-B3-a",
        id_factory=_deterministic_id_factory(), preloaded=state,
    )
    assert r.chemicals_unchanged == 2
    assert r.chemicals_new == 0
    assert r.chemicals_changed == 0
    # Identity byte-stable.
    for cid, uid in ids:
        row = store.get_chemical_by_natural_key("KOSHA_MSDS", cid)
        assert row["id"] == uid
        assert row["content_id"] == f"CHEM:{uid}"

    # F6-style: identity conflict → IncrementalWriteBlocked.
    bad = _existing_chem_row("C00001", id="uu-C00001",
                             content_id="CHEM:uu-C00001",
                             source_content_hash="H")
    bad["chem_id"] = "999999"
    inputs_conflict = _plan_inputs([_plan_bundle("C00001", source_content_hash="H")])
    store2 = w.MemoryMaterializeStore(chemicals=[bad])
    state2 = w.preload_existing_state(inputs_conflict, store2)
    with pytest.raises(w.IncrementalWriteBlocked):
        w.execute_incremental_write(
            inputs_conflict, store=store2, snapshot_id="snap-B3-b",
            id_factory=_deterministic_id_factory(), preloaded=state2,
        )


def test_deterministic_replay_produces_identical_write_report():
    """Same plan + same store baseline + same id_factory → identical report."""
    plan = [_plan_bundle(f"P{i:05d}", source_content_hash=f"H{i}")
            for i in range(1, 4)]
    inputs = _plan_inputs(plan)

    store_a = w.MemoryMaterializeStore()
    report_a = w.execute_incremental_write(
        inputs, store=store_a, snapshot_id="snap-A",
        id_factory=_deterministic_id_factory(),
    )
    store_b = w.MemoryMaterializeStore()
    report_b = w.execute_incremental_write(
        inputs, store=store_b, snapshot_id="snap-A",
        id_factory=_deterministic_id_factory(),
    )
    assert report_a.to_dict() == report_b.to_dict()
