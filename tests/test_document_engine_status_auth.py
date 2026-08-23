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

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "99999999-9999-9999-9999-999999999999"
DOC_ID = "dddddddd-0001-0001-0001-000000000001"

_svc_calls = []
_confirm_calls = []


def _change_status(doc_id, to_status, actor_id, comment):
    _svc_calls.append({"doc_id": doc_id, "to_status": to_status,
                       "actor_id": actor_id, "comment": comment})
    return {"id": doc_id, "status": to_status, "submitted_by": actor_id}


def _fake_confirm(doc_id, *, actor_id, comment, current_user):
    _confirm_calls.append({"doc_id": doc_id, "actor_id": actor_id,
                           "comment": comment, "current_user": current_user})
    return {"id": doc_id, "status": "APPROVED_BY_HUMAN"}


class _Model:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ── sys.modules 격리: stub 설치 → 대상 라우터 import → 즉시 전역 원복 ──────────
#    collection 시점에 sys.modules 를 전역으로 오염시키지 않는다. 실제 대상
#    module object(api, HTTPException)만 지역 참조로 들고 나온다. import 후
#    finally 에서 schemas/routers/services 항목을 이전 상태로 되돌려, 이후
#    다른 테스트가 이 stub 을 재사용하지 못하게 한다(pytest isolation 계약).
_MODULE_NAMES = (
    "schemas",
    "schemas.document_engine",
    "routers",
    "routers.auth",
    "routers.document_engine_api",
    "services.document_engine_svc",
)
_MISSING = object()
_saved = {name: sys.modules.get(name, _MISSING) for name in _MODULE_NAMES}

try:
    # schemas.document_engine stub (StatusChangeIn 등)
    _schemas_pkg = types.ModuleType("schemas")
    _schemas_doc = types.ModuleType("schemas.document_engine")
    for _n in ("DocumentCreateIn", "DocumentUpdateIn", "StatusChangeIn",
               "EvidenceLinkIn", "GenerateDocumentIn"):
        setattr(_schemas_doc, _n, _Model)
    _schemas_pkg.document_engine = _schemas_doc
    sys.modules["schemas"] = _schemas_pkg
    sys.modules["schemas.document_engine"] = _schemas_doc

    # routers.auth.get_current_user stub
    _routers_pkg = types.ModuleType("routers")
    _routers_pkg.__path__ = [str(ROOT / "routers")]
    sys.modules["routers"] = _routers_pkg
    _auth = types.ModuleType("routers.auth")
    _auth.get_current_user = lambda: {"id": USER_ID}
    sys.modules["routers.auth"] = _auth

    # services.document_engine_svc stub (change_status 관찰)
    _svc = types.ModuleType("services.document_engine_svc")
    _svc.change_status = _change_status
    _svc._approval = lambda *a, **k: None
    _svc._audit = lambda *a, **k: None
    sys.modules["services.document_engine_svc"] = _svc

    # 대상 라우터 재 import (stub 적용 상태). 캐시본 있으면 제거 후 fresh import.
    sys.modules.pop("routers.document_engine_api", None)
    import routers.document_engine_api as api
    from fastapi import HTTPException

    api.confirm_document_atomic = _fake_confirm  # 지역 module object 만 수정

finally:
    # 전역 import 상태 원복 — 이후 테스트가 stub 을 재사용하지 못하게 한다.
    for _name, _prev in _saved.items():
        if _prev is _MISSING:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev


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


# ── R6: 격리 계약 — import 이후 stub 이 sys.modules 에 전역 잔류하지 않는다 ──
def test_R6_no_global_sys_modules_contamination():
    # services.document_engine_svc 가 이 테스트의 stub(_change_status 보유)으로
    # 잔류하면 안 된다. 원래 없었으면 없어야 하고, 있었으면 원본이어야 한다.
    svc = sys.modules.get("services.document_engine_svc", _MISSING)
    if svc is not _MISSING:
        assert getattr(svc, "change_status", None) is not _change_status
    # schemas / routers.auth 도 이 파일 stub 으로 남지 않아야 한다.
    sch = sys.modules.get("schemas", _MISSING)
    if sch is not _MISSING:
        assert getattr(sch, "document_engine", None) is not _schemas_doc
    auth = sys.modules.get("routers.auth", _MISSING)
    if auth is not _MISSING:
        assert getattr(auth, "get_current_user", None) is not _auth.get_current_user
    # 그러나 지역 api 객체는 여전히 살아 있어 테스트가 동작한다.
    assert hasattr(api, "change_status")
