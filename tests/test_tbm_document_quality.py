"""WO-AUTO-REUSE-G4-TBM-DOCUMENT-QUALITY-CORR-001

T1-T14: TBM Fetcher 수정 + Template 정합성 + 서명 증적 분리.
기존 82개 회귀는 별도 실행.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services.document_engine.fetchers.tbm_fetcher as TF  # noqa: E402
import services.document_engine.renderer as R  # noqa: E402


# ── Fake infrastructure ──────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTbmQuery:
    """지원: select / eq / gte / lte / order / limit / execute."""

    def __init__(self, data):
        self._data = list(data)
        self._eq: dict = {}

    def select(self, _): return self
    def limit(self, _): return self
    def order(self, *a, **kw): return self
    def gte(self, col, val): return self
    def lte(self, col, val): return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def execute(self):
        data = self._data
        for col, val in self._eq.items():
            data = [r for r in data if r.get(col) == val]
        return _FakeResult(data)


class _FakeSBTbm:
    """tbm_meetings, tbm_attendees, factories, companies 를 serves."""

    def __init__(self, meetings=None, attendees=None, factories=None, companies=None):
        self._tables = {
            "tbm_meetings": meetings or [],
            "tbm_attendees": attendees or [],
            "factories": factories or [],
            "companies": companies or [],
        }

    def table(self, name):
        if name in self._tables:
            return _FakeTbmQuery(self._tables[name])
        raise AssertionError(f"unexpected table: {name!r}")


class _PatchTbm:
    def __init__(self, sb):
        self._sb = sb
        self._orig = None

    def __enter__(self):
        self._orig = TF.get_supabase
        TF.get_supabase = lambda: self._sb
        return self

    def __exit__(self, *a):
        TF.get_supabase = self._orig
        return False


def _meeting(**over):
    m = {
        "id": "mtg-1",
        "factory_id": "fac-1",
        "work_date": "2026-08-11",
        "work_location": "전 공정",
        "conductor_name": "이재성",
        "work_description": "금일 작업 위험요인 공유",
        "attendee_count": None,
        "meeting_date": None,
        "risk_items": [],
        "safety_items": [],
        "work_type": None,
    }
    m.update(over)
    return m


def _attendee(**over):
    a = {
        "meeting_id": "mtg-1",
        "name": "홍길동",
        "job_type": "용접공",
        "subcontractor_name": "",
        "signature_url": None,
        "signed_at_final": None,
        "signed_at": None,
        "sign_status": "UNSIGNED",
        "issue_flag": None,
        "issue_note": "",
    }
    a.update(over)
    return a


def _factory(**over):
    f = {
        "id": "fac-1",
        "name": "데모정밀 남동공장",
        "site_address": "인천광역시 남동구 남동서로 123",
        "manager_name": "이재성",
        "company_id": "co-1",
    }
    f.update(over)
    return f


def _company(**over):
    c = {
        "id": "co-1",
        "name": "데모 제조 (산업)",
        "logo_url": None,
    }
    c.update(over)
    return c


def _fetch(params=None, meetings=None, attendees=None, factories=None, companies=None):
    sb = _FakeSBTbm(
        meetings=meetings if meetings is not None else [_meeting()],
        attendees=attendees if attendees is not None else [],
        factories=factories if factories is not None else [_factory()],
        companies=companies if companies is not None else [_company()],
    )
    fetcher = TF.TbmFetcher.__new__(TF.TbmFetcher)
    with _PatchTbm(sb):
        return asyncio.run(fetcher.fetch(params or {"meeting_id": "mtg-1"}))


# ── T1-T14 ───────────────────────────────────────────────────────────────────

def test_T1_meeting_id_only_factory_metadata_populated():
    """CORR-A: meeting_id만으로 factory_name 조회 성공."""
    out = _fetch(params={"meeting_id": "mtg-1"})
    assert out["factory_name"] == "데모정밀 남동공장"


def test_T2_company_name_populated():
    """CORR-A: company_name 필드 채워짐."""
    out = _fetch()
    assert out["company_name"] == "데모 제조 (산업)"


def test_T3_factory_address_populated():
    """CORR-B: factory_address(site_address) 필드 채워짐."""
    out = _fetch()
    assert out["factory_address"] == "인천광역시 남동구 남동서로 123"


def test_T4_factory_id_mismatch_raises():
    """CORR-A: params.factory_id != meeting.factory_id → ValueError."""
    try:
        _fetch(params={"meeting_id": "mtg-1", "factory_id": "fac-OTHER"})
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "factory_id" in str(e).lower() or "fac-OTHER" in str(e)


def test_T5_manager_name_forwarded():
    """CORR-A: manager_name 필드 채워짐."""
    out = _fetch()
    assert out["manager_name"] == "이재성"


def test_T6_signed_at_null_sign_status_signed_no_false_evidence():
    """CORR-C: signed_at=NULL + sign_status=SIGNED → SIGNED_STATUS_ONLY (완료 오표시 금지)."""
    att = _attendee(sign_status="SIGNED", signed_at=None, signed_at_final=None, signature_url=None)
    out = _fetch(attendees=[att])
    a = out["attendees"][0]
    assert a["sign_display"] == "SIGNED_STATUS_ONLY"
    assert a["signature_url"] is None


def test_T7_signature_url_present_returns_signed_with_evidence():
    """CORR-C: signature_url 있으면 SIGNED_WITH_EVIDENCE."""
    att = _attendee(signature_url="https://example.com/sig.png", sign_status="SIGNED")
    out = _fetch(attendees=[att])
    assert out["attendees"][0]["sign_display"] == "SIGNED_WITH_EVIDENCE"


def test_T8_unsigned_status_returns_unsigned():
    """CORR-C: sign_status=UNSIGNED → UNSIGNED."""
    att = _attendee(sign_status="UNSIGNED", signature_url=None)
    out = _fetch(attendees=[att])
    assert out["attendees"][0]["sign_display"] == "UNSIGNED"


def test_T9_attendee_count_mismatch_detected():
    """CORR-D: attendee_count_recorded=20, rows=2 → mismatch=True."""
    m = _meeting(attendee_count=20)
    atts = [_attendee(name="A"), _attendee(name="B")]
    out = _fetch(meetings=[m], attendees=atts)
    assert out["attendee_count_recorded"] == 20
    assert out["attendee_count_registered"] == 2
    assert out["attendee_count_mismatch"] is True


def test_T10_empty_safety_items_risk_countermeasure_none():
    """CORR-E: risk_items 문자열 배열 → countermeasure=None; safety_items=[] 무관."""
    m = _meeting(risk_items=["협착", "화상"], safety_items=[])
    out = _fetch(meetings=[m])
    for item in out["risk_items"]:
        assert item["countermeasure"] is None
    assert out["safety_items"] == []


def test_T11_missing_issue_flag_not_rendered_as_normal():
    """CORR-F: issue_flag 없으면 None 유지 — '정상' 단정 금지."""
    att = _attendee(issue_flag=None)
    out = _fetch(attendees=[att])
    a = out["attendees"][0]
    assert a["issue_flag"] is None
    # 렌더링 확인: "정상" 배지가 아니라 "확인 정보 없음" 이어야 한다
    html = asyncio.run(R.render_document_html(
        "DOC-OSH-056",
        {"attendees": [a], "risk_items": [], "empty_rows": [],
         "attendee_count_registered": 1, "attendee_count_mismatch": False,
         "has_issue": None},
    ))
    assert "확인 정보 없음" in html
    # "정상" 배지 b-g 클래스가 없어야 함
    assert 'class="b b-g"' not in html


def test_T12_preview_contract_company_and_factory_present():
    """CORR-A/B: Preview 렌더 시 company_name, factory_name, factory_address 포함."""
    out = _fetch()
    html = asyncio.run(R.render_document_html("DOC-OSH-056", out))
    assert "데모 제조 (산업)" in html
    assert "데모정밀 남동공장" in html
    assert "인천광역시" in html


def test_T13_sign_status_only_badge_text_not_완료():
    """CORR-C: SIGNED_STATUS_ONLY → '완료' 단독 표시 금지, 증적 미확인 표시."""
    att = _attendee(sign_status="SIGNED", signature_url=None, signed_at=None)
    out = _fetch(attendees=[att])
    html = asyncio.run(R.render_document_html(
        "DOC-OSH-056",
        {"attendees": out["attendees"], "risk_items": [], "empty_rows": [],
         "attendee_count_registered": 1, "attendee_count_mismatch": False,
         "has_issue": None},
    ))
    # "완료" 단독 텍스트가 서명란에 없어야 함 (이전 버그 재현 방지)
    assert ">완료<" not in html
    # 증적 미확인 표시가 있어야 함
    assert "증적미확인" in html or "증적 미확인" in html


def test_T14_factory_id_params_none_uses_meeting_factory_id():
    """CORR-A: params.factory_id 없을 때 meeting.factory_id 로 factory 조회."""
    # fac-2 로 연결된 meeting, fac-2 factory 제공
    m = _meeting(factory_id="fac-2")
    f = _factory(id="fac-2", name="다른공장", company_id="co-2")
    c = _company(id="co-2", name="다른회사")
    out = _fetch(params={"meeting_id": "mtg-1"}, meetings=[m], factories=[f], companies=[c])
    assert out["factory_name"] == "다른공장"
    assert out["company_name"] == "다른회사"


# ── C2-D: CORR-002 추가 테스트 ────────────────────────────────────────────────

def test_C2D1_partial_confirmed_does_not_produce_all_normal():
    """C2-A: 1명 False + 9명 None → has_issue=None (전원 정상 표시 금지)."""
    atts = [_attendee(issue_flag=False)] + [_attendee(issue_flag=None) for _ in range(9)]
    out = _fetch(attendees=atts)
    assert out["has_issue"] is None


def test_C2D2_all_explicit_false_produces_has_issue_false():
    """C2-A: 전원 issue_flag=False → has_issue=False (정상 확인)."""
    atts = [_attendee(issue_flag=False) for _ in range(3)]
    out = _fetch(attendees=atts)
    assert out["has_issue"] is False


def test_C2D3_one_true_rest_none_has_issue_true():
    """C2-A: 1명 True + 나머지 None → has_issue=True."""
    atts = [_attendee(issue_flag=True)] + [_attendee(issue_flag=None) for _ in range(4)]
    out = _fetch(attendees=atts)
    assert out["has_issue"] is True


def test_C2D4_no_attendees_has_issue_none():
    """C2-A: 참석자 0명 → has_issue=None (전원 정상 표시 금지)."""
    out = _fetch(attendees=[])
    assert out["has_issue"] is None


def test_C2D5_template_label_is_meeting_time_not_work_time():
    """C2-B: 템플릿 레이블이 '회의시각' (작업시간 아님)."""
    src = (R.TEMPLATE_DIR / "DOC-OSH-056.html").read_text(encoding="utf-8")
    assert "회의시각" in src
    assert "<th>작업시간</th>" not in src


def test_C2D6_unsigned_with_signature_url_returns_unknown():
    """C2-C: UNSIGNED + signature_url 존재 → 상태 충돌 UNKNOWN."""
    disp = TF._attendee_sign_display({
        "sign_status": "UNSIGNED",
        "signature_url": "https://example.com/sig.png",
    })
    assert disp == "UNKNOWN"


def test_C2D7_signed_with_signature_url_normal_path():
    """C2-C: SIGNED + signature_url → SIGNED_WITH_EVIDENCE (정상 경로 유지)."""
    disp = TF._attendee_sign_display({
        "sign_status": "SIGNED",
        "signature_url": "https://example.com/sig.png",
    })
    assert disp == "SIGNED_WITH_EVIDENCE"


def test_C2D8_signed_no_url_status_only():
    """C2-C: SIGNED + signature_url 없음 → SIGNED_STATUS_ONLY."""
    disp = TF._attendee_sign_display({
        "sign_status": "SIGNED",
        "signature_url": None,
    })
    assert disp == "SIGNED_STATUS_ONLY"


# ── C2-D CORR-003: 인원 불일치 + 전체 정상 문구 정합성 ───────────────────────────

def _render_attendee_status(attendees, attendee_count_recorded, attendee_count_registered):
    """has_issue 계산 후 template 렌더링."""
    any_true = any(a.get("issue_flag") is True for a in attendees)
    all_false = len(attendees) > 0 and all(a.get("issue_flag") is False for a in attendees)
    has_issue = True if any_true else (False if all_false else None)
    mismatch = attendee_count_recorded != attendee_count_registered
    html = asyncio.run(R.render_document_html(
        "DOC-OSH-056",
        {"attendees": attendees, "risk_items": [], "empty_rows": [],
         "attendee_count_registered": attendee_count_registered,
         "attendee_count_recorded": attendee_count_recorded,
         "attendee_count_mismatch": mismatch,
         "has_issue": has_issue},
    ))
    return html


def test_C3A_mismatch_20_vs_10_all_false_no_all_normal_message():
    """CORR-003: 기록 20명/등록 10명 전원 False → 전원 정상 문구 미출력."""
    atts = [{"name": f"P{i}", "issue_flag": False, "sign_display": "UNSIGNED",
             "job_type": "-", "subcontractor_name": "", "signature_url": None,
             "issue_note": ""} for i in range(10)]
    html = _render_attendee_status(atts, attendee_count_recorded=20, attendee_count_registered=10)
    assert "전원 보호구 착용 확인" not in html


def test_C3B_no_mismatch_10_vs_10_all_false_shows_normal_message():
    """CORR-003: 기록 10명/등록 10명 전원 False → 전원 정상 문구 출력."""
    atts = [{"name": f"P{i}", "issue_flag": False, "sign_display": "UNSIGNED",
             "job_type": "-", "subcontractor_name": "", "signature_url": None,
             "issue_note": ""} for i in range(10)]
    html = _render_attendee_status(atts, attendee_count_recorded=10, attendee_count_registered=10)
    assert "전원 보호구 착용 확인" in html


def test_C3C_mismatch_with_true_flag_no_all_normal_message():
    """CORR-003: 기록 20명/등록 10명 중 1명 True → 전원 정상 문구 미출력."""
    atts = [{"name": "이상자", "issue_flag": True, "sign_display": "UNSIGNED",
             "job_type": "-", "subcontractor_name": "", "signature_url": None,
             "issue_note": ""}] + [
            {"name": f"P{i}", "issue_flag": False, "sign_display": "UNSIGNED",
             "job_type": "-", "subcontractor_name": "", "signature_url": None,
             "issue_note": ""} for i in range(9)]
    html = _render_attendee_status(atts, attendee_count_recorded=20, attendee_count_registered=10)
    assert "전원 보호구 착용 확인" not in html


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
