"""WP-1C-5A writer asset id=None/pending regression — no writer rewrite unless FAIL."""
from __future__ import annotations

from services.kosha_safety_materials.asset_parser import logical_checksum
from services.kosha_safety_materials.writer import MemoryStore, Writer


def _detail(mid="m001", h="h1"):
    return {
        "material_id": mid, "source_provider": "KOSHA", "source_med_seq": "1",
        "source_url": "https://portal.kosha.or.kr/x", "source_title": "t",
        "source_description": None, "source_published_at": None, "source_updated_at": None,
        "kogl_type": "4", "license_name": None, "license_source_url": None,
        "commercial_allowed": False, "modification_allowed": False,
        "render_policy": "LINK_ONLY", "content_type": "PDF", "thumbnail_url": None,
        "source_checked_at": "2026-09-11T00:00:00+00:00", "source_content_hash": h,
        "enrichment_status": "OK", "failure_reason": None,
    }


def _asset(mid="m001", name="a.pdf"):
    return {
        "material_id": mid, "asset_type": "PDF", "file_name": name,
        "source_file_url": None, "external_url": "https://portal.kosha.or.kr/x",
        "embed_url": None, "mime_type": "application/pdf", "file_size": 1,
        "local_storage_url": None, "checksum": logical_checksum(mid, "NO", 1, name),
        "display_order": 0, "storage_allowed": False, "is_original": True,
    }


class RecStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.update_ids = []

    def update_asset(self, asset_id, body):
        self.update_ids.append(asset_id)
        super().update_asset(asset_id, body)


def test_same_checksum_repeated_never_updates_none_or_pending():
    s = RecStore()
    s.catalog["m001"] = {"id": "m001"}
    w = Writer(dry_run=False, store=s)
    a = _asset()
    w.upsert(_detail(), [a, dict(a), dict(a)], allow_update=False)
    assert s.update_ids == []
    assert None not in s.update_ids
    assert "pending" not in s.update_ids
    assert s.count("kosha_safety_material_assets") == 1


def test_prev_id_none_and_pending_skipped():
    s = RecStore()
    s.catalog["m001"] = {"id": "m001"}
    s.details["m001"] = {**_detail(h="old"), "source_content_hash": "old"}
    s.assets.append({**_asset(), "id": None})
    w = Writer(dry_run=False, store=s)
    w.upsert(_detail(h="new"), [_asset()], allow_update=True)
    assert None not in s.update_ids
    s2 = RecStore()
    s2.catalog["m001"] = {"id": "m001"}
    s2.details["m001"] = {**_detail(h="old"), "source_content_hash": "old"}
    s2.assets.append({**_asset(), "id": "pending"})
    w2 = Writer(dry_run=False, store=s2)
    w2.upsert(_detail(h="new"), [_asset()], allow_update=True)
    assert "pending" not in s2.update_ids


def test_existing_real_id_updates_when_allow_update():
    s = RecStore()
    s.catalog["m001"] = {"id": "m001"}
    s.details["m001"] = {**_detail(h="old"), "source_content_hash": "old"}
    s.insert_asset(_asset())
    real_id = s.assets[0]["id"]
    assert real_id not in (None, "pending")
    w = Writer(dry_run=False, store=s)
    w.upsert(_detail(h="new"), [_asset()], allow_update=True)
    assert real_id in s.update_ids
