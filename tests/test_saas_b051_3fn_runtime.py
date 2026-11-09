"""
WO-TAI-QA-COVERAGE-BULK-051 — SAAS 3건 런타임 HTTP 검증
소스 계약 검증 완료 후 Owner 독립검증 요청에 따라 FastAPI TestClient로 기능 실행 확인.

TC-EDU-001: P2-SAAS-EDU-FNC-001 — GET /education/company-settings → 200 + 목록
TC-EDU-002: P2-SAAS-EDU-FNC-001 — PUT /education/company-settings/{id} → 200 + 저장
TC-CON-001: P2-SAAS-CON-FNC-001 — POST /sites/{id}/diagnose → 200 + 진단 결과
TC-RISK-001: P2-SAAS-RISK-FNC-001 — POST /risk-assessments/{id}/complete → 200 + 완료

운영 안전:
  PRODUCTION_API_HITS=0 / REAL_DB_READS=0 / REAL_DB_WRITES=0
  get_supabase 패치 or dependency_overrides로 실제 Supabase 연결 없음
  run_diagnose_site, _readiness_of 패치로 외부 호출 차단
"""
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── 공용 _SBMock ─────────────────────────────────────────────────────────────

class _QM:
    """경량 Supabase 쿼리 체인 모의 — SAAS 3건 공용."""

    def __init__(self, store: dict, tbl: str):
        self._store = store
        self._tbl = tbl
        self._single = False
        self._payload = None
        self._filters: list = []

    def select(self, *a, **k): return self
    def insert(self, row): self._payload = row; return self
    def update(self, row): self._payload = row; return self
    def upsert(self, row, **k): self._payload = row; return self
    def delete(self): self._payload = "__delete__"; return self
    def eq(self, col, val): self._filters.append((col, val)); return self
    def neq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def single(self): self._single = True; return self

    def execute(self):
        rows = list(self._store.get(self._tbl, []))
        for col, val in self._filters:
            rows = [r for r in rows if str(r.get(col, "")) == str(val)]
        r = MagicMock()
        if self._payload == "__delete__":
            r.data = []
        elif self._payload is not None:
            if isinstance(self._payload, dict):
                r.data = [{**self._payload}]
            else:
                r.data = list(self._payload)
        elif self._single:
            r.data = rows[0] if rows else None
        else:
            r.data = rows
        r.count = len(rows)
        return r


class _SBMock:
    def __init__(self, store: dict):
        self._store = store

    def table(self, tbl: str) -> _QM:
        return _QM(self._store, tbl)


def _sb(store: dict | None = None) -> _SBMock:
    return _SBMock(store or {})


USER = {"sub": "u1", "company_id": "co1", "role_code": "002"}

# ── TC-EDU-001 / TC-EDU-002: P2-SAAS-EDU-FNC-001 ──────────────────────────

class TestEduCompanySettings:
    """교육 세팅 템플릿 관리 — GET/PUT /education/company-settings."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from routers.education import router as edu_router, get_supabase

        self.sb = _sb({
            "education_master": [
                {"id": 1, "education_code": "EDU001", "is_active": True,
                 "name": "화학물질 안전교육", "source_url": "https://kosha.or.kr/edu/001"},
                {"id": 2, "education_code": "EDU002", "is_active": True,
                 "name": "안전보건관리자 교육", "source_url": ""},
            ],
            "company_education_setting": [
                {"id": "s1", "company_id": "co1", "education_id": 1,
                 "custom_url": "https://tai.example/edu/001", "is_active": True},
            ],
            "role_data_scope": [],  # role_code="002" 없음 → scope="TEAM", non-admin
        })

        from routers.auth import get_current_user
        app = FastAPI()
        app.include_router(edu_router)
        app.dependency_overrides[get_supabase] = lambda: self.sb
        app.dependency_overrides[get_current_user] = lambda: USER
        self.client = TestClient(app)

    def test_TC_EDU_001_get_company_settings_200(self):
        """TC-EDU-001: GET /education/company-settings → 200, 마스터 2건 + 커스텀 URL 병합."""
        resp = self.client.get("/education/company-settings", params={"company_id": "co1"})
        assert resp.status_code == 200, f"EDU-001 GET status={resp.status_code}: {resp.text[:200]}"
        body = resp.json()
        assert body.get("success") is True, f"EDU-001 success 필드 없음: {body}"
        data = body.get("data", [])
        assert isinstance(data, list), "EDU-001 data는 list여야 함"
        assert len(data) == 2, f"EDU-001 마스터 2건 반환 필요, 실제={len(data)}"
        # education_id=1 항목: 커스텀 URL 세팅이 병합되어야 함
        item_edu1 = next((d for d in data if d.get("education_id") == "1"), None)
        assert item_edu1 is not None, "EDU-001 education_id=1 항목 없음"
        assert item_edu1.get("has_custom") is True, "EDU-001 education_id=1에 커스텀 URL 없음"
        assert item_edu1.get("effective_url") == "https://tai.example/edu/001", \
            f"EDU-001 effective_url 불일치: {item_edu1.get('effective_url')}"

    def test_TC_EDU_002_put_company_setting_200(self):
        """TC-EDU-002: PUT /education/company-settings/1 → 200, 저장된 custom_url 반환."""
        new_url = "https://tai.example/edu/001-updated"
        payload = {"custom_url": new_url, "custom_url_label": "TAI 맞춤 교육", "is_active": True}
        resp = self.client.put(
            "/education/company-settings/1",
            params={"company_id": "co1"},
            json=payload,
        )
        assert resp.status_code == 200, f"EDU-002 PUT status={resp.status_code}: {resp.text[:200]}"
        body = resp.json()
        assert body.get("success") is True, f"EDU-002 success 필드 없음: {body}"
        saved = body.get("data", {})
        assert saved.get("custom_url") == new_url, \
            f"EDU-002 저장된 custom_url 불일치: {saved.get('custom_url')}"


# ── TC-CON-001: P2-SAAS-CON-FNC-001 ─────────────────────────────────────────

SITE_ID = str(uuid.uuid4())


class TestConstructionDiagnose:
    """공정 추출 정상 처리 — POST /sites/{id}/diagnose."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from routers.construction_sites_router import router as con_router
        from routers.auth import get_current_user

        self.sb = _sb({
            "construction_sites": [
                {"id": SITE_ID, "company_id": "co1", "is_active": True,
                 "site_name": "1공장 신축"},
            ],
            "role_data_scope": [],
        })

        # run_diagnose_site: (supabase, site_id, factory_fn, diagnosis_fn) → (site, factory_id, diag)
        self._diag_result = {
            "applicable_count": 3,
            "diagnosis_id": "diag-001",
            "by_obligation_type": {"A": 2, "B": 1},
            "applicable_rules": ["RULE-001"],
        }

        app = FastAPI()
        app.include_router(con_router)
        app.dependency_overrides[get_current_user] = lambda: USER

        with patch("routers.construction_sites_router.get_supabase",
                   return_value=self.sb) as _p_sb, \
             patch("routers.construction_sites_router.run_diagnose_site",
                   return_value=({"id": SITE_ID}, "factory-001", self._diag_result)):
            self.client = TestClient(app)
            yield

    def test_TC_CON_001_diagnose_200(self):
        """TC-CON-001: POST /sites/{id}/diagnose → 200, 진단 결과(applicable_rules·diagnosis_id) 반환."""
        with patch("routers.construction_sites_router.get_supabase",
                   return_value=self.sb), \
             patch("routers.construction_sites_router.run_diagnose_site",
                   return_value=({"id": SITE_ID}, "factory-001", self._diag_result)):
            resp = self.client.post(f"/sites/{SITE_ID}/diagnose")
        assert resp.status_code == 200, f"CON-001 status={resp.status_code}: {resp.text[:200]}"
        body = resp.json()
        assert body.get("status") == "success", f"CON-001 status 필드: {body}"
        data = body.get("data", {})
        assert data.get("site_id") == SITE_ID, "CON-001 site_id 불일치"
        assert data.get("factory_id") == "factory-001", "CON-001 factory_id 없음"
        assert data.get("applicable_rules") == 3, \
            f"CON-001 applicable_rules 수 불일치: {data.get('applicable_rules')}"
        assert data.get("diagnosis_id") == "diag-001", \
            f"CON-001 diagnosis_id 없음: {data.get('diagnosis_id')}"
        assert data.get("by_obligation_type") == {"A": 2, "B": 1}, \
            f"CON-001 by_obligation_type 불일치: {data.get('by_obligation_type')}"


# ── TC-RISK-001: P2-SAAS-RISK-FNC-001 ───────────────────────────────────────

RA_ID = "ra-" + str(uuid.uuid4())


class TestRiskAssessmentComplete:
    """위험도 리포트 발행 — POST /risk-assessments/{id}/complete."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        import routers.risk_assessments as ra_mod
        from routers.auth import get_current_user

        completed_row = {
            "id": RA_ID,
            "company_id": "co1",
            "status_code": "COMPLETED",
            "completed_at": "2026-11-09T10:00:00+09:00",
            "retention_years": 3,
            "retention_until": "2029-11-09",
            "updated_at": "2026-11-09T10:00:00+09:00",
        }

        self.sb = _sb({
            "risk_assessments": [
                {"id": RA_ID, "company_id": "co1", "status_code": "IN_PROGRESS"},
            ],
            "role_data_scope": [],
        })

        # _SBMock.update 반환 → completed_row
        class _SBComplete(_SBMock):
            def table(self, tbl):
                q = super().table(tbl)
                if tbl == "risk_assessments":
                    # update().eq().execute() → completed_row
                    orig_execute = q.execute

                    def _patched_execute():
                        r = orig_execute()
                        if q._payload not in (None, "__delete__"):
                            r.data = [completed_row]
                        return r
                    q.execute = _patched_execute
                return q

        sb_complete = _SBComplete(self.sb._store)

        app = FastAPI()
        app.include_router(ra_mod.router)
        app.dependency_overrides[get_current_user] = lambda: USER

        with patch.object(ra_mod, "get_supabase", return_value=sb_complete), \
             patch.object(ra_mod, "_readiness_of", return_value=None):
            self.client = TestClient(app)
            yield

    def test_TC_RISK_001_complete_200(self):
        """TC-RISK-001: POST /risk-assessments/{id}/complete → 200, COMPLETED + 보존만료일 반환."""
        # fixture patch 활성화 중 — 추가 patch 불필요
        resp = self.client.post(f"/risk-assessments/{RA_ID}/complete")
        assert resp.status_code == 200, f"RISK-001 status={resp.status_code}: {resp.text[:200]}"
        body = resp.json()
        assert body.get("status") == "success", f"RISK-001 status 필드: {body}"
        assert body.get("message") == "완료 처리되었습니다.", f"RISK-001 message 없음"
        data = body.get("data", {})
        assert data.get("status_code") == "COMPLETED", \
            f"RISK-001 COMPLETED 미반환: {data}"
        assert data.get("retention_years") == 3, \
            f"RISK-001 retention_years 없음: {data.get('retention_years')}"
        assert data.get("retention_until") == "2029-11-09", \
            f"RISK-001 retention_until 없음: {data.get('retention_until')}"
