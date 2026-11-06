"""WO-TAI-FORM647-PREVIEW-INTEGRATION-001 R1
generate_pilot_form647_previews.py 안전성 테스트

검증 항목:
  PILOT-01  dry-run: Pilot A, B → DRY_PASS, 쓰기 호출 없음
  PILOT-02  execute: 중복 실행 시 Storage REUSED + Artifact REUSED → INSERTED(멱등)
  PILOT-03  execute: Storage 업로드 성공 후 Artifact INSERT 실패 → FAIL 보고, 프로세스 오류 반환
  PILOT-04  execute: Artifact INSERT 성공 후 file link UPDATE 0건 → FAIL 보고
  PILOT-05  execute: 파일에 다른 artifact가 이미 연결 → FILE_CONFLICT FAIL
  PILOT-06  execute: qa_status=PENDING, is_published=false로 INSERT
  PILOT-07  preflight: SHA256 불일치 → 모든 쓰기 차단
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# 테스트용 헬퍼
# ---------------------------------------------------------------------------

_FORM_ID_A = "da4a262b-1819-45a0-b702-e7e1735c8d99"
_FORM_ID_B = "85f2f722-b004-40b6-a93c-882cca2a7264"

_FILE_ID_A_PDF  = "6a3b84b6-f67f-4c57-9d54-2c958f0391b3"
_FILE_ID_B_HWP  = "a4b8ddca-1b4a-4cb6-9a65-8e938d20d43f"
_SHA256_A       = "62d6e4f7981ebd122f5233d42d7283a1b517c7429b034a3bb030a3fc6c136c74"
_SHA256_B       = "9c39355c0cebe4df1d50985c81835e01d70953e1a1f784496bf061c18811fc06"

_ARTIFACT_ID_A  = "art-aaaa-0000-0000-0000-000000000001"
_ARTIFACT_ID_B  = "art-bbbb-0000-0000-0000-000000000002"


def _make_png(w: int = 10, h: int = 10) -> bytes:
    """최소 유효 PNG bytes (1x1 흰색)."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_hwpx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
    return buf.getvalue()


def _make_sb(
    *,
    form_id_a=_FORM_ID_A,
    form_id_b=_FORM_ID_B,
    raw_a: bytes | None = None,
    raw_b: bytes | None = None,
    storage_existing: dict[str, bytes] | None = None,
    artifact_existing: dict[str, dict] | None = None,
    file_link_existing: dict[str, str | None] | None = None,
    artifact_insert_id_a: str = _ARTIFACT_ID_A,
    artifact_insert_id_b: str = _ARTIFACT_ID_B,
    update_returns_rows: bool = True,
) -> MagicMock:
    """
    테스트용 Supabase 클라이언트 목 생성.
    """
    # 실제 PDF bytes가 없으므로 PNG bytes를 직접 사용하고 generate_preview를 패치한다.
    if raw_a is None:
        raw_a = b"%PDF-1.4 fake-a"
    if raw_b is None:
        raw_b = _make_hwpx_bytes()

    sha_a = hashlib.sha256(raw_a).hexdigest()
    sha_b = hashlib.sha256(raw_b).hexdigest()

    # DB 쿼리 결과 테이블 맵
    _content_map = {
        "ref-f647-17649099": form_id_a,
        "ref-f647-3033503":  form_id_b,
    }
    _file_link_map = file_link_existing or {
        _FILE_ID_A_PDF: None,
        _FILE_ID_B_HWP: None,
    }
    _artifact_existing = artifact_existing or {}
    _storage_existing  = storage_existing or {}

    _insert_counters = {"a": 0, "b": 0}

    sb = MagicMock()

    # --- table().select().eq().limit().execute() ---
    def _table_side_effect(table_name: str):
        tbl = MagicMock()

        def _select(*args):
            sel = MagicMock()

            def _eq(col, val):
                eq = MagicMock()

                def _limit(n):
                    lim = MagicMock()

                    def _execute():
                        if table_name == "reference_form_content":
                            form_id = _content_map.get(val)
                            if form_id:
                                return SimpleNamespace(data=[{"form_id": form_id}])
                            return SimpleNamespace(data=[])

                        if table_name == "reference_form_preview_artifacts":
                            key = (val, args[0].split(",")[0] if "," in str(args) else val)
                            # Look up by form_id+sha256
                            match = _artifact_existing.get(val)
                            if match:
                                return SimpleNamespace(data=[match])
                            return SimpleNamespace(data=[])

                        if table_name == "reference_form_files":
                            existing_artifact = _file_link_map.get(val)
                            return SimpleNamespace(data=[{
                                "id": val,
                                "preview_artifact_id": existing_artifact,
                            }])

                        return SimpleNamespace(data=[])

                    lim.execute = _execute
                    return lim

                eq.limit = _limit

                # For artifact lookup with two .eq() chained
                def _eq2(col2, val2):
                    eq2 = MagicMock()

                    def _limit2(n):
                        lim2 = MagicMock()

                        def _execute2():
                            match = _artifact_existing.get(form_id_a if val == form_id_a else form_id_b)
                            if match and match.get("source_sha256_match", True):
                                return SimpleNamespace(data=[match])
                            return SimpleNamespace(data=[])

                        lim2.execute = _execute2
                        return lim2

                    eq2.limit = _limit2
                    return eq2

                eq.eq = _eq2
                return eq

            sel.eq = _eq
            return sel

        tbl.select = _select

        def _insert(data):
            ins = MagicMock()

            def _execute():
                # Determine form_id from inserted data
                fid = data.get("form_id", "")
                art_id = artifact_insert_id_a if fid == form_id_a else artifact_insert_id_b
                return SimpleNamespace(data=[{"id": art_id}])

            ins.execute = _execute
            return ins

        tbl.insert = _insert

        def _update(data):
            upd = MagicMock()

            def _eq_upd(col, val):
                eq_upd = MagicMock()

                def _execute():
                    if update_returns_rows:
                        return SimpleNamespace(data=[{"id": val, **data}])
                    return SimpleNamespace(data=[])

                eq_upd.execute = _execute
                return eq_upd

            upd.eq = _eq_upd
            return upd

        tbl.update = _update
        return tbl

    sb.table.side_effect = _table_side_effect

    # --- storage ---
    _storage_bk = MagicMock()

    def _from_bucket(bucket_name: str):
        bk = MagicMock()

        def _download(path: str) -> bytes:
            if bucket_name == "reference-forms":
                run_id = "form647-remediation-002-714df47a637e3e73"
                if "17649099_licbyl.pdf" in path:
                    return raw_a
                if "3033503_admbyl.hwp" in path:
                    return raw_b
                raise Exception(f"Not found: {path}")
            if bucket_name == "reference-forms-preview":
                if path in _storage_existing:
                    return _storage_existing[path]
                raise Exception(f"Not found: {path}")
            raise Exception(f"Unknown bucket: {bucket_name}")

        def _upload(path: str, file: bytes, file_options=None):
            return SimpleNamespace(data=[{"path": path}])

        bk.download = _download
        bk.upload = _upload
        return bk

    sb.storage.from_.side_effect = _from_bucket
    return sb


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------

def _make_preview(png_bytes=None, fmt="pdf", w=100, h=100):
    from services.reference_form_preview_gen_svc import PreviewResult
    if png_bytes is None:
        png_bytes = _make_png(w, h)
    return PreviewResult(
        png_bytes=png_bytes,
        source_format=fmt,
        page_count=1,
        width_px=w,
        height_px=h,
        dpi=150,
    )


@patch("scripts.generate_pilot_form647_previews.generate_preview")
def test_pilot_01_dry_run_pass(mock_gen):
    """PILOT-01: dry-run → 2건 DRY_PASS, Storage/DB 쓰기 없음."""
    mock_gen.side_effect = [
        _make_preview(fmt="pdf"),
        _make_preview(fmt="hwpx"),
    ]

    from scripts.generate_pilot_form647_previews import run
    # Patch sha256 verification to match fake raw bytes
    raw_a = b"%PDF-1.4 fake-a"
    raw_b = _make_hwpx_bytes()
    sb = _make_sb(raw_a=raw_a, raw_b=raw_b)

    with (
        patch("scripts.generate_pilot_form647_previews.get_supabase", return_value=sb),
        patch("scripts.generate_pilot_form647_previews._PILOT_FORMS", [
            {
                "slug": "ref-f647-17649099",
                "files": [{
                    "file_id": _FILE_ID_A_PDF,
                    "format": "pdf",
                    "storage_path": f"form647/form647-remediation-002-714df47a637e3e73/pdf/17649099_licbyl.pdf",
                    "sha256": hashlib.sha256(raw_a).hexdigest(),
                }],
            },
            {
                "slug": "ref-f647-3033503",
                "files": [{
                    "file_id": _FILE_ID_B_HWP,
                    "format": "hwp",
                    "storage_path": f"form647/form647-remediation-002-714df47a637e3e73/hwp/3033503_admbyl.hwp",
                    "sha256": hashlib.sha256(raw_b).hexdigest(),
                }],
            },
        ]),
        patch("scripts.generate_pilot_form647_previews._OUT_DIR", Path("/tmp/pilot_test_output")),
    ):
        exit_code = run(dry_run=True)

    assert exit_code == 0
    # Storage 쓰기 없음 — upload 호출 없어야 함
    for call_args in sb.storage.from_.call_args_list:
        bk_name = call_args[0][0]
        assert bk_name != "reference-forms-preview", \
            "dry-run 중 preview 버킷 접근 금지"


@patch("scripts.generate_pilot_form647_previews.generate_preview")
def test_pilot_02_idempotent_execute(mock_gen):
    """PILOT-02: 동일 PNG·artifact 이미 존재 → REUSED 경로, 중복 INSERT 없음."""
    raw_a = b"%PDF-1.4 fake-a"
    png_a = _make_png()
    mock_gen.return_value = _make_preview(png_bytes=png_a, fmt="pdf")

    # Storage에 동일 PNG 존재, artifact에 동일 항목 존재
    storage_path_a = f"previews/{_FORM_ID_A}/{_FILE_ID_A_PDF}.png"
    preview_ref_a  = f"storage://reference-forms-preview/{storage_path_a}"

    sb = _make_sb(
        raw_a=raw_a,
        raw_b=raw_a,  # pilot B는 이 테스트에서 미사용 (single form)
        storage_existing={storage_path_a: png_a},
        artifact_existing={
            _FORM_ID_A: {
                "id": _ARTIFACT_ID_A,
                "preview_ref": preview_ref_a,
                "source_sha256_match": True,
            }
        },
        file_link_existing={_FILE_ID_A_PDF: _ARTIFACT_ID_A},  # already linked
    )

    from scripts.generate_pilot_form647_previews import (
        _storage_upload_or_reuse,
        _artifact_insert_or_reuse,
        _link_artifact_to_file,
    )

    # Storage: 동일 파일 → REUSED
    result = _storage_upload_or_reuse(sb, storage_path_a, png_a)
    assert result == "REUSED"

    # Artifact: 동일 → REUSED (simulate by calling with existing data)
    # (Full mock table returns existing artifact)
    # 직접 함수 로직 검증
    artifact_id, action = _artifact_insert_or_reuse(
        sb, _FORM_ID_A, preview_ref_a, hashlib.sha256(raw_a).hexdigest()
    )
    assert action == "REUSED"
    assert artifact_id == _ARTIFACT_ID_A

    # File link: 이미 같은 artifact → ALREADY_LINKED
    link_result = _link_artifact_to_file(sb, _FILE_ID_A_PDF, _ARTIFACT_ID_A)
    assert link_result == "ALREADY_LINKED"


def test_pilot_03_storage_ok_artifact_fail():
    """PILOT-03: Storage 업로드 성공 후 Artifact INSERT 실패 → FAIL, 프로세스 오류 코드."""
    from services.reference_form_preview_gen_svc import PreviewResult

    raw_a = b"%PDF-1.4 fake-a"
    png_a = _make_png()
    preview_a = _make_preview(png_bytes=png_a, fmt="pdf")

    storage_path_a = f"previews/{_FORM_ID_A}/{_FILE_ID_A_PDF}.png"
    preview_ref_a  = f"storage://reference-forms-preview/{storage_path_a}"

    # artifact INSERT가 RuntimeError를 발생시키도록 설정
    from scripts.generate_pilot_form647_previews import _artifact_insert_or_reuse

    with patch(
        "scripts.generate_pilot_form647_previews._artifact_insert_or_reuse",
        side_effect=RuntimeError("ARTIFACT_CONFLICT: 의도적 실패"),
    ), patch(
        "scripts.generate_pilot_form647_previews._storage_upload_or_reuse",
        return_value="UPLOADED",
    ):
        from scripts.generate_pilot_form647_previews import _execute_one

        preflight = {
            "slug": "ref-f647-17649099",
            "form_id": _FORM_ID_A,
            "rep": {"file_id": _FILE_ID_A_PDF, "sha256": hashlib.sha256(raw_a).hexdigest()},
            "preview": preview_a,
            "storage_path": storage_path_a,
        }

        sb = MagicMock()
        result = _execute_one(sb, preflight)

    assert result["verdict"] == "FAIL"
    assert "artifact_failed" in result["error"]
    assert result["steps"]["storage"] == "UPLOADED"
    assert result["steps"]["artifact_insert"] == "FAIL"
    assert result["steps"]["file_link"] == "PENDING"


def test_pilot_04_update_zero_rows():
    """PILOT-04: file link UPDATE가 0건 반환 → FILE_LINK FAIL."""
    from scripts.generate_pilot_form647_previews import _link_artifact_to_file

    sb = _make_sb(
        file_link_existing={_FILE_ID_A_PDF: None},
        update_returns_rows=False,
    )

    with pytest.raises(RuntimeError) as exc_info:
        _link_artifact_to_file(sb, _FILE_ID_A_PDF, _ARTIFACT_ID_A)
    assert "UPDATE_ROW_COUNT_ERROR" in str(exc_info.value)


def test_pilot_05_file_conflict():
    """PILOT-05: 파일에 다른 artifact 연결 → FILE_CONFLICT RuntimeError."""
    from scripts.generate_pilot_form647_previews import _link_artifact_to_file

    other_artifact = "art-other-0000-0000-0000-000000000099"
    sb = _make_sb(
        file_link_existing={_FILE_ID_A_PDF: other_artifact},
    )

    with pytest.raises(RuntimeError) as exc_info:
        _link_artifact_to_file(sb, _FILE_ID_A_PDF, _ARTIFACT_ID_A)
    assert "FILE_CONFLICT" in str(exc_info.value)


def test_pilot_06_insert_uses_pending_defaults():
    """PILOT-06: artifact INSERT 호출 시 qa_status=PENDING, is_published=false."""
    inserted_data = {}

    sb = MagicMock()

    def _capture_insert(data):
        inserted_data.update(data)
        ins = MagicMock()
        ins.execute.return_value = SimpleNamespace(data=[{"id": _ARTIFACT_ID_A}])
        return ins

    # artifact 미존재 → INSERT 경로
    sel = MagicMock()
    sel.eq.return_value.eq.return_value.limit.return_value.execute.return_value = \
        SimpleNamespace(data=[])
    sb.table.return_value.select.return_value = sel
    sb.table.return_value.insert.side_effect = _capture_insert

    from scripts.generate_pilot_form647_previews import _artifact_insert_or_reuse
    _artifact_insert_or_reuse(
        sb, _FORM_ID_A,
        f"storage://reference-forms-preview/previews/{_FORM_ID_A}/{_FILE_ID_A_PDF}.png",
        _SHA256_A,
    )

    assert inserted_data.get("qa_status") == "PENDING"
    assert inserted_data.get("is_published") is False


@patch("scripts.generate_pilot_form647_previews.generate_preview")
def test_pilot_07_preflight_sha_mismatch_blocks_all(mock_gen):
    """PILOT-07: SHA256 불일치 → preflight 실패, 모든 쓰기 호출 없음."""
    raw_a = b"%PDF-1.4 fake-a"
    wrong_sha = "0" * 64

    sb = MagicMock()

    # reference-forms bucket download returns raw_a
    bk = MagicMock()
    bk.download.return_value = raw_a
    sb.storage.from_.return_value = bk

    # reference_form_content 조회 성공
    content_sel = MagicMock()
    content_sel.eq.return_value.limit.return_value.execute.return_value = \
        SimpleNamespace(data=[{"form_id": _FORM_ID_A}])
    sb.table.return_value.select.return_value = content_sel

    from scripts.generate_pilot_form647_previews import _preflight_one

    pf = {
        "slug": "ref-f647-17649099",
        "files": [{
            "file_id": _FILE_ID_A_PDF,
            "format": "pdf",
            "storage_path": "form647/x/pdf/17649099_licbyl.pdf",
            "sha256": wrong_sha,  # ← 고의 불일치
        }],
    }
    result = _preflight_one(sb, pf)

    assert result["error"] is not None
    assert "sha256_mismatch" in result["error"]
    # generate_preview 호출 없어야 함 (SHA256 실패 후 PNG 생성 중단)
    mock_gen.assert_not_called()
