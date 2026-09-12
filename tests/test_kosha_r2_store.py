"""WP-1C-5A R2 S3 client — mocked, no live PUT/DELETE."""
from __future__ import annotations

import hashlib
import inspect
import os

from services.kosha_safety_materials.storage import r2_store as rs
from services.kosha_safety_materials.storage.r2_store import (
    ALLOWED_BUCKET,
    FORBIDDEN_BUCKETS,
    R2Error,
    R2Store,
    assert_bucket,
    classify_client_error,
    credentials_from_env,
)


class FakeErr(Exception):
    def __init__(self, code, http=None):
        self.response = {"Error": {"Code": str(code)}, "ResponseMetadata": {"HTTPStatusCode": http}}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.puts = 0
        self.gets = 0
        self.heads = 0
        self.auth = False
        self.transient = False
        self.read_chunk = 8
        self.incomplete_reads = 0
        self.reset_reads = 0

    def head_object(self, Bucket, Key):
        self.heads += 1
        if self.auth:
            raise FakeErr("AccessDenied", 403)
        if self.transient:
            raise FakeErr("InternalError", 500)
        if Key not in self.objects:
            raise FakeErr("404", 404)
        o = self.objects[Key]
        return {
            "ContentLength": len(o["Body"]),
            "ContentType": o.get("ContentType"),
            "Metadata": o.get("Metadata") or {},
            "ETag": o.get("ETag", '"not-a-sha"'),
        }

    def get_object(self, Bucket, Key):
        self.gets += 1
        if Key not in self.objects:
            raise FakeErr("404", 404)
        data = self.objects[Key]["Body"]
        body = self._body_for(data)
        declared = getattr(body, "declared_length", len(data))
        return {"Body": body, "ContentLength": declared}

    def _body_for(self, data):
        if self.incomplete_reads:
            self.incomplete_reads -= 1
            return IncompleteBody(data, keep=max(1, len(data) // 3))
        if self.reset_reads:
            self.reset_reads -= 1
            return ResetBody(data, after=1)
        return ChunkedBody(data, chunk=self.read_chunk)

    def put_object(self, Bucket, Key, Body, ContentType=None, Metadata=None):
        self.puts += 1
        self.objects[Key] = {
            "Body": Body if isinstance(Body, (bytes, bytearray)) else bytes(Body),
            "ContentType": ContentType,
            "Metadata": dict(Metadata or {}),
            "ETag": '"etag-not-sha256"',
        }


class ChunkedBody:
    """botocore-like: read(n) returns at most n, and may return even fewer."""

    def __init__(self, data, chunk=8):
        self._d = data
        self._i = 0
        self._chunk = chunk
        self.reads = 0

    def read(self, n=-1):
        self.reads += 1
        if self._i >= len(self._d):
            return b""
        take = self._chunk
        if n is not None and n >= 0:
            take = min(take, n)
        out = self._d[self._i:self._i + take]
        self._i += len(out)
        return out


class IncompleteBody(ChunkedBody):
    def __init__(self, data, keep=1):
        super().__init__(data[:keep], chunk=8)
        self.declared_length = len(data)


class ResetBody(ChunkedBody):
    def __init__(self, data, after=1):
        super().__init__(data, chunk=8)
        self._after = after

    def read(self, n=-1):
        if self.reads >= self._after:
            raise ConnectionResetError("reset during body")
        return super().read(n)


def test_bucket_guards():
    assert ALLOWED_BUCKET == "tai-kosha-originals"
    assert "45cm-backup" in FORBIDDEN_BUCKETS
    try:
        assert_bucket("45cm-backup")
        assert False
    except R2Error as e:
        assert e.code == "FORBIDDEN_BUCKET"
    try:
        assert_bucket("other-bucket")
        assert False
    except R2Error as e:
        assert e.code == "UNEXPECTED_BUCKET"
    assert_bucket("tai-kosha-originals")


def test_no_wrangler_and_private_endpoint():
    src = inspect.getsource(rs)
    assert "import subprocess" not in src
    assert "npx" not in src
    assert "_wrangler" not in src
    assert "r2.dev" in src  # forbidden check
    creds = credentials_from_env({
        "CLOUDFLARE_R2_ACCOUNT_ID": "acct",
        "CLOUDFLARE_R2_ACCESS_KEY_ID": "id",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "secret",
        "CLOUDFLARE_R2_BUCKET": "tai-kosha-originals",
    })
    assert creds["endpoint"] == "https://acct.r2.cloudflarestorage.com"
    assert "r2.dev" not in creds["endpoint"]
    try:
        credentials_from_env({"CLOUDFLARE_R2_BUCKET": "tai-kosha-originals"})
        assert False
    except R2Error as e:
        assert e.code == "R2_INTEGRATION_BLOCKED"


def test_head_exists_missing_auth_transient():
    s3 = FakeS3()
    st = R2Store(s3)
    assert st.head("k")["exists"] is False
    s3.objects["k"] = {"Body": b"%PDF-x", "ContentType": "application/pdf", "Metadata": {}, "ETag": '"abc"'}
    h = st.head("k")
    assert h["exists"] is True
    assert h["etag"] == '"abc"'
    s3.auth = True
    try:
        st.head("k")
        assert False
    except R2Error as e:
        assert e.code == "R2_HEAD_AUTH"
    s3.auth = False
    s3.transient = True
    try:
        st.head("k")
        assert False
    except R2Error as e:
        assert e.code == "R2_HEAD_TRANSIENT"


def test_etag_not_sha_legacy_and_conflict_and_put_absent_only():
    sha = hashlib.sha256(b"%PDF-ok").hexdigest()
    s3 = FakeS3()
    st = R2Store(s3)
    s3.objects["legacy"] = {
        "Body": b"%PDF-ok", "ContentType": "application/pdf",
        "Metadata": {}, "ETag": f'"{sha}"',
    }
    assert st.verify_existing("legacy", sha) == "LEGACY_OBJECT"
    wrong = hashlib.sha256(b"nope").hexdigest()
    try:
        st.verify_existing("legacy", wrong)
        assert False
    except R2Error as e:
        assert e.code == "R2_OBJECT_CONFLICT"

    s3.objects["meta"] = {
        "Body": b"%PDF-ok", "ContentType": "application/pdf",
        "Metadata": {"tai-content-sha256": sha}, "ETag": '"not-sha"',
    }
    assert st.verify_existing("meta", sha) == "OBJECT_EXISTS_VERIFIED"
    try:
        st.verify_existing("meta", wrong)
        assert False
    except R2Error as e:
        assert e.code == "R2_OBJECT_CONFLICT"

    puts_before = s3.puts
    status = st.put_new(
        "newkey", b"%PDF-ok", content_type="application/pdf",
        source_asset_key="sak", material_id="m1", content_sha256=sha,
    )
    assert status == "PUT"
    assert s3.puts == puts_before + 1
    status2 = st.put_new(
        "newkey", b"%PDF-ok", content_type="application/pdf",
        source_asset_key="sak", material_id="m1", content_sha256=sha,
    )
    assert status2 == "OBJECT_EXISTS_VERIFIED"
    assert s3.puts == puts_before + 1

    try:
        st.delete("newkey")
        assert False
    except R2Error as e:
        assert e.code == "R2_DELETE_FORBIDDEN"


def test_readback_mismatch_stops_before_promotion_hook():
    s3 = FakeS3()
    st = R2Store(s3)
    sha = hashlib.sha256(b"AAA").hexdigest()
    st.put_new("k", b"AAA", content_type="application/octet-stream",
               source_asset_key="s", material_id="m", content_sha256=sha)
    s3.objects["k"]["Body"] = b"TAMPER"
    try:
        st.readback_verify("k", sha)
        assert False
    except R2Error as e:
        assert e.code == "READBACK_MISMATCH"


def test_put_auth_maps_to_access_blocked():
    s3 = FakeS3()
    st = R2Store(s3)

    def deny(**k):
        raise FakeErr("AccessDenied", 403)

    s3.put_object = deny  # type: ignore
    sha = hashlib.sha256(b"x").hexdigest()
    try:
        st.put_new("k", b"x", content_type="application/octet-stream",
                   source_asset_key="s", material_id="m", content_sha256=sha)
        assert False
    except R2Error as e:
        assert e.code == "R2_ACCESS_BLOCKED"
    assert s3.puts == 0


def test_classify_404_403_5xx():
    assert classify_client_error(FakeErr("404", 404)) == "MISSING"
    assert classify_client_error(FakeErr("AccessDenied", 403)) == "AUTH"
    assert classify_client_error(FakeErr("InternalError", 500)) == "TRANSIENT"


def test_streaming_partial_chunks_and_large_object_sha():
    from services.kosha_safety_materials.storage.r2_store import GET_ATTEMPTS

    data = b"%PDF-" + bytes(range(256)) * 20
    sha = hashlib.sha256(data).hexdigest()
    s3 = FakeS3()
    s3.read_chunk = 3
    s3.objects["k"] = {"Body": data, "ContentType": "application/pdf", "Metadata": {}, "ETag": '"x"'}
    st = R2Store(s3)
    got = st.readback_verify("k", sha, sleeper=lambda s: None)
    assert got["byte_count"] == len(data)
    assert got["sha256"] == sha
    assert s3.gets == 1

    big = b"%PDF-" + (b"\x00" * (6_500_000))
    big_sha = hashlib.sha256(big).hexdigest()
    s3b = FakeS3()
    s3b.read_chunk = 64 * 1024
    s3b.objects["big"] = {"Body": big, "ContentType": "application/pdf", "Metadata": {}, "ETag": '"x"'}
    st2 = R2Store(s3b)
    got2 = st2.readback_verify("big", big_sha, sleeper=lambda s: None)
    assert got2["byte_count"] == len(big)
    assert GET_ATTEMPTS == 3


def test_short_read_and_reset_retry_then_exhaust():
    data = b"%PDF-complete-bytes"
    sha = hashlib.sha256(data).hexdigest()
    s3 = FakeS3()
    s3.objects["k"] = {"Body": data, "ContentType": "application/pdf", "Metadata": {}, "ETag": '"x"'}
    s3.incomplete_reads = 1
    st = R2Store(s3)
    st.readback_verify("k", sha, sleeper=lambda s: None)
    assert s3.gets == 2

    s3b = FakeS3()
    s3b.objects["k"] = {"Body": data, "ContentType": "application/pdf", "Metadata": {}, "ETag": '"x"'}
    s3b.reset_reads = 1
    R2Store(s3b).readback_verify("k", sha, sleeper=lambda s: None)
    assert s3b.gets == 2

    s3c = FakeS3()
    s3c.objects["k"] = {"Body": data, "ContentType": "application/pdf", "Metadata": {}, "ETag": '"x"'}
    s3c.reset_reads = 99
    try:
        R2Store(s3c).readback_verify("k", sha, sleeper=lambda s: None)
        assert False
    except R2Error as e:
        assert e.code == "R2_TRANSIENT"
    assert s3c.gets == 3


def test_complete_sha_mismatch_does_not_retry():
    s3 = FakeS3()
    st = R2Store(s3)
    sha = hashlib.sha256(b"AAA").hexdigest()
    st.put_new("k", b"AAA", content_type="application/octet-stream",
               source_asset_key="s", material_id="m", content_sha256=sha)
    s3.objects["k"]["Body"] = b"TAMPERED-FULL"
    gets_before = s3.gets
    try:
        st.readback_verify("k", sha, sleeper=lambda s: None)
        assert False
    except R2Error as e:
        assert e.code == "READBACK_MISMATCH"
    assert s3.gets == gets_before + 1


def test_verify_existing_does_full_get_even_when_metadata_sha_matches():
    sha = hashlib.sha256(b"%PDF-ok").hexdigest()
    s3 = FakeS3()
    s3.objects["meta"] = {
        "Body": b"%PDF-ok", "ContentType": "application/pdf",
        "Metadata": {"tai-content-sha256": sha}, "ETag": '"not-sha"',
    }
    st = R2Store(s3)
    assert st.verify_existing("meta", sha, sleeper=lambda s: None) == "OBJECT_EXISTS_VERIFIED"
    assert s3.gets == 1
    s3.objects["meta"]["Body"] = b"%PDF-NO"
    try:
        st.verify_existing("meta", sha, sleeper=lambda s: None)
        assert False
    except R2Error as e:
        assert e.code == "R2_OBJECT_CONFLICT"
