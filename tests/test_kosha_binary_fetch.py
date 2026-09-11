"""WP-1C-5A binary fetch security — mocked, no live KOSHA."""
from __future__ import annotations

import email.message
import inspect
import io
import os
import tempfile
import urllib.error
import urllib.request

from services.kosha_safety_materials import detail_client as dc
from services.kosha_safety_materials.storage.binary_fetch import (
    BinaryFetchError,
    GuardedRedirectHandler,
    assert_binary_allowed,
    assert_https_allowed,
    assert_pdf_payload,
    fetch_attachment_binary,
    fetch_https_binary,
    pick_first_pdf,
)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


class MockHandler(urllib.request.BaseHandler):
    handler_order = 1

    def __init__(self, table: dict):
        self.table = table
        self.opened = []
        self.fps = []

    def http_open(self, req):
        return self._open(req)

    def https_open(self, req):
        return self._open(req)

    def _open(self, req):
        url = req.full_url
        self.opened.append(url)
        if url not in self.table:
            raise urllib.error.URLError(f"unexpected {url}")
        status, headers, body = self.table[url]
        hdr = email.message.Message()
        for k, v in headers.items():
            hdr[k] = v

        class _Resp(io.BytesIO):
            def __init__(self, data, headers, url, status):
                super().__init__(data)
                self.headers = headers
                self._url = url
                self.status = status
                self.code = status
                self.msg = "OK" if status < 300 else "redirect"

            def geturl(self):
                return self._url

            def info(self):
                return self.headers

        resp = _Resp(body, hdr, url, status)
        self.fps.append(resp)
        return resp


def opener_for(table: dict, chain: list | None = None):
    chain = chain if chain is not None else []
    mock = MockHandler(table)
    rh = GuardedRedirectHandler(chain)
    opener = urllib.request.build_opener(rh, mock)
    return opener, mock, chain


def test_detail_client_has_no_binary_download():
    src = inspect.getsource(dc)
    assert "def download_file" not in src
    assert "def fetch_attachment_binary" not in src
    assert "downloadAtchFile" in src  # forbidden fragment only


def test_license_gate_before_network():
    for kt in ("2", "4", "UNKNOWN", "00"):
        try:
            assert_binary_allowed(kt, "PDF")
            assert False
        except BinaryFetchError as e:
            assert e.code == "LICENSE_STORAGE_FORBIDDEN"
    try:
        assert_binary_allowed("1", "VIDEO")
        assert False
    except BinaryFetchError as e:
        assert e.code == "VIDEO_BINARY_FORBIDDEN"
    assert_binary_allowed("1", "PDF")
    assert_binary_allowed("3", "PDF")
    assert_binary_allowed("1", "IMAGE")
    assert_binary_allowed("3", "IMAGE")


def test_schemes_https_only():
    for u in ("http://portal.kosha.or.kr/x", "file:///etc/passwd", "data:text/plain,x", "ftp://portal.kosha.or.kr/x"):
        try:
            assert_https_allowed(u)
            assert False
        except BinaryFetchError as e:
            assert e.code in ("SCHEME_NOT_ALLOWED", "HOST_NOT_ALLOWED")


def test_pdf_magic_and_octet_stream():
    assert_pdf_payload("application/pdf", b"%PDF-1.4")
    assert_pdf_payload("application/octet-stream", b"%PDF-")
    try:
        assert_pdf_payload("application/pdf", b"<html>")
        assert False
    except BinaryFetchError as e:
        assert e.code in ("HTML_NOT_BINARY", "PDF_MAGIC_MISMATCH")


def test_evil_redirect_before_follow():
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "c.pdf")
        evil = b"SECRET_BODY_SHOULD_NOT_BE_READ"
        table = {
            "https://portal.kosha.or.kr/from": (
                302, {"Location": "https://evil.example/steal", "Content-Type": "text/html"}, b"",
            ),
            "https://evil.example/steal": (200, {"Content-Type": "application/pdf"}, evil),
        }
        opener, mock, chain = opener_for(table)
        try:
            fetch_https_binary("https://portal.kosha.or.kr/from", dest, opener=opener, expect_pdf=True)
            assert False
        except BinaryFetchError as e:
            assert e.code == "REDIRECT_HOST_BLOCKED"
        assert "https://evil.example/steal" not in mock.opened


def test_oversize_html_json_and_no_net_blocks():
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "e.pdf")
        huge = str(20 * 1024 * 1024 + 1)
        table = {
            "https://portal.kosha.or.kr/big": (
                200, {"Content-Type": "application/pdf", "Content-Length": huge}, PDF * 10,
            ),
        }
        opener, mock, _ = opener_for(table)
        try:
            fetch_https_binary("https://portal.kosha.or.kr/big", dest, opener=opener, expect_pdf=True)
            assert False
        except BinaryFetchError as e:
            assert e.code == "RESPONSE_TOO_LARGE"
            assert e.body_bytes_read == 0

    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "f.pdf")
        opener, _, _ = opener_for({
            "https://portal.kosha.or.kr/html": (200, {"Content-Type": "text/html"}, b"<html>x</html>"),
        })
        try:
            fetch_https_binary("https://portal.kosha.or.kr/html", dest, opener=opener, expect_pdf=True)
            assert False
        except BinaryFetchError as e:
            assert e.code == "HTML_NOT_BINARY"

    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "g.pdf")
        opener, _, _ = opener_for({
            "https://portal.kosha.or.kr/json": (200, {"Content-Type": "application/json"}, b'{"e":1}'),
        })
        try:
            fetch_https_binary("https://portal.kosha.or.kr/json", dest, opener=opener, expect_pdf=True)
            assert False
        except BinaryFetchError as e:
            assert e.code == "JSON_NOT_BINARY"

    class Boom(urllib.request.BaseHandler):
        handler_order = 1
        def https_open(self, req):
            raise AssertionError("network should not run")

    boom = urllib.request.build_opener(Boom())
    for kt, ct, code in (
        ("2", "PDF", "LICENSE_STORAGE_FORBIDDEN"),
        ("4", "PDF", "LICENSE_STORAGE_FORBIDDEN"),
        ("UNKNOWN", "PDF", "LICENSE_STORAGE_FORBIDDEN"),
        ("00", "PDF", "LICENSE_STORAGE_FORBIDDEN"),
        ("1", "VIDEO", "VIDEO_BINARY_FORBIDDEN"),
    ):
        try:
            fetch_attachment_binary(kogl_type=kt, content_type=ct, atcfl_no="X", atcfl_seq=1, opener=boom)
            assert False
        except BinaryFetchError as e:
            assert e.code == code

    assert pick_first_pdf([
        {"atcflSeq": 3, "orgnlAtchFileNm": "b.pdf", "atcflExtnNm": "pdf"},
        {"atcflSeq": 1, "orgnlAtchFileNm": "a.pdf", "atcflExtnNm": "pdf"},
    ])["orgnlAtchFileNm"] == "a.pdf"


def test_stream_overflow_and_direct_pdf():
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "a.pdf")
        opener, mock, _ = opener_for({
            "https://portal.kosha.or.kr/file": (200, {"Content-Type": "application/pdf"}, PDF),
        })
        got = fetch_https_binary("https://portal.kosha.or.kr/file", dest, opener=opener, expect_pdf=True)
        assert got["ok"] and os.path.isfile(dest)

    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "ov.pdf")
        big = b"%PDF-" + (b"x" * (64 * 1024 + 10))
        opener, _, _ = opener_for({
            "https://portal.kosha.or.kr/stream": (200, {"Content-Type": "application/pdf"}, big),
        })
        try:
            fetch_https_binary(
                "https://portal.kosha.or.kr/stream", dest, opener=opener, expect_pdf=True, max_bytes=100,
            )
            assert False
        except BinaryFetchError as e:
            assert e.code == "RESPONSE_TOO_LARGE"
            assert e.body_bytes_read > 0
