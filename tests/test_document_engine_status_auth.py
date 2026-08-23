"""WP-DOCUMENT-ARCH-05B-B1-CORR-01 — router submitter identity binding tests.

SUBMITTED_FOR_REVIEW 시 submitted_by 가 반드시 인증 사용자로 기록되는지(위조 차단),
APPROVED_BY_HUMAN 이 confirm_document_atomic 으로 분기되는지 검증한다.

라우터 함수를 직접 호출한다. fastapi/schemas/auth/svc 는 경량 stub 으로 대체한다.
"""

import sys
import types
from pathlib import Path

# ── repo-relative 경로 (특정 환경 비종속) ────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── 경량 stub 주입 (import 전에) ───────────────────────────────────
USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "99999999-9999-9999-9999-999999999999"
DOC_ID = "dddddddd-0001-0001-0001-000000000001"


# schemas.document_engine stub (StatusChangeIn 등)
_schemas_pkg = types.ModuleType("schemas")
_schemas_doc = types.ModuleType("schemas.document_engine")
class _Model:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
for _n in ("DocumentCreateIn", "DocumentUpdateIn", "StatusChangeIn",
           "EvidenceLinkIn", "GenerateDocumentIn"):
    setattr(_schemas_doc, _n, _Model)
_schemas_pkg.document_engine = _schemas_doc
sys.modules["schemas"] = _schemas_pkg
sys.modules["schemas.document_engine"] = _schemas_doc

# routers.auth.get_current_user stub
_routers_pkg = sys.modules.get("routers") or types.ModuleType("routers")
_routers_pkg.__path__ = [str(ROOT / "routers")]
sys.modules["routers"] = _routers_pkg
_auth = types.ModuleType("routers.auth")
_auth.get_current_user = lambda: {"id": USER_ID}
sys.modules["routers.auth"] = _auth

# services.document_engine_svc stub (change_status 관찰)
_svc = types.ModuleType("services.document_engine_svc")
_svc_calls = []
def _change_status(doc_id, to_status, actor_id, comment):
    _svc_calls.append({"doc_id": doc_id, "to_status": to_status,
                       "actor_id": actor_id, "comment": comment})
    return {"id": doc_id, "status": to_status, "submitted_by": actor_id}
_svc.change_status = _change_status
_svc._approval = lambda *a, **k: None
_svc._audit = lambda *a, **k: None
sys.modules["services.document_engine_svc"] = _svc

# services.document_confirm_svc — 실제 모듈 유지하되 confirm 관찰
import services.document_confirm_svc as confirm_mod
_confirm_calls = []
def _fake_confirm(doc_id, *, actor_id, comment, current_user):
    _confirm_calls.append({"doc_id": doc_id, "actor_id": actor_id,
                           "comment": comment, "current_user": current_user})
    return {"id": doc_id, "status": "APPROVED_BY_HUMAN"}

# 라우터 import (stub 적용 상태)
import routers.document_engine_api as api
api.confirm_document_atomic = _fake_confirm
from fastapi import HTTPException


def _body(to_status, actor_id=None, comment="c"):
    return _Model(to_status=to_status, actor_id=actor_id, comment=comment)


def _reset():
    _svc_calls.clear()
    _confirm_calls.clear()


# ── R1: SUBMITTED_FOR_REVIEW, actor_id 없음 → svc actor = current_user.id ──
def test_R1_submit_no_actor_uses_current_user():
    _reset()
    out = api.change_status(DOC_ID, _body("SUBMITTED_FOR_REVIEW", actor_id=None),
                            current_user={"id": USER_ID})
    assert len(_svc_calls) == 1
    assert _svc_calls[0]["actor_id"] == USER_ID          # submitted_by = 인증 사용자
    assert _svc_calls[0]["to_status"] == "SUBMITTED_FOR_REVIEW"
    assert out["status"] == "success"


# ── R2: actor_id == current_user.id → svc actor = current_user.id ─────────
def test_R2_submit_actor_matches():
    _reset()
    api.change_status(DOC_ID, _body("SUBMITTED_FOR_REVIEW", actor_id=USER_ID),
                      current_user={"id": USER_ID})
    assert len(_svc_calls) == 1 and _svc_calls[0]["actor_id"] == USER_ID


# ── R3: actor_id != current_user.id → 403, svc.change_status 미호출 ────────
def test_R3_submit_actor_spoof_403():
    _reset()
    try:
        api.change_status(DOC_ID, _body("SUBMITTED_FOR_REVIEW", actor_id=OTHER_ID),
                          current_user={"id": USER_ID})
        assert False
    except HTTPException as e:
        assert e.status_code == 403
    assert len(_svc_calls) == 0   # 사칭 시 서비스 호출 0


# ── 보강 R4: APPROVED_BY_HUMAN → confirm_document_atomic 분기 ─────────
def test_R4_approve_routes_to_confirm():
    _reset()
    out = api.change_status(DOC_ID, _body("APPROVED_BY_HUMAN", actor_id=None),
                            current_user={"id": USER_ID})
    assert len(_confirm_calls) == 1 and len(_svc_calls) == 0
    assert out["status"] == "success"


# ── 보강 R5: 그 외 상태(REJECTED)는 기존 svc.change_status 경로 유지 ───────
def test_R5_other_status_uses_legacy_svc():
    _reset()
    api.change_status(DOC_ID, _body("REJECTED_BY_HUMAN", actor_id=USER_ID),
                      current_user={"id": USER_ID})
    # 이번 WP 범위 밖 — 기존 경로로 actor_id 그대로 전달(재설계 금지)
    assert len(_svc_calls) == 1 and _svc_calls[0]["to_status"] == "REJECTED_BY_HUMAN"
    assert len(_confirm_calls) == 0
