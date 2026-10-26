"""tests/test_official_forms_download.py — FORM647 공식서식 다운로드 게이트 테스트

WO: WO-TAI-DOC-M004-FORM647-DOWNLOAD-API-003 STEP C

T01: 라우터 auth 의존성 구조 확인
T02: 잘못된 file_type → 404
T03: LEG DB 빈 결과 (ek 없음) → 404
T04: service_sot_gate='BLOCKED' → 404 (현재 운영 시나리오)
T05: source_gate!='PASS' → 404
T06: private_storage_path=None → 404
T07: storage_path prefix 불일치 → 404 (경로 조작 차단)
T08: 모든 게이트 PASS + storage 정상 → 200 HWP 응답
T09: PDF 경로 정상 분기 (Content-Type application/pdf)
T10: storage download 실패 → 502
T11: LEG DB 연결 env 미설정 → 503
T12: LEG form_snapshots 조회 예외 → 503 fail-closed
T13: LEG source_binary_snapshots 조회 예외 → 503 fail-closed
T14: run_id 연계 — binary_snapshots 조회에 run_id 조건 포함
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, call, patch

import pytest

_RUN_ID = "form647-remediation-002-714df47a637e3e73"
_SNAP_PASS = {"run_id": _RUN_ID, "source_gate": "PASS", "service_sot_gate": "PASS"}
_SNAP_BLOCKED = {"run_id": _RUN_ID, "source_gate": "PASS", "service_sot_gate": "BLOCKED"}
_SNAP_NO_SOURCE = {"run_id": _RUN_ID, "source_gate": "FAIL", "service_sot_gate": "PASS"}
_BINARY_HWP = {"private_storage_path": f"form647/{_RUN_ID}/hwp/sample.hwp"}
_BINARY_PDF = {"private_storage_path": f"form647/{_RUN_ID}/pdf/sample.pdf"}
_BINARY_NULL = {"private_storage_path": None}
_BINARY_BAD_PREFIX = {"private_storage_path": "other-bucket/secret/key.hwp"}


def _make_leg_mock(snap_data, binary_data=None):
    mock_leg = MagicMock()

    def side_effect_table(name):
        t = MagicMock()
        if name == "form_snapshots":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = snap_data
        else:
            # source_binary_snapshots: .eq(run_id).eq(ek).eq(file_type)
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
                binary_data if binary_data is not None else []
            )
        return t

    mock_leg.schema.return_value.table.side_effect = side_effect_table
    return mock_leg


class TestT01_AuthDependency:
    def test_router_endpoint_has_get_current_user(self):
        import inspect
        from routers.official_forms_download import router
        from routers.auth import get_current_user

        assert any("/official-forms" in r.path for r in router.routes)
        for route in router.routes:
            sig = inspect.signature(route.endpoint)
            deps = [
                p.default.dependency
                for p in sig.parameters.values()
                if hasattr(p.default, "dependency")
            ]
            assert get_current_user in deps, (
                f"route {route.path} must declare get_current_user dependency"
            )


class TestT02_InvalidFileType:
    def test_unknown_file_type_returns_404(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        with pytest.raises(HTTPException) as exc_info:
            download_official_form(ek="FORM-001", file_type="doc", current={})
        assert exc_info.value.status_code == 404


class TestT03_EkNotFound:
    def test_empty_snap_rows_returns_404(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[])
        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="NONEXISTENT", file_type="hwp", current={})
        assert exc_info.value.status_code == 404


class TestT04_GateBlocked:
    def test_service_sot_gate_blocked_returns_404(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_BLOCKED])
        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 404


class TestT05_SourceGateFail:
    def test_source_gate_not_pass_returns_404(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_NO_SOURCE])
        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 404


class TestT06_StoragePathNull:
    def test_none_storage_path_returns_404(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_PASS], binary_data=[_BINARY_NULL])
        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 404

    def test_empty_binary_rows_returns_404(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_PASS], binary_data=[])
        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 404


class TestT07_PathPrefixViolation:
    def test_bad_prefix_storage_path_returns_404(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_PASS], binary_data=[_BINARY_BAD_PREFIX])
        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 404


class TestT08_HwpGatePass:
    def test_hwp_returns_200_with_correct_headers(self):
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_PASS], binary_data=[_BINARY_HWP])
        mock_supabase = MagicMock()
        fake_bytes = b"\xd0\xcf\x11\xe0fake-hwp"
        mock_supabase.storage.from_.return_value.download.return_value = fake_bytes

        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg), \
             patch("routers.official_forms_download.get_supabase", return_value=mock_supabase):
            resp = download_official_form(ek="FORM-001", file_type="hwp", current={})

        assert resp.body == fake_bytes
        assert resp.media_type == "application/x-hwp"
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd
        assert "filename*=UTF-8''" in cd
        assert resp.headers["x-content-type-options"] == "nosniff"
        mock_supabase.storage.from_.assert_called_once_with("form-originals")


class TestT09_PdfGatePass:
    def test_pdf_returns_correct_content_type(self):
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_PASS], binary_data=[_BINARY_PDF])
        mock_supabase = MagicMock()
        fake_bytes = b"%PDF-1.4 fake"
        mock_supabase.storage.from_.return_value.download.return_value = fake_bytes

        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg), \
             patch("routers.official_forms_download.get_supabase", return_value=mock_supabase):
            resp = download_official_form(ek="FORM-001", file_type="pdf", current={})

        assert resp.media_type == "application/pdf"
        assert resp.body == fake_bytes


class TestT10_StorageFailure:
    def test_storage_error_returns_502(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = _make_leg_mock(snap_data=[_SNAP_PASS], binary_data=[_BINARY_HWP])
        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.download.side_effect = RuntimeError("storage error")

        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg), \
             patch("routers.official_forms_download.get_supabase", return_value=mock_supabase):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 502


class TestT11_LegEnvMissing:
    def test_missing_env_raises_503_at_endpoint(self):
        import routers.official_forms_download as mod
        from fastapi import HTTPException

        original = mod._leg_client
        mod._leg_client = None
        try:
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("LEG_SUPABASE_URL", None)
                os.environ.pop("LEG_SUPABASE_SERVICE_ROLE_KEY", None)
                with pytest.raises(HTTPException) as exc_info:
                    mod.download_official_form(ek="FORM-001", file_type="hwp", current={})
            assert exc_info.value.status_code == 503
        finally:
            mod._leg_client = original


class TestT12_LegSnapQueryException:
    def test_leg_snap_exception_returns_503_fail_closed(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = MagicMock()
        (mock_leg.schema.return_value.table.return_value
         .select.return_value.eq.return_value.limit.return_value
         .execute.side_effect) = ConnectionError("network error")

        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 503


class TestT13_LegBinaryQueryException:
    def test_leg_binary_exception_returns_503_fail_closed(self):
        from fastapi import HTTPException
        from routers.official_forms_download import download_official_form

        mock_leg = MagicMock()

        call_count = [0]

        def side_effect_table(name):
            t = MagicMock()
            if name == "form_snapshots":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [_SNAP_PASS]
            else:
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = ConnectionError("db error")
            return t

        mock_leg.schema.return_value.table.side_effect = side_effect_table

        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg):
            with pytest.raises(HTTPException) as exc_info:
                download_official_form(ek="FORM-001", file_type="hwp", current={})
        assert exc_info.value.status_code == 503


class TestT14_RunIdLinkage:
    def test_binary_query_uses_run_id_from_snap(self):
        from routers.official_forms_download import download_official_form

        captured_eq_calls = []
        mock_leg = MagicMock()

        def side_effect_table(name):
            t = MagicMock()
            if name == "form_snapshots":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [_SNAP_PASS]
            else:
                # capture the .eq() chain to verify run_id is first
                mock_chain = MagicMock()

                def capture_eq(col, val):
                    captured_eq_calls.append((col, val))
                    return mock_chain

                t.select.return_value.eq.side_effect = capture_eq
                mock_chain.eq.side_effect = capture_eq
                mock_chain.limit.return_value.execute.return_value.data = [_BINARY_HWP]
            return t

        mock_leg.schema.return_value.table.side_effect = side_effect_table
        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.download.return_value = b"\xd0\xcf"

        with patch("routers.official_forms_download._get_leg_client", return_value=mock_leg), \
             patch("routers.official_forms_download.get_supabase", return_value=mock_supabase):
            download_official_form(ek="FORM-001", file_type="hwp", current={})

        run_id_calls = [c for c in captured_eq_calls if c[0] == "run_id"]
        assert run_id_calls, "binary_snapshots query must include run_id condition"
        assert run_id_calls[0][1] == _RUN_ID
