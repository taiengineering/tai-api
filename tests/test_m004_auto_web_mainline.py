"""WO-TAI-M004-AUTO-WEB-MAINLINE-INTEGRATION-001 — gap tests only.

기존 테스트 재사용 매핑 (코드 변경 없음):
  A01 AUTO Inspection HTML    ← test_auto_doc_security_integration::test_SI2
                                 test_auto_document_quality::T1-T6
  A02 AUTO Inspection PDF     ← test_auto_doc_security_integration::test_SI4
  A03 AUTO TBM HTML/PDF       ← test_auto_doc_security_integration::test_ST2 / test_ST4
                                 test_auto_document_quality::T7-T9
  A04 AUTO 미완료 업무 차단   ← test_auto_reuse_01_discovery::test_RR1-RR4
  A05 AUTO 타사업장 접근 차단 ← test_auto_doc_factory_isolation (13 tests)
                                 test_auto_doc_security_integration::test_SI1/SI3/ST1/ST3
  A06 AUTO 미승인 필드 자동입력 차단 ← NEW: test_A06_generate_document_no_auto_fetcher
  W01 WEB 승인 Fixture 열기   ← test_m004_e2e_pipeline::test_E2E_02
  W02 WEB 입력·수정           ← test_m004_e2e_pipeline::test_E2E_04
  W03 WEB 저장                ← test_m004_e2e_pipeline::test_E2E_02 / test_E2E_04
  W04 WEB 복원·재수정         ← test_m004_e2e_pipeline::test_E2E_03
  W05 WEB HTML 렌더링         ← test_m004_e2e_pipeline::test_E2E_08
  W06 WEB PDF 생성            ← NEW: test_W06_generate_document_pdf
  W07 WEB CANDIDATE 차단      ← test_m004_e2e_pipeline::test_E2E_10a
  W08 WEB 상태 전이           ← test_m004_e2e_pipeline::test_E2E_05a / 05b / 05c
  W09 WEB 봉인 문서 편집 차단 ← test_m004_e2e_pipeline::test_E2E_10d
  W10 WEB 잘못된 전이 차단    ← test_m004_e2e_pipeline::test_E2E_10c
  C01 REFERENCE_DOWNLOAD      ← test_document_catalog::T2 / T10
  C02 OFFICIAL_ORIGINAL       ← test_document_catalog::T3 / T4
  C03 WEB_EDIT                ← test_document_catalog::T1 / T9
  C04 SAAS_EXPORT             ← test_document_catalog::T9
  C05 SAAS_AUTO_FILL          ← test_document_catalog::T5
  C06 채널 필터               ← test_document_catalog::T11 / T12 / T13

Production write = 0. Fake DB only.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOC_ID  = "doc00001-0000-0000-0000-000000000001"
USER_ID = "user0001-0000-0000-0000-000000000001"
_FAKE_HTML = "<html><body>WEB 문서</body></html>"
_FAKE_PDF  = b"%PDF-1.4 fake"


def _fake_doc_scope(_sb, _doc_id, _user):
    return {"id": _doc_id, "company_id": "c1", "factory_id": "f1", "status": "DRAFT"}


# ══════════════════════════════════════════════════════════════════════════════
# A06  AUTO 미승인 필드 자동입력 차단
#      generate_document 는 InspectionFetcher / TbmFetcher 를 호출하지 않는다.
#      사용자가 입력한 runtime_data_json 만 사용하는 svc.render_document_html() 경로.
# ══════════════════════════════════════════════════════════════════════════════

def test_A06_generate_document_no_auto_fetcher():
    """WEB export_type=HTML: render_document_html 호출 O, InspectionFetcher/TbmFetcher 호출 X."""
    from schemas.document_engine import GenerateDocumentIn
    from routers.document_engine_api import generate_document

    inspection_fetch_called: list[bool] = []
    tbm_fetch_called: list[bool] = []

    async def _fake_insp_fetch(*a, **kw):
        inspection_fetch_called.append(True)
        return {}

    async def _fake_tbm_fetch(*a, **kw):
        tbm_fetch_called.append(True)
        return {}

    with patch("routers.document_engine_api.get_supabase", return_value=MagicMock()):
        with patch("routers.document_engine_api._check_doc_scope", side_effect=_fake_doc_scope):
            with patch("routers.document_engine_api.svc.render_document_html", return_value=_FAKE_HTML):
                with patch("services.document_engine.fetchers.inspection_fetcher.InspectionFetcher.fetch",
                           new_callable=AsyncMock, side_effect=_fake_insp_fetch):
                    with patch("services.document_engine.fetchers.tbm_fetcher.TbmFetcher.fetch",
                               new_callable=AsyncMock, side_effect=_fake_tbm_fetch):
                        body = GenerateDocumentIn(export_type="HTML")
                        resp = asyncio.run(
                            generate_document(DOC_ID, body, current_user={"id": USER_ID})
                        )

    assert not inspection_fetch_called, \
        "generate_document must NOT call InspectionFetcher.fetch (auto fill 금지)"
    assert not tbm_fetch_called, \
        "generate_document must NOT call TbmFetcher.fetch (auto fill 금지)"
    assert _FAKE_HTML in resp.body.decode(), "render_document_html 결과가 응답에 포함돼야 함"


# ══════════════════════════════════════════════════════════════════════════════
# W06  WEB PDF 생성
#      generate_document(export_type=PDF) → application/pdf + 비어있지 않은 bytes
# ══════════════════════════════════════════════════════════════════════════════

def test_W06_generate_document_pdf():
    """export_type=PDF → Content-Type: application/pdf, PDF bytes 반환, DB 쓰기 없음."""
    from schemas.document_engine import GenerateDocumentIn
    from routers.document_engine_api import generate_document

    with patch("routers.document_engine_api.get_supabase", return_value=MagicMock()):
        with patch("routers.document_engine_api._check_doc_scope", side_effect=_fake_doc_scope):
            with patch("routers.document_engine_api.svc.render_document_html",
                       return_value=_FAKE_HTML) as mock_render:
                with patch("routers.document_engine_api._html_to_pdf",
                           new_callable=AsyncMock, return_value=_FAKE_PDF) as mock_pdf:
                    body = GenerateDocumentIn(export_type="PDF")
                    resp = asyncio.run(
                        generate_document(DOC_ID, body, current_user={"id": USER_ID})
                    )

    assert resp.media_type == "application/pdf", \
        f"PDF export 시 Content-Type은 application/pdf여야 함, got {resp.media_type!r}"
    assert resp.body == _FAKE_PDF, "PDF bytes 원본 반환 필요"
    mock_render.assert_called_once_with(DOC_ID)
    mock_pdf.assert_called_once_with(_FAKE_HTML)
