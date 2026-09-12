"""WP-2 read-only public material + signed GET. No live KOSHA/R2/DB writes."""
from __future__ import annotations

from services.kosha_safety_materials.display import MemoryDisplayStore, load_public_material
from services.kosha_safety_materials.storage.r2_store import ALLOWED_BUCKET, R2Error, assert_bucket
from services.kosha_safety_materials.storage.signed_url import R2GetSigner, SIGNED_TTL_SECONDS


class FakeSigner:
    def __init__(self):
        self.puts = 0
        self.deletes = 0
        self.presigns = 0
        self.keys = []

    def sign(self, bucket, key, *, mime=None, filename=None):
        assert_bucket(bucket)
        assert bucket == ALLOWED_BUCKET
        self.presigns += 1
        self.keys.append(key)
        return f"https://signed.test/{key}?ttl={SIGNED_TTL_SECONDS}"


class FakeS3:
    def __init__(self):
        self.puts = 0
        self.deletes = 0
        self.calls = []

    def put_object(self, **kw):
        self.puts += 1
        raise AssertionError("PUT forbidden")

    def delete_object(self, **kw):
        self.deletes += 1
        raise AssertionError("DELETE forbidden")

    def generate_presigned_url(self, op, Params=None, ExpiresIn=None):
        self.calls.append((op, dict(Params or {}), ExpiresIn))
        return f"https://signed.r2/{Params['Key']}?exp={ExpiresIn}"


def _seed_member(store, mid="m1", kogl="1", ct="PDF", title="자료"):
    store.snapshots.append({"id": "snap1", "status": "COMPLETED", "completed_at": "2026-09-12T00:00:00+09:00"})
    store.items.append({"snapshot_id": "snap1", "material_id": mid})
    store.catalog[mid] = {
        "id": mid, "title": title, "url": "https://www.kosha.or.kr/x",
        "category": "EDUCATION", "industry_category": "MANUFACTURING",
    }
    store.details[mid] = {
        "material_id": mid, "enrichment_status": "OK", "kogl_type": kogl,
        "content_type": ct, "source_url": "https://www.kosha.or.kr/x",
        "source_description": "본문", "source_published_at": "2024-01-02",
        "license_name": f"공공누리 제{kogl}유형",
    }
    return store


def _pdf_asset(mid="m1", aid=10, name="a.pdf"):
    return {
        "id": aid, "material_id": mid, "asset_type": "PDF",
        "file_name": name, "mime_type": "application/pdf", "file_size": 123,
        "display_order": 1,
    }


def _version(mid="m1", aid=10, bucket=ALLOWED_BUCKET, current=True, derivative=False, key=None):
    return {
        "id": 99, "asset_id": aid, "material_id": mid,
        "storage_bucket": bucket, "storage_key": key or f"kosha/{mid}.pdf",
        "content_checksum": "a" * 64, "source_content_type": "application/pdf",
        "source_file_size": 123, "source_file_name": "a.pdf",
        "is_current_version": current, "is_derivative": derivative,
    }


def test_type1_pdf_signed_url():
    st = _seed_member(MemoryDisplayStore(), kogl="1")
    st.assets.append(_pdf_asset())
    st.versions.append(_version())
    sg = FakeSigner()
    w0 = st.writes
    body = load_public_material("m1", store=st, signer=sg)
    assert body["id"] == "m1"
    assert body["source"]["license_type"] == "1"
    a = body["assets"][0]
    assert a["internally_available"] is True
    assert a["view_url"].startswith("https://signed.test/")
    assert sg.presigns == 1
    assert sg.puts == 0 and sg.deletes == 0
    assert st.writes == w0 == 0
    assert st.kosha_network == 0 and st.r2_put == 0 and st.r2_delete == 0


def test_type3_pdf_signed_url():
    st = _seed_member(MemoryDisplayStore(), kogl="3")
    st.assets.append(_pdf_asset())
    st.versions.append(_version())
    body = load_public_material("m1", store=st, signer=FakeSigner())
    assert body["source"]["license_type"] == "3"
    assert body["assets"][0]["internally_available"] is True
    assert body["assets"][0]["view_url"]


def test_type2_no_internal_asset():
    st = _seed_member(MemoryDisplayStore(), kogl="2")
    st.assets.append(_pdf_asset())
    st.versions.append(_version())
    sg = FakeSigner()
    body = load_public_material("m1", store=st, signer=sg)
    assert body["assets"][0]["internally_available"] is False
    assert body["assets"][0]["view_url"] is None
    assert sg.presigns == 0


def test_type4_no_internal_asset():
    st = _seed_member(MemoryDisplayStore(), kogl="4")
    st.assets.append(_pdf_asset())
    st.versions.append(_version())
    sg = FakeSigner()
    body = load_public_material("m1", store=st, signer=sg)
    assert body["assets"][0]["internally_available"] is False
    assert sg.presigns == 0


def test_unknown_no_internal_asset():
    st = _seed_member(MemoryDisplayStore(), kogl="UNKNOWN")
    st.assets.append(_pdf_asset())
    sg = FakeSigner()
    body = load_public_material("m1", store=st, signer=sg)
    assert body["source"]["license_type"] == "UNKNOWN"
    assert body["assets"][0]["internally_available"] is False
    assert sg.presigns == 0


def test_video_no_internal_binary():
    st = _seed_member(MemoryDisplayStore(), kogl="1", ct="VIDEO")
    st.assets.append({
        "id": 1, "material_id": "m1", "asset_type": "VIDEO",
        "file_name": "v.mp4", "mime_type": "video/mp4", "display_order": 1,
    })
    st.versions.append(_version(aid=1, key="kosha/v.mp4"))
    sg = FakeSigner()
    body = load_public_material("m1", store=st, signer=sg)
    assert body["assets"][0]["internally_available"] is False
    assert sg.presigns == 0


def test_non_current_version_not_returned():
    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset())
    st.versions.append(_version(current=False, key="kosha/old.pdf"))
    sg = FakeSigner()
    body = load_public_material("m1", store=st, signer=sg)
    assert body["assets"][0]["internally_available"] is False
    assert "old.pdf" not in (body["assets"][0]["view_url"] or "")
    assert sg.presigns == 0


def test_wrong_bucket_fail_no_url():
    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset())
    st.versions.append(_version(bucket="45cm-backup"))
    sg = FakeSigner()
    body = load_public_material("m1", store=st, signer=sg)
    assert body["assets"][0]["internally_available"] is False
    assert body["assets"][0]["view_url"] is None
    assert sg.presigns == 0


def test_derivative_fail_no_url():
    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset())
    st.versions.append(_version(derivative=True))
    sg = FakeSigner()
    body = load_public_material("m1", store=st, signer=sg)
    assert body["assets"][0]["internally_available"] is False
    assert sg.presigns == 0


def test_missing_material_404():
    st = MemoryDisplayStore()
    st.snapshots.append({"id": "snap1", "status": "COMPLETED", "completed_at": "z"})
    assert load_public_material("nope", store=st, signer=FakeSigner()) is None


def test_not_snapshot_member_404():
    st = _seed_member(MemoryDisplayStore())
    st.catalog["other"] = {"id": "other", "title": "x", "url": "u", "category": "OTHER"}
    assert load_public_material("other", store=st, signer=FakeSigner()) is None


def test_hold_without_version_is_fallback_not_error():
    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset())
    body = load_public_material("m1", store=st, signer=FakeSigner())
    assert body["assets"][0]["internally_available"] is False
    assert body["source"]["source_url"]


def test_multiple_assets_all_listed():
    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset(aid=1, name="one.pdf"))
    st.assets.append({
        "id": 2, "material_id": "m1", "asset_type": "IMAGE",
        "file_name": "two.jpg", "mime_type": "image/jpeg", "file_size": 10, "display_order": 2,
    })
    st.versions.append(_version(aid=1, key="kosha/one.pdf"))
    st.versions.append({
        **_version(aid=2, key="kosha/two.jpg"),
        "source_content_type": "image/jpeg", "source_file_name": "two.jpg",
    })
    body = load_public_material("m1", store=st, signer=FakeSigner())
    assert [a["file_name"] for a in body["assets"]] == ["one.pdf", "two.jpg"]
    assert all(a["internally_available"] for a in body["assets"])


def test_raw_key_query_not_accepted_by_loader():
    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset())
    st.versions.append(_version(key="kosha/real.pdf"))
    body = load_public_material("m1?key=evil&bucket=x", store=st, signer=FakeSigner())
    assert body is None


def test_r2_signer_get_object_only():
    s3 = FakeS3()
    signer = R2GetSigner(s3, ttl=600)
    url = signer.sign(ALLOWED_BUCKET, "kosha/a.pdf", mime="application/pdf", filename='a".pdf')
    assert "kosha/a.pdf" in url
    assert signer.puts == 0 and signer.deletes == 0 and s3.puts == 0 and s3.deletes == 0
    op, params, exp = s3.calls[0]
    assert op == "get_object"
    assert params["Bucket"] == ALLOWED_BUCKET
    assert params["Key"] == "kosha/a.pdf"
    assert exp == 600
    assert "inline" in params["ResponseContentDisposition"]
    assert "a.pdf" in params["ResponseContentDisposition"]


def test_r2_signer_rejects_wrong_bucket():
    s3 = FakeS3()
    signer = R2GetSigner(s3)
    try:
        signer.sign("other-bucket", "k")
        raise AssertionError("should fail")
    except R2Error as e:
        assert e.code == "UNEXPECTED_BUCKET"
    assert s3.calls == []


def test_router_404_and_ignores_key_bucket_query(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.kosha_public_materials as mod

    st = MemoryDisplayStore()
    monkeypatch.setattr(mod, "get_store", lambda: st)
    monkeypatch.setattr(mod, "get_signer", lambda: FakeSigner())
    app = FastAPI()
    app.include_router(mod.router)
    c = TestClient(app)
    r = c.get("/public/kosha/materials/nope")
    assert r.status_code == 404
    r2 = c.get("/public/kosha/materials/nope", params={"key": "evil", "bucket": "other"})
    assert r2.status_code == 404


def test_router_type1_ok(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.kosha_public_materials as mod

    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset())
    st.versions.append(_version())
    monkeypatch.setattr(mod, "get_store", lambda: st)
    monkeypatch.setattr(mod, "get_signer", lambda: FakeSigner())
    app = FastAPI()
    app.include_router(mod.router)
    r = TestClient(app).get("/public/kosha/materials/m1")
    assert r.status_code == 200
    assert r.json()["assets"][0]["internally_available"] is True
    assert "key" not in (r.json()["assets"][0])
