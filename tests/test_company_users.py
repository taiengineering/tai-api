"""WP-A · /me/company/* + /user-invites/* 라우터 · guard · 초대 단위테스트.

WO-SAFE-COMPANY-ACCESS-001. FakeSupabase 격리(실 DB/네트워크 0).
매트릭스 (B/C/D/E 표본) :
  B 가드 : COMPANY scope + worker-list CRUD (LIST/INVITE/APPROVE/ROLE/STATUS/CANCEL)
  C cross-company : 타사 리소스 404 · body 에 company_id 불수용 계약
  D invite : SHA-256 token_hash · raw token DB 미저장 · PENDING result · dup 409 ·
              expired 410 · accept invite-frozen(email/company/role) · approve→ACTIVE
  E role : assignable filter · own-company factory/team · last admin 409
  INV : 소스 grep — _require_admin 미사용 · unlimited (max_user_count 등) 신규코드 0
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.company_users as cu
from services import company_user_svc as svc

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


# ── FakeSupabase (in-memory) ────────────────────────────────────────
class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []
        self._cols = "*"; self._count_exact = False
        self._range = None; self._order = None; self._limit = None

    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"
        if k.get("count") == "exact": self._count_exact = True
        return self
    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def neq(self, c, v): self._filters.append(("neq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def is_(self, c, v): self._filters.append(("is", c, v)); return self
    def ilike(self, c, pattern): self._filters.append(("ilike", c, pattern)); return self
    def limit(self, n): self._limit = n; return self
    def order(self, col, *, desc=False, **k): self._order = (col, desc); return self
    def range(self, s, e): self._range = (s, e); return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and str(rv) != str(v): return False
            if op == "neq" and str(rv) == str(v): return False
            if op == "in" and rv not in v: return False
            if op == "is" and v == "null" and rv is not None: return False
            if op == "ilike":
                # 간단 구현 : %prefix% / prefix% 만 지원
                pat = str(v).lower()
                s = str(rv or "").lower()
                if pat.startswith("%") and pat.endswith("%"):
                    if pat.strip("%") not in s: return False
                elif pat.endswith("%"):
                    if not s.startswith(pat.rstrip("%")): return False
                elif pat.startswith("%"):
                    if not s.endswith(pat.lstrip("%")): return False
                else:
                    if s != pat: return False
        return True

    def _project(self, row):
        if not self._cols or self._cols == "*": return dict(row)
        keys = [c.strip() for c in self._cols.split(",") if c.strip()]
        return {k: row.get(k) for k in keys}

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            matched = [r for r in rows if self._match(r)]
            total = len(matched)
            if self._order:
                col, desc = self._order
                matched = sorted(matched, key=lambda r: (r.get(col) or ""), reverse=desc)
            if self._range is not None:
                s, e = self._range; matched = matched[s:e + 1]
            elif self._limit is not None:
                matched = matched[:self._limit]
            return _Result([self._project(r) for r in matched],
                           count=total if self._count_exact else None)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                rows.append(it); out.append(dict(it))
            return _Result(out)
        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched: r.update(self._payload)
            return _Result([dict(r) for r in matched])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []
    def table(self, name): return _Query(self.store, name, self.log)


# ── Fixtures ────────────────────────────────────────────────────────
def _base_store(users=None, companies=None, invites=None,
                factories=None, teams=None, roles=None,
                role_data_scope=None, role_menu_permissions=None,
                subscriptions=None, contracts=None,
                inicis_auth_requests=None):
    default_roles = [
        {"role_code": "001", "role_name": "슈퍼관리자", "is_active": True},
        {"role_code": "002", "role_name": "회사관리자", "is_active": True},
        {"role_code": "010", "role_name": "대표이사", "is_active": True},
        {"role_code": "011", "role_name": "안전보건관리책임자", "is_active": True},
        {"role_code": "020", "role_name": "일반사용자", "is_active": True},
        {"role_code": "030", "role_name": "관리자직원", "is_active": True},
        {"role_code": "031", "role_name": "플랫폼운영", "is_active": True},
    ]
    default_scopes = [
        {"role_code": "001", "scope_type": "ALL"},
        {"role_code": "002", "scope_type": "COMPANY"},
        {"role_code": "010", "scope_type": "COMPANY"},
        {"role_code": "011", "scope_type": "COMPANY"},
        {"role_code": "020", "scope_type": "FACTORY"},
        {"role_code": "030", "scope_type": "FACTORY"},
        {"role_code": "031", "scope_type": "PLATFORM"},
    ]
    default_menu_perms = [
        # worker-list : 002/010/011 관리 capability true, 020/030 false
        {"role_code": "002", "menu_code": "worker-list",
         "can_list": True, "can_read": True, "can_create": True,
         "can_update": True, "can_delete": True},
        {"role_code": "010", "menu_code": "worker-list",
         "can_list": True, "can_read": True, "can_create": True,
         "can_update": True, "can_delete": True},
        {"role_code": "011", "menu_code": "worker-list",
         "can_list": True, "can_read": True, "can_create": True,
         "can_update": True, "can_delete": True},
        {"role_code": "020", "menu_code": "worker-list",
         "can_list": True, "can_read": True, "can_create": False,
         "can_update": False, "can_delete": False},
    ]
    default_subs = [
        # C-A 회사 : ACTIVE SaaS subscription
        {"id": "sub-a", "company_id": "C-A", "status": "ACTIVE",
         "product_type": "SAAS", "plan_code": "PRO",
         "start_date": "2026-01-01", "ended_at": None},
    ]
    return {
        "users": list(users or []),
        "companies": list(companies or [{"id": "C-A", "name": "A 주식회사"}]),
        "company_user_invites": list(invites or []),
        "factories": list(factories or []),
        "teams": list(teams or []),
        "roles": list(roles or default_roles),
        "role_data_scope": list(role_data_scope or default_scopes),
        "role_menu_permissions": list(role_menu_permissions or default_menu_perms),
        "subscriptions": list(subscriptions or default_subs),
        "contracts": list(contracts or []),
        # PATCH-1 : Inicis 실제 계약(register 와 동일) — 초대 accept 는 inicis_auth_requests 를 참조.
        "inicis_auth_requests": list(inicis_auth_requests or []),
    }


# PATCH-1 : 유효한 Inicis 검증 fixture row 생성 헬퍼.
def _inicis_success(mtx_id, user_ci="CI-USER-XYZ-01",
                    name="홍길동", phone="01012345678", birth="1990-01-01"):
    return {"mtx_id": mtx_id, "status": "SUCCESS",
            "user_ci": user_ci, "user_name": name,
            "user_phone": phone, "user_birthday": birth}


def _admin_user(uid="U-ADMIN", role="002", cid="C-A"):
    return {"id": uid, "email": "admin@a.co.kr", "name": "관리자",
            "role_code": role, "company_id": cid,
            "status_code": "ACTIVE", "is_active": True}


def _factory_scope_user(uid="U-F", cid="C-A"):
    return {"id": uid, "email": "f@a.co.kr", "name": "시설관리자",
            "role_code": "020", "company_id": cid,
            "status_code": "ACTIVE", "is_active": True}


def _client(current_user, store):
    app = FastAPI()
    app.include_router(cu.router)
    app.dependency_overrides[cu.get_current_user] = lambda: current_user
    fake = FakeSupabase(store)
    cu.get_supabase = lambda: fake
    # svc 내부에서도 helper 호출 시 같은 fake 를 사용하도록 raise 방지 — endpoint 는 sb 인자로 fake 를 넘김
    c = TestClient(app)
    c._fake = fake
    return c


# ════════════════════════════════════════════════════════════════════
# B : guard capability (COMPANY scope + worker-list CRUD)
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_B01_admin_002_can_list():
    c = _client(_admin_user(role="002"), _base_store())
    assert c.get("/me/company/users").status_code == 200


@requires_client
def test_B02_admin_010_can_list():
    """대표이사(010) capability 유지 — 002 하드코딩 아니라는 근거."""
    c = _client(_admin_user(uid="U-010", role="010"), _base_store())
    assert c.get("/me/company/users").status_code == 200


@requires_client
def test_B03_admin_011_can_list():
    """안전보건관리책임자(011) capability 유지."""
    c = _client(_admin_user(uid="U-011", role="011"), _base_store())
    assert c.get("/me/company/users").status_code == 200


@requires_client
def test_B04_factory_scope_denied_403():
    """FACTORY scope 는 회사 관리 capability 부재 → 403."""
    c = _client(_factory_scope_user(), _base_store())
    r = c.get("/me/company/users")
    assert r.status_code == 403


@requires_client
def test_B05_no_company_denied_403():
    admin = _admin_user(cid=None)
    c = _client(admin, _base_store())
    r = c.get("/me/company/users")
    assert r.status_code == 403


@requires_client
def test_B06_pending_denied_by_guard():
    """PENDING (get_current_user 가 이미 차단하지만 guard 방어도 유효)."""
    admin = _admin_user()
    admin["status_code"] = "PENDING"
    c = _client(admin, _base_store())
    r = c.get("/me/company/users")
    assert r.status_code == 403


@requires_client
def test_B07_invite_requires_active_saas():
    """C-B 회사엔 ACTIVE SaaS 없음 → INVITE 시 403 SAAS_ENTITLEMENT_REQUIRED."""
    admin = _admin_user(uid="U-B-ADM", cid="C-B")
    store = _base_store(companies=[{"id": "C-B", "name": "B 주식회사"}])
    # C-B 는 subscriptions 에 없음 → entitlement 없음
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "x@b.co.kr", "role_code": "020"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_B08_platform_role_would_be_blocked():
    """role 031(PLATFORM) 은 COMPANY scope 아님 → 403."""
    admin = _admin_user(uid="U-P", role="031")
    c = _client(admin, _base_store())
    r = c.get("/me/company/users")
    assert r.status_code == 403


# ════════════════════════════════════════════════════════════════════
# C : cross-company & body override
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_C01_body_has_no_company_id_in_invite_schema():
    """InviteCreateBody 스키마에 company_id 필드 부재 (Pydantic model_fields)."""
    fields = set(cu.InviteCreateBody.model_fields.keys())
    assert "company_id" not in fields


@requires_client
def test_C02_body_override_company_id_ignored_in_invite():
    """Pydantic extra=ignore : 추가 필드는 폐기 · 서버는 current.company_id 사용."""
    admin = _admin_user()
    store = _base_store()
    c = _client(admin, store)
    r = c.post("/me/company/user-invites", json={
        # PATCH-3 : COMPANY scope role (010) 사용 · FACTORY_REQUIRED 회피
        "email": "n@a.co.kr", "role_code": "010",
        "company_id": "C-OTHER",              # 무시되어야 함
    })
    assert r.status_code == 200
    assert store["company_user_invites"][0]["company_id"] == "C-A"


@requires_client
def test_C03_cross_company_user_approve_returns_404():
    """다른 회사 사용자 approve 시도 → 404 (존재 은닉)."""
    admin = _admin_user()
    store = _base_store(users=[
        {"id": "U-OTHER", "email": "o@x.co.kr", "name": "O",
         "role_code": "020", "company_id": "C-B",           # 타사
         "status_code": "PENDING", "is_active": False},
    ])
    c = _client(admin, store)
    r = c.post("/me/company/users/U-OTHER/approve")
    assert r.status_code == 404


@requires_client
def test_C04_cross_company_user_role_patch_returns_404():
    admin = _admin_user()
    store = _base_store(users=[
        {"id": "U-OTHER2", "email": "o2@x.co.kr", "name": "O2",
         "role_code": "020", "company_id": "C-B",
         "status_code": "ACTIVE", "is_active": True},
    ])
    c = _client(admin, store)
    r = c.patch("/me/company/users/U-OTHER2/role", json={"role_code": "030"})
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# D : invite lifecycle
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_D01_invite_stores_token_hash_only_not_raw():
    admin = _admin_user()
    store = _base_store()
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "new@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    assert r.status_code == 200
    row = store["company_user_invites"][0]
    # raw token 은 응답에는 있으나 저장에는 없다.
    raw = r.json()["data"]["token"]
    assert row.get("token_hash") == svc.hash_token(raw)
    assert "token" not in row and raw not in str(row)


def test_D02_hash_is_sha256_hex():
    import hashlib
    raw = "abcdef123456"
    assert svc.hash_token(raw) == hashlib.sha256(raw.encode()).hexdigest()


@requires_client
def test_D03_dup_pending_invite_returns_409():
    admin = _admin_user()
    store = _base_store()
    c = _client(admin, store)
    # PATCH-3 : COMPANY scope role
    r1 = c.post("/me/company/user-invites",
                json={"email": "dup@a.co.kr", "role_code": "010"})
    assert r1.status_code == 200
    r2 = c.post("/me/company/user-invites",
                json={"email": "dup@a.co.kr", "role_code": "010"})
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "INVITE_PENDING_EXISTS"


@requires_client
def test_D04_conflict_user_belongs_to_another_company():
    admin = _admin_user()
    store = _base_store(users=[
        {"id": "U-EX", "email": "x@x.co.kr", "company_id": "C-B",
         "role_code": "020", "status_code": "ACTIVE", "is_active": True},
    ])
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "x@x.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "USER_BELONGS_TO_ANOTHER_COMPANY"


@requires_client
def test_D05_accept_uses_invite_email_not_body():
    """PATCH-1 : accept 는 mtx_id 필수 · fixture 에 valid inicis_auth_requests 제공."""
    admin = _admin_user()
    store = _base_store(inicis_auth_requests=[_inicis_success("MTX-D05", user_ci="CI-D05")])
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "signup@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    # accept
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "홍길동", "phone": "010-1234-5678",
                      "password": "pw12345678", "mtx_id": "MTX-D05"})
    assert r2.status_code == 200
    d = r2.json()["data"]
    # email 은 invite 값
    assert d["email"] == "signup@a.co.kr"
    # 결과 PENDING · is_active=false
    assert d["status_code"] == "PENDING"
    assert d["is_active"] is False
    # invite 는 ACCEPTED 로 갱신
    inv = store["company_user_invites"][0]
    assert inv["status"] == "ACCEPTED"


@requires_client
def test_D06_accept_frozen_company_and_role_from_invite():
    admin = _admin_user()
    store = _base_store(inicis_auth_requests=[_inicis_success("MTX-D06", user_ci="CI-D06")])
    c = _client(admin, store)
    # PATCH-3 : COMPANY scope role (010) · invite-frozen 검증은 값 자체가 아닌 "invite 값 보존" 이 요지
    r = c.post("/me/company/user-invites",
               json={"email": "frozen@a.co.kr", "role_code": "010"})
    raw = r.json()["data"]["token"]
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "김프", "phone": "010-2222-3333",
                      "password": "pw1234567", "mtx_id": "MTX-D06"})
    d = r2.json()["data"]
    assert d["company_id"] == "C-A"                                # invite frozen
    assert d["role_code"] == "010"                                 # invite frozen


@requires_client
def test_D07_accept_expired_returns_410():
    admin = _admin_user()
    store = _base_store(inicis_auth_requests=[_inicis_success("MTX-D07", user_ci="CI-D07")])
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "old@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    # 만료 처리
    inv = store["company_user_invites"][0]
    inv["expires_at"] = "2000-01-01T00:00:00+00:00"
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "만료", "phone": "010-9999-9999",
                      "password": "pw12345678", "mtx_id": "MTX-D07"})
    assert r2.status_code == 410
    assert r2.json()["detail"]["code"] == "INVITE_EXPIRED"


@requires_client
def test_D08_accept_cancelled_returns_410():
    admin = _admin_user()
    store = _base_store(inicis_auth_requests=[_inicis_success("MTX-D08", user_ci="CI-D08")])
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "cancel@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    inv_id = store["company_user_invites"][0]["id"]
    c.delete(f"/me/company/user-invites/{inv_id}")
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "취소", "phone": "010-8888-9999",
                      "password": "pw12345678", "mtx_id": "MTX-D08"})
    assert r2.status_code == 410
    assert r2.json()["detail"]["code"] == "INVITE_CANCELLED"


@requires_client
def test_D09_approve_pending_flips_to_active():
    admin = _admin_user()
    store = _base_store(users=[
        {"id": "U-P", "email": "p@a.co.kr", "name": "P",
         "role_code": "020", "company_id": "C-A",
         "status_code": "PENDING", "is_active": False},
    ])
    c = _client(admin, store)
    r = c.post("/me/company/users/U-P/approve")
    assert r.status_code == 200
    saved = [u for u in store["users"] if u["id"] == "U-P"][0]
    assert saved["status_code"] == "ACTIVE"
    assert saved["is_active"] is True


@requires_client
def test_D10_invite_info_public_masked_email():
    admin = _admin_user()
    store = _base_store()
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "aaaa@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    r2 = c.get(f"/user-invites/{raw}/info")
    d = r2.json()["data"]
    assert d["valid"] is True
    assert "@" in d["email_masked"]
    assert d["email_masked"] != "aaaa@a.co.kr"                     # 마스킹 확인
    assert d["company_name"] == "A 주식회사"


@requires_client
def test_D11_invite_info_unknown_token_returns_invalid_not_404():
    admin = _admin_user()
    c = _client(admin, _base_store())
    r = c.get("/user-invites/UNKNOWN_TOKEN_1234/info")
    # 미로그인 접근이라도 존재 은닉 위해 valid:false 반환.
    assert r.status_code == 200
    assert r.json()["data"]["valid"] is False


# ── PATCH-1 : BLOCKER-INICIS · register 계약 정합 ──────────────────
@requires_client
def test_D12_accept_valid_mtx_saves_sha256_identity_ci():
    """valid mtx_id (inicis_auth_requests status=SUCCESS) → identity_ci = sha256(user_ci) 저장."""
    import hashlib
    admin = _admin_user()
    raw_ci = "CI-USER-D12-ABC"
    store = _base_store(inicis_auth_requests=[_inicis_success("MTX-D12", user_ci=raw_ci)])
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "d12@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "이름", "phone": "010-3333-4444",
                      "password": "pw12345678", "mtx_id": "MTX-D12"})
    assert r2.status_code == 200
    # 저장된 실제 user row 확인
    saved = [u for u in store["users"] if u.get("email") == "d12@a.co.kr"][0]
    assert saved["status_code"] == "PENDING"
    assert saved["is_active"] is False
    expected_hash = hashlib.sha256(raw_ci.encode("utf-8")).hexdigest()
    assert saved["identity_ci"] == expected_hash
    # identity_fields 병합 확인 (register 와 동일 필드셋)
    assert saved.get("identity_verified") is True
    assert saved.get("identity_name") == "홍길동"
    assert saved.get("identity_phone") == "01012345678"


@requires_client
def test_D13_accept_ci_already_used_returns_409_no_insert():
    """이미 등록된 identity_ci 가 있으면 409 CI_ALREADY_USED · users insert 0."""
    import hashlib
    admin = _admin_user()
    raw_ci = "CI-USER-D13-XY"
    existing_hash = hashlib.sha256(raw_ci.encode("utf-8")).hexdigest()
    store = _base_store(
        users=[{"id": "U-EX", "email": "ex@a.co.kr", "phone": "01099998888",
                "role_code": "020", "company_id": "C-A",
                "status_code": "ACTIVE", "is_active": True,
                "identity_ci": existing_hash}],
        inicis_auth_requests=[_inicis_success("MTX-D13", user_ci=raw_ci)],
    )
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "d13@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    users_before = len(store["users"])
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "새이름", "phone": "010-5555-6666",
                      "password": "pw12345678", "mtx_id": "MTX-D13"})
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "CI_ALREADY_USED"
    # users insert 발생 안 함
    assert len(store["users"]) == users_before


@requires_client
def test_D14_accept_mtx_status_not_success_returns_400():
    """mtx_id 존재하지만 status != SUCCESS → 400 IDENTITY_VERIFICATION_REQUIRED."""
    admin = _admin_user()
    ir = _inicis_success("MTX-D14", user_ci="CI-D14")
    ir["status"] = "PENDING"                                     # SUCCESS 가 아님
    store = _base_store(inicis_auth_requests=[ir])
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "d14@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "이름", "phone": "010-1111-1111",
                      "password": "pw12345678", "mtx_id": "MTX-D14"})
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "IDENTITY_VERIFICATION_REQUIRED"


@requires_client
def test_D15_accept_without_mtx_id_returns_400():
    """PATCH-1 정책 : 초대 가입에서도 mtx_id 필수 (register 와 동일). 없으면 400."""
    admin = _admin_user()
    store = _base_store()
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "d15@a.co.kr", "role_code": "010"})  # PATCH-3 : COMPANY scope
    raw = r.json()["data"]["token"]
    r2 = c.post(f"/user-invites/{raw}/accept",
                json={"name": "이름", "phone": "010-7777-8888",
                      "password": "pw12345678"})                # mtx_id 미전송
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "IDENTITY_VERIFICATION_REQUIRED"


# ════════════════════════════════════════════════════════════════════
# E : role & last admin
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_E01_user_roles_excludes_platform_and_all():
    admin = _admin_user()
    c = _client(admin, _base_store())
    r = c.get("/me/company/user-roles")
    assert r.status_code == 200
    codes = [it["role_code"] for it in r.json()["data"]["items"]]
    for excluded in ("001", "031", "032", "033"):
        assert excluded not in codes


@requires_client
def test_E02_role_patch_factory_out_of_scope_422():
    """다른 회사 factory_id 지정 시 422 FACTORY_OUT_OF_SCOPE."""
    admin = _admin_user()
    store = _base_store(
        users=[{"id": "U-X", "email": "x@a.co.kr", "name": "X",
                "role_code": "030", "company_id": "C-A",
                "status_code": "ACTIVE", "is_active": True}],
        factories=[{"id": "F-OTHER", "company_id": "C-B"}],
    )
    c = _client(admin, store)
    r = c.patch("/me/company/users/U-X/role",
                json={"role_code": "020", "factory_id": "F-OTHER"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "FACTORY_OUT_OF_SCOPE"


@requires_client
def test_E03_last_company_admin_status_inactive_returns_409():
    """회사에 단독 관리자(002 ACTIVE)를 INACTIVE 로 못 만든다."""
    admin = _admin_user(uid="U-SOLO", role="002", cid="C-A")
    store = _base_store(users=[admin])
    c = _client(admin, store)
    r = c.patch("/me/company/users/U-SOLO/status",
                json={"status_code": "INACTIVE"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LAST_COMPANY_ADMIN"


@requires_client
def test_E04_last_company_admin_role_downgrade_returns_409():
    """단독 관리자를 non-capability role 로 변경 시 409.
    020 은 FACTORY scope 라 body 에 own-company factory_id 를 함께 지정 (다른 검증 통과)."""
    admin = _admin_user(uid="U-SOLO2", role="002", cid="C-A")
    store = _base_store(users=[admin],
                        factories=[{"id": "F-A1", "company_id": "C-A"}])
    c = _client(admin, store)
    r = c.patch("/me/company/users/U-SOLO2/role",
                json={"role_code": "020", "factory_id": "F-A1"})  # 020 = FACTORY · non-capability
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LAST_COMPANY_ADMIN"


@requires_client
def test_E05_status_pending_via_status_endpoint_rejected():
    """PENDING 은 approve endpoint 로만 처리 · status 로 ACTIVE 시도 시 409."""
    admin = _admin_user()
    store = _base_store(users=[
        admin,
        {"id": "U-P2", "email": "p2@a.co.kr", "name": "P2",
         "role_code": "020", "company_id": "C-A",
         "status_code": "PENDING", "is_active": False},
    ])
    c = _client(admin, store)
    r = c.patch("/me/company/users/U-P2/status",
                json={"status_code": "ACTIVE"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "USE_APPROVE_FOR_PENDING"


# ════════════════════════════════════════════════════════════════════
# INV : 소스 grep · unlimited 유지 · _require_admin 미사용
# ════════════════════════════════════════════════════════════════════
def test_INV_STATIC_no_require_admin_in_new_router():
    import inspect
    src = inspect.getsource(cu)
    assert "_require_admin" not in src, \
        "routers/company_users 에 legacy _require_admin 참조가 있으면 안 된다"


def test_INV_STATIC_no_require_admin_in_new_svc():
    import inspect
    src = inspect.getsource(svc)
    assert "_require_admin(" not in src, \
        "services/company_user_svc 에 _require_admin() 호출 참조가 있으면 안 된다"


def test_INV_STATIC_no_unlimited_gate_tokens():
    """신규 코드 unlimited 게이트 금지 (max_user_count / seat_limit / user_gate 등)."""
    import inspect
    for mod in (cu, svc):
        src = inspect.getsource(mod)
        for tok in ("max_user_count", "seat_limit", "user_gate", "seat_gate"):
            assert tok not in src, f"신규 코드에 unlimited 위반 토큰 '{tok}' 발견"


def test_INV_STATIC_uses_new_guard_only():
    import inspect
    src = inspect.getsource(cu)
    assert "_require_company_user_admin" in src, \
        "회사 사용자 관리 라우터가 신규 guard 를 호출해야 한다"
    assert "require_active_company_saas" in src, \
        "라우터가 strict entitlement 헬퍼를 호출해야 한다"


def test_INV_STATIC_PATCH1_uses_correct_inicis_table():
    """PATCH-1 : 잘못된 inicis_verifications 참조 완전 제거, inicis_auth_requests 사용."""
    import inspect
    src = inspect.getsource(cu)
    assert "inicis_verifications" not in src, \
        "PATCH-1: 잘못된 테이블 inicis_verifications 참조가 남아있다"
    assert "inicis_auth_requests" in src, \
        "PATCH-1: register 와 동일한 inicis_auth_requests 테이블을 사용해야 한다"
    # SHA-256 hash 로 identity_ci 산출
    assert "hashlib.sha256" in src or "sha256(" in src, \
        "PATCH-1: identity_ci 는 SHA-256(user_ci) 이어야 한다"


# ═══════════════════════════════════════════════════════════════════
# PATCH-2 : 4 blocker
#   2A public accept · 2B assignable-role · 2C strict entitlement 확장 ·
#   2D bootstrap SaaS predicate + migration invited_by NOT NULL
# ═══════════════════════════════════════════════════════════════════

# ── 2A : POST /user-invites/{token}/accept public allowlist ──────
def test_P2_2A_permission_guard_public_covers_post_accept():
    """permission_guard._PUBLIC 에 POST /user-invites/ 추가되어 미로그인 accept 허용."""
    from services import permission_guard as pg
    # POST accept 는 public
    assert pg.is_public("POST", "/user-invites/abc123/accept") is True
    # GET info 도 여전히 public
    assert pg.is_public("GET", "/user-invites/xyz/info") is True
    # /me/company/* 는 절대 public 아님
    assert pg.is_public("GET", "/me/company/access") is False
    assert pg.is_public("GET", "/me/company/users") is False
    assert pg.is_public("POST", "/me/company/user-invites") is False


# ── 2B : assignable-role 서버 강제 (invite create + role PATCH) ──
@requires_client
def test_P2_2B_invite_create_platform_role_422_not_assignable():
    """platform role (001/031/032/033) 로 초대 → 422 ROLE_NOT_ASSIGNABLE."""
    admin = _admin_user()
    store = _base_store()
    c = _client(admin, store)
    for bad in ("001", "031"):
        r = c.post("/me/company/user-invites",
                   json={"email": f"bad{bad}@a.co.kr", "role_code": bad})
        assert r.status_code == 422, f"role={bad}"
        assert r.json()["detail"]["code"] == "ROLE_NOT_ASSIGNABLE"


@requires_client
def test_P2_2B_invite_create_inactive_role_422():
    """is_active=false role 로 초대 → 422 ROLE_NOT_ASSIGNABLE."""
    admin = _admin_user()
    # 020 role 을 비활성화한 fixture
    roles = [
        {"role_code": "002", "role_name": "회사관리자", "is_active": True},
        {"role_code": "020", "role_name": "일반사용자", "is_active": False},
    ]
    scopes = [
        {"role_code": "002", "scope_type": "COMPANY"},
        {"role_code": "020", "scope_type": "FACTORY"},
    ]
    store = _base_store(roles=roles, role_data_scope=scopes)
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "x@a.co.kr", "role_code": "020"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ROLE_NOT_ASSIGNABLE"


@requires_client
def test_P2_2B_role_patch_platform_role_422_not_assignable():
    """role PATCH 로 001/031 지정 → 422 ROLE_NOT_ASSIGNABLE."""
    admin = _admin_user()
    store = _base_store(users=[
        admin,
        {"id": "U-X", "email": "x@a.co.kr", "name": "X",
         "role_code": "020", "company_id": "C-A",
         "status_code": "ACTIVE", "is_active": True},
    ])
    c = _client(admin, store)
    r = c.patch("/me/company/users/U-X/role",
                json={"role_code": "001"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ROLE_NOT_ASSIGNABLE"


@requires_client
def test_P2_2B_role_patch_valid_role_passes():
    """정상 role (010 COMPANY scope active) 지정 → 통과."""
    admin = _admin_user()
    store = _base_store(users=[
        admin,
        {"id": "U-X2", "email": "x2@a.co.kr", "name": "X2",
         "role_code": "020", "company_id": "C-A",
         "status_code": "ACTIVE", "is_active": True},
    ])
    c = _client(admin, store)
    r = c.patch("/me/company/users/U-X2/role",
                json={"role_code": "010"})
    assert r.status_code == 200


# ── 2C : management surface strict entitlement ───────────────────
@requires_client
def test_P2_2C_list_users_without_entitlement_403():
    """entitlement 없는 회사에서 GET /me/company/users → 403 SAAS_ENTITLEMENT_REQUIRED."""
    # C-B 는 default subs 에 포함 안 됨 → entitlement 없음
    admin = _admin_user(uid="U-BADM", cid="C-B")
    store = _base_store(companies=[{"id": "C-B", "name": "B사"}])
    c = _client(admin, store)
    r = c.get("/me/company/users")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_P2_2C_list_user_roles_without_entitlement_403():
    admin = _admin_user(uid="U-BADM2", cid="C-B")
    store = _base_store(companies=[{"id": "C-B", "name": "B사"}])
    c = _client(admin, store)
    r = c.get("/me/company/user-roles")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_P2_2C_list_invites_without_entitlement_403():
    admin = _admin_user(uid="U-BADM3", cid="C-B")
    store = _base_store(companies=[{"id": "C-B", "name": "B사"}])
    c = _client(admin, store)
    r = c.get("/me/company/user-invites")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_P2_2C_cancel_invite_without_entitlement_403():
    admin = _admin_user(uid="U-BADM4", cid="C-B")
    store = _base_store(
        companies=[{"id": "C-B", "name": "B사"}],
        invites=[{"id": "IV-1", "company_id": "C-B",
                  "email": "x@b.co.kr", "role_code": "020",
                  "status": "PENDING", "token_hash": "h",
                  "expires_at": "2030-01-01T00:00:00+00:00"}],
    )
    c = _client(admin, store)
    r = c.delete("/me/company/user-invites/IV-1")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_P2_2C_access_endpoint_still_returns_200_without_entitlement():
    """/me/company/access 는 entitlement 게이트 없음 (상태 반환 · Safe 진입 판정 소스)."""
    admin = _admin_user(uid="U-BADM5", cid="C-B")
    store = _base_store(companies=[{"id": "C-B", "name": "B사"}])
    c = _client(admin, store)
    r = c.get("/me/company/access")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["entitlement"]["active"] is False
    assert d["company_id"] == "C-B"


# ═══════════════════════════════════════════════════════════════════
# PATCH-3 : create_invite scope-required (BLOCKER-2B 잔여)
#   FACTORY/TEAM scope role 은 factory_id/team_id 필수 (patch_user_role 정합).
# ═══════════════════════════════════════════════════════════════════
@requires_client
def test_P3_1_invite_factory_role_without_factory_id_422():
    """FACTORY scope role (020) + factory_id 없음 → 422 FACTORY_REQUIRED."""
    admin = _admin_user()
    store = _base_store()
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "p3f@a.co.kr", "role_code": "020"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "FACTORY_REQUIRED"


@requires_client
def test_P3_2_invite_factory_role_with_own_factory_passes():
    """FACTORY scope role (020) + own-company factory_id → 200."""
    admin = _admin_user()
    store = _base_store(factories=[{"id": "F-A1", "company_id": "C-A"}])
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "p3fp@a.co.kr", "role_code": "020",
                     "factory_id": "F-A1"})
    assert r.status_code == 200
    inv = store["company_user_invites"][0]
    assert inv["role_code"] == "020"
    assert inv["factory_id"] == "F-A1"


@requires_client
def test_P3_3_invite_team_role_without_team_id_422():
    """TEAM scope role + team_id 없음 → 422 TEAM_REQUIRED."""
    admin = _admin_user()
    # 040 TEAM scope role · assignable (COMPANY 그룹 필터에 TEAM 포함되어 있음)
    roles = list([
        {"role_code": "002", "role_name": "회사관리자", "is_active": True},
        {"role_code": "040", "role_name": "팀장", "is_active": True},
    ])
    scopes = list([
        {"role_code": "002", "scope_type": "COMPANY"},
        {"role_code": "040", "scope_type": "TEAM"},
    ])
    menu_perms = list([
        {"role_code": "002", "menu_code": "worker-list",
         "can_list": True, "can_read": True, "can_create": True,
         "can_update": True, "can_delete": True},
    ])
    store = _base_store(roles=roles, role_data_scope=scopes,
                        role_menu_permissions=menu_perms)
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "p3t@a.co.kr", "role_code": "040"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "TEAM_REQUIRED"


@requires_client
def test_P3_4_invite_team_role_with_own_team_passes():
    """TEAM scope role + own-company team (team.factory.company_id=C-A) → 200."""
    admin = _admin_user()
    roles = list([
        {"role_code": "002", "role_name": "회사관리자", "is_active": True},
        {"role_code": "040", "role_name": "팀장", "is_active": True},
    ])
    scopes = list([
        {"role_code": "002", "scope_type": "COMPANY"},
        {"role_code": "040", "scope_type": "TEAM"},
    ])
    menu_perms = list([
        {"role_code": "002", "menu_code": "worker-list",
         "can_list": True, "can_read": True, "can_create": True,
         "can_update": True, "can_delete": True},
    ])
    store = _base_store(
        roles=roles, role_data_scope=scopes, role_menu_permissions=menu_perms,
        factories=[{"id": "F-A1", "company_id": "C-A"}],
        teams=[{"id": "T-1", "factory_id": "F-A1"}],
    )
    c = _client(admin, store)
    r = c.post("/me/company/user-invites",
               json={"email": "p3tp@a.co.kr", "role_code": "040",
                     "team_id": "T-1"})
    assert r.status_code == 200
    inv = store["company_user_invites"][0]
    assert inv["role_code"] == "040"
    assert inv["team_id"] == "T-1"


# ── migration : invited_by NOT NULL ───────────────────────────────
def test_P2_migration_invited_by_not_null():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    sql_path = os.path.join(here, "..", "docs", "sql",
                             "20260907_company_user_invites.sql")
    with open(sql_path, encoding="utf-8") as f:
        sql = f.read()
    # invited_by NOT NULL + ON DELETE RESTRICT
    import re
    m = re.search(r"invited_by\s+uuid\s+NOT NULL[^\n]*ON DELETE RESTRICT", sql)
    assert m is not None, \
        "migration invited_by 는 NOT NULL + ON DELETE RESTRICT 이어야 한다"
