"""WO-CHEM-FULL-READINESS-002 — cutover / rollback rehearsal (fixture only).

Exercises the end-to-end SEO_PREVIEW ↔ FULL cutover machinery that is
already in the repo (CHEM-06 read scope wiring, CHEM-07 dormant
router's KOSHA_MSDS_PUBLIC_MODE env var handling, CHEM-10 publish
preflight). This WO does not introduce new routing or new schema —
it only proves the seams hold under C1..C8.

No live DB. No production publish. No env change in production —
tests mutate `os.environ[KOSHA_MSDS_PUBLIC_MODE]` locally via
monkeypatch and always reset.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.kosha_msds.contract import (
    PUBLIC_MODE_ENV_VAR,
    PUBLIC_MODE_FULL,
    PUBLIC_MODE_OFF,
    PUBLIC_MODE_SEO_PREVIEW,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SNAPSHOT_COMPLETED,
    ENUMERATION_FULL_OFFICIAL,
)
from services.kosha_msds import cutover, publish as pub, read
from routers import kosha_public_msds as router_mod


# ---------------------------------------------------------------------------
# Fixture helpers — two publication slices in a single store
# ---------------------------------------------------------------------------

FULL_CHEM = pub.FULL_OFFICIAL_CHEMICAL_COUNT       # 20,568
FULL_SEC = pub.FULL_OFFICIAL_SECTION_COUNT         # 329,088
PREVIEW_CHEM = 1_997


def _slice_row(chem_id: str, *, id: str, content_id: str,
               ko: str | None = None, cas: str | None = None) -> dict:
    return {
        "id": id, "content_id": content_id,
        "source_id": "KOSHA_MSDS", "source_key": chem_id, "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": ko, "chemical_name_en": None,
        "cas_no": cas, "ke_no": None, "en_no": None, "un_no": None,
        "source_content_hash": "sha-" + chem_id,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "snapshot_id": "snap-shared",
    }


def _read_store_two_slices() -> read.MemoryMsdsReadStore:
    """Read store with a PREVIEW slice (3 rows) and a FULL slice
    (2 preview rows + 3 new rows = 5 rows). FULL is a superset of
    PREVIEW — this is the rehearsal shape."""
    preview_rows = [
        _slice_row("P00001", id="uu-P1", content_id="CHEM:uu-P1", ko="벤젠"),
        _slice_row("P00002", id="uu-P2", content_id="CHEM:uu-P2", ko="메탄올"),
        _slice_row("P00003", id="uu-P3", content_id="CHEM:uu-P3", ko="에탄올"),
    ]
    # FULL slice: 2 of the 3 preview rows (P00001, P00002 — represents
    # the FULL snapshot happening to include them) plus 3 additional
    # chemicals only available under FULL.
    full_rows = [
        _slice_row("P00001", id="uu-P1", content_id="CHEM:uu-P1", ko="벤젠"),
        _slice_row("P00002", id="uu-P2", content_id="CHEM:uu-P2", ko="메탄올"),
        _slice_row("F00001", id="uu-F1", content_id="CHEM:uu-F1"),
        _slice_row("F00002", id="uu-F2", content_id="CHEM:uu-F2"),
        _slice_row("F00003", id="uu-F3", content_id="CHEM:uu-F3"),
    ]
    return read.MemoryMsdsReadStore(
        current_rows=full_rows,
        preview_rows=preview_rows,
    )


def _publish_snapshot_row(
    id: str,
    *,
    status: str = SNAPSHOT_COMPLETED,
    enumeration_mode: str = ENUMERATION_FULL_OFFICIAL,
    publish_state: str = PUBLISH_NOT_PUBLISHED,
    expected_count: int = FULL_CHEM,
    discovered_count: int = FULL_CHEM,
    completed_at: str = "2026-09-20T10:00:00Z",
    started_at: str = "2026-09-20T09:00:00Z",
    metrics_json: dict | None = None,
) -> dict:
    return {
        "id": id,
        "source_id": "KOSHA_MSDS",
        "run_type": "FULL_SYNC",
        "status": status,
        "enumeration_mode": enumeration_mode,
        "publish_state": publish_state,
        "source_contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
        "expected_count": expected_count,
        "discovered_count": discovered_count,
        "started_at": started_at,
        "completed_at": completed_at,
        "metrics_json": dict(metrics_json or {
            "adapter_version": "CHEM05_V1",
            "materialize_plan_sha256": "plan-sem-sha",
            "responses_sha256": "resp-sha",
        }),
    }


def _full_membership(snap_id: str, count: int = FULL_CHEM,
                     detail_status: str = "COMPLETE") -> list[dict]:
    return [
        {"snapshot_id": snap_id, "chemical_id": f"uu-full-{i:06d}",
         "detail_status": detail_status, "in_snapshot": True}
        for i in range(count)
    ]


def _full_sections(count: int = FULL_CHEM) -> list[dict]:
    rows = []
    for i in range(count):
        cid = f"uu-full-{i:06d}"
        for n in range(1, 17):
            rows.append({"chemical_id": cid, "section_no": n,
                         "section_hash": f"sec-{cid}-{n}",
                         "result_code": "00"})
    return rows


def _valid_full_publish_store(snap_id: str = "snap-FULL") -> pub.MemoryPublishStore:
    """Publish store with:
      - one OLD PUBLISHED_SEO_PREVIEW snapshot (preview slice)
      - one COMPLETED / NOT_PUBLISHED FULL snapshot (candidate for cutover)
    Both coexist. This is the state the rehearsal starts from."""
    old_preview = _publish_snapshot_row(
        "snap-preview-old",
        publish_state=PUBLISH_PUBLISHED_SEO_PREVIEW,
        expected_count=PREVIEW_CHEM,
        discovered_count=PREVIEW_CHEM,
        completed_at="2026-09-18T05:00:00Z",
        started_at="2026-09-18T04:00:00Z",
    )
    new_full = _publish_snapshot_row(snap_id)
    return pub.MemoryPublishStore(
        snapshots=[old_preview, new_full],
        snapshot_items=_full_membership(snap_id),
        sections=_full_sections(),
    )


@pytest.fixture
def client_factory(monkeypatch):
    """Return a `set_mode(mode)` callable that builds an isolated
    FastAPI app with the CHEM-07 router mounted, wired to a memory
    read store that already contains both slices. Setting the mode
    via monkeypatch keeps the real environment clean.
    """
    read_store = _read_store_two_slices()
    monkeypatch.setattr(router_mod, "get_store", lambda: read_store)

    def _set(mode: str | None):
        if mode is None:
            monkeypatch.delenv(PUBLIC_MODE_ENV_VAR, raising=False)
        else:
            monkeypatch.setenv(PUBLIC_MODE_ENV_VAR, mode)
        app = FastAPI()
        app.include_router(router_mod.router)
        return TestClient(app), read_store
    return _set


# ---------------------------------------------------------------------------
# C1 — Preview remains active before FULL
# ---------------------------------------------------------------------------


def test_C1_preview_active_before_full_publish(client_factory):
    client, store = client_factory(PUBLIC_MODE_SEO_PREVIEW)
    r = client.get("/public/kosha/msds")
    assert r.status_code == 200
    body = r.json()
    # Preview slice is served — 3 rows.
    assert body["total"] == 3
    chem_ids = {i["chem_id"] for i in body["items"]}
    assert chem_ids == {"P00001", "P00002", "P00003"}
    # FULL-only chemicals never leak into preview.
    for cid in ("F00001", "F00002", "F00003"):
        assert cid not in chem_ids


# ---------------------------------------------------------------------------
# C2 — FULL publish eligibility (canonical readiness check)
# ---------------------------------------------------------------------------


def test_C2_full_publish_eligibility_pass():
    store = _valid_full_publish_store()
    result = cutover.is_full_ready(
        "snap-FULL", store=store,
        expected_materialize_binding={
            "adapter_version": "CHEM05_V1",
            "materialize_plan_sha256": "plan-sem-sha",
            "responses_sha256": "resp-sha",
        },
    )
    assert result.ready is True
    assert result.block_reasons == ()
    assert result.expected_count == FULL_CHEM
    assert result.discovered_count == FULL_CHEM
    assert result.snapshot_item_count == FULL_CHEM
    assert result.section_count == FULL_SEC
    assert result.incomplete_memberships == 0
    assert result.duplicate_memberships == 0
    assert result.duplicate_sections == 0
    assert result.materialize_binding_mismatch is False


# ---------------------------------------------------------------------------
# C3 — FULL publish preserves preview snapshot
# ---------------------------------------------------------------------------


def test_C3_full_publish_preserves_preview_snapshot():
    store = _valid_full_publish_store()
    # Owner-approved fixture promotion (three-gate opened via kwargs
    # exactly like the future execution WO would).
    result = pub.promote_to_published_full(
        "snap-FULL",
        store=store,
        owner_approved=True,
        wo_scope_allows_publish=True,
    )
    assert result.publish_state == PUBLISH_PUBLISHED_FULL

    # Old preview snapshot must remain intact.
    preview = store.get_snapshot("snap-preview-old")
    assert preview is not None
    assert preview["publish_state"] == PUBLISH_PUBLISHED_SEO_PREVIEW

    # And the FULL snapshot's row is present + PUBLISHED_FULL.
    full = store.get_snapshot("snap-FULL")
    assert full["publish_state"] == PUBLISH_PUBLISHED_FULL


# ---------------------------------------------------------------------------
# C4 — mode=full serves FULL slice
# ---------------------------------------------------------------------------


def test_C4_mode_full_serves_full_scope(client_factory):
    client, store = client_factory(PUBLIC_MODE_FULL)
    r = client.get("/public/kosha/msds")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    chem_ids = {i["chem_id"] for i in body["items"]}
    assert {"F00001", "F00002", "F00003"} <= chem_ids


# ---------------------------------------------------------------------------
# C5 — rollback: mode=seo_preview after mode=full
# ---------------------------------------------------------------------------


def test_C5_rollback_to_preview_does_not_touch_db(monkeypatch):
    """Simulate FULL activation, then flip mode back to preview.
    Assert that ONLY the router's read pointer changes; the memory
    read store's `_current` and `_preview` lists are byte-identical
    before/after. The FULL DB state stays intact — a critical
    property of the L1 rollback contract."""
    read_store = _read_store_two_slices()
    monkeypatch.setattr(router_mod, "get_store", lambda: read_store)

    # Take a defensive snapshot of both slices.
    current_before = [dict(r) for r in read_store._current]
    preview_before = [dict(r) for r in read_store._preview]

    # Phase 1: mode=full → FULL scope serves.
    monkeypatch.setenv(PUBLIC_MODE_ENV_VAR, PUBLIC_MODE_FULL)
    app_full = FastAPI(); app_full.include_router(router_mod.router)
    with TestClient(app_full) as cli:
        r_full = cli.get("/public/kosha/msds").json()
    assert r_full["total"] == 5

    # Phase 2: rollback → mode=seo_preview → PREVIEW scope serves.
    monkeypatch.setenv(PUBLIC_MODE_ENV_VAR, PUBLIC_MODE_SEO_PREVIEW)
    app_prev = FastAPI(); app_prev.include_router(router_mod.router)
    with TestClient(app_prev) as cli:
        r_prev = cli.get("/public/kosha/msds").json()
    assert r_prev["total"] == 3

    # ── L1 rollback invariant: NO DB mutation. ──
    assert read_store._current == current_before
    assert read_store._preview == preview_before

    # And cutover.rollback_contract() documents the invariant.
    contract = cutover.rollback_contract()
    assert contract["l1"]["mutates_db"] is False
    assert contract["l1"]["from_mode"] == PUBLIC_MODE_FULL
    assert contract["l1"]["to_mode"] == PUBLIC_MODE_SEO_PREVIEW
    assert contract["l2"]["authorized_here"] is False


# ---------------------------------------------------------------------------
# C6 — invalid full corpus blocks (each invariant tested separately)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutation,expected_reason", [
    ("membership_short",  pub.BLOCK_SNAPSHOT_ITEM_COUNT_MISMATCH),
    ("section_short",     pub.BLOCK_SECTION_COUNT_MISMATCH),
    ("incomplete_member", pub.BLOCK_INCOMPLETE_MEMBERSHIP),
    ("duplicate_member",  pub.BLOCK_DUPLICATE_MEMBERSHIP),
    ("duplicate_section", pub.BLOCK_DUPLICATE_SECTION),
    ("binding_mismatch",  pub.BLOCK_MATERIALIZE_BINDING_MISMATCH),
])
def test_C6_invalid_full_corpus_blocks_publish(mutation, expected_reason):
    snap_id = "snap-C6"
    snap = _publish_snapshot_row(snap_id)
    items = _full_membership(snap_id)
    sections = _full_sections()

    if mutation == "membership_short":
        items = items[:-1]  # 20,567 rows
    elif mutation == "section_short":
        sections = sections[:-1]  # 329,087 rows
    elif mutation == "incomplete_member":
        items[0]["detail_status"] = "INCOMPLETE"
    elif mutation == "duplicate_member":
        items.append(dict(items[0]))
    elif mutation == "duplicate_section":
        sections.append(dict(sections[0]))
    elif mutation == "binding_mismatch":
        snap["metrics_json"]["materialize_plan_sha256"] = "different-sha"

    store = pub.MemoryPublishStore(
        snapshots=[snap], snapshot_items=items, sections=sections,
    )
    kwargs = {}
    if mutation == "binding_mismatch":
        kwargs["expected_materialize_binding"] = {
            "adapter_version": "CHEM05_V1",
            "materialize_plan_sha256": "plan-sem-sha",  # what the manifest promised
            "responses_sha256": "resp-sha",
        }

    result = cutover.is_full_ready(snap_id, store=store, **kwargs)
    assert result.ready is False
    assert expected_reason in result.block_reasons

    # And the three-gate publish fence refuses too — no snapshot mutation.
    from services.kosha_msds.publish import (
        assert_can_execute_publish, PublicationForbidden, preflight_publish,
    )
    report = preflight_publish(
        snap_id, store=store,
        publication_scope=PUBLICATION_SCOPE_FULL,
        expected_materialize_binding=kwargs.get("expected_materialize_binding"),
    )
    with pytest.raises(PublicationForbidden):
        assert_can_execute_publish(
            report=report, owner_approved=True,
            wo_scope_allows_publish=True,
        )
    # DB untouched.
    assert store.get_snapshot(snap_id)["publish_state"] == PUBLISH_NOT_PUBLISHED


# ---------------------------------------------------------------------------
# C7 — mode=full without a PUBLISHED_FULL snapshot returns an empty envelope
# ---------------------------------------------------------------------------


def test_C7_mode_full_without_published_full_returns_empty(client_factory):
    """Simulate the transitional window between mode=full being flipped
    on and a PUBLISHED_FULL snapshot actually existing: the store's FULL
    slice is empty. The router must return an empty envelope, not 500,
    and no preview data leaks in."""
    # Override with an empty FULL slice; preview slice still populated.
    empty_full_store = read.MemoryMsdsReadStore(
        current_rows=[],  # no FULL rows
        preview_rows=[
            _slice_row("P00001", id="uu-P1", content_id="CHEM:uu-P1"),
        ],
    )
    # Re-use the fixture pattern by creating a fresh client with an
    # override.
    from unittest.mock import patch
    with patch.object(router_mod, "get_store", lambda: empty_full_store):
        import os
        os.environ[PUBLIC_MODE_ENV_VAR] = PUBLIC_MODE_FULL
        try:
            app = FastAPI(); app.include_router(router_mod.router)
            with TestClient(app) as cli:
                body = cli.get("/public/kosha/msds").json()
        finally:
            os.environ.pop(PUBLIC_MODE_ENV_VAR, None)

    assert body["items"] == []
    assert body["total"] == 0
    # No preview leakage.
    assert not any(i.get("chem_id", "").startswith("P") for i in body["items"])


# ---------------------------------------------------------------------------
# C8 — unknown mode → off → 503
# ---------------------------------------------------------------------------


def test_C8_unknown_mode_is_dormant_503(client_factory):
    """Any KOSHA_MSDS_PUBLIC_MODE value not in ALLOWED_PUBLIC_MODES
    routes as OFF (fail-safe) and returns 503."""
    client, _ = client_factory("garbage_mode_that_does_not_exist")
    r = client.get("/public/kosha/msds")
    assert r.status_code == 503
    detail = r.json()["detail"]
    if isinstance(detail, dict):
        assert detail["code"] == "MSDS_PUBLIC_DORMANT"
    else:
        assert "DORMANT" in detail


def test_C8b_explicit_off_mode_is_503(client_factory):
    """Explicit 'off' also returns 503."""
    client, _ = client_factory(PUBLIC_MODE_OFF)
    r = client.get("/public/kosha/msds")
    assert r.status_code == 503


def test_C8c_missing_env_defaults_to_off(client_factory):
    """No env var set → DEFAULT_PUBLIC_MODE = off → 503."""
    client, _ = client_factory(None)
    r = client.get("/public/kosha/msds")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Cross-domain isolation
# ---------------------------------------------------------------------------


def test_no_new_engine_or_terminology_change():
    """The cutover composer must not fork the search / terminology /
    materialize / publish engines. It composes existing helpers only."""
    src = Path(cutover.__file__).read_text(encoding="utf-8")
    # No search or terminology imports.
    assert "search_adapter" not in src
    assert "safe_help_kiwi" not in src
    assert "search_dict" not in src
    # No hydration coupling.
    assert "chem04" not in src
    assert "official_hydrate" not in src
    # No production_store direct imports — must go through the
    # publish preflight, which is the canonical reader.
    assert "production_store" not in src
    # No kosha_safety_materials (different domain).
    assert "kosha_safety_materials" not in src


def test_l1_rollback_contract_documented():
    """rollback_contract() returns the frozen L1/L2 policy as
    machine-readable data. Receipts and future execution WOs consult
    this shape rather than parsing prose."""
    c = cutover.rollback_contract()
    assert set(c.keys()) == {"l1", "l2", "off_failsafe"}
    assert c["l1"]["mutates_db"] is False
    assert c["l2"]["authorized_here"] is False
    assert c["off_failsafe"]["response"].startswith("HTTP 503")
