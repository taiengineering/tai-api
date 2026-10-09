"""WO-WWW-AUTH-NAVER-001: /auth/ensure-user account ownership regression.

This suite patches _auth_user_from_token; NO real DB, OAuth credential, or network.
Existing Google/Kakao users whose public.users.auth_id matches remain idempotent.
Email-only account linking (including legacy NULL auth_id) must fail closed.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
import routers.auth as auth_mod


class _Users:
    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]
        self.inserts = []
        self.updates = []
        self.calls = []

    def table(self, name):
        assert name == "users"
        return _Query(self)


class _Query:
    def __init__(self, state):
        self.state = state
        self.filters = []
        self.insert_payload = None

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, _):
        return self

    def update(self, payload):
        self.state.updates.append(payload)
        raise AssertionError("ensure-user must not rebind public.users.auth_id")

    def insert(self, payload):
        self.insert_payload = dict(payload)
        return self

    def execute(self):
        if self.insert_payload is not None:
            row = {"id": "new-row-1", **self.insert_payload}
            self.state.inserts.append(row)
            self.state.rows.append(row)
            return SimpleNamespace(data=[row])
        rows = [
            r for r in self.state.rows
            if all(r.get(key) == value for key, value in self.filters)
        ]
        self.state.calls.append(tuple(self.filters))
        return SimpleNamespace(data=rows[:1])


def _run(monkeypatch, existing, *, auth_id="auth-new", email="person@example.com"):
    db = _Users(existing)
    auth_user = SimpleNamespace(
        id=auth_id,
        email=email,
        user_metadata={"name": "테스트"},
        app_metadata={"provider": "custom:naver"},
    )
    monkeypatch.setattr(auth_mod, "_auth_user_from_token", lambda _: (db, auth_user))
    return db, lambda: auth_mod.ensure_user("Bearer fixture")


def test_existing_auth_id_is_idempotent_and_no_mutation(monkeypatch):
    row = {"id": "public-1", "auth_id": "auth-new", "email": "person@example.com"}
    db, invoke = _run(monkeypatch, [row])
    result = invoke()
    assert result["status"] == "success"
    assert result["created"] is False
    assert result["data"]["id"] == "public-1"
    assert not db.inserts and not db.updates


@pytest.mark.parametrize("linked", ["auth-other", None, ""])
def test_same_email_different_or_unbound_auth_id_is_409(monkeypatch, linked):
    row = {"id": "existing-customer", "auth_id": linked, "email": "person@example.com"}
    db, invoke = _run(monkeypatch, [row])
    with pytest.raises(HTTPException) as captured:
        invoke()
    assert captured.value.status_code == 409
    assert captured.value.detail["code"] == "SOCIAL_EMAIL_ACCOUNT_CONFLICT"
    assert db.rows == [row]
    assert not db.inserts and not db.updates


@pytest.mark.parametrize("missing_email", [None, "", "  "])
def test_missing_email_is_422_without_create(monkeypatch, missing_email):
    db, invoke = _run(monkeypatch, [], email=missing_email)
    with pytest.raises(HTTPException) as captured:
        invoke()
    assert captured.value.status_code == 422
    assert captured.value.detail["code"] == "SOCIAL_EMAIL_REQUIRED"
    assert not db.inserts and not db.updates


def test_new_social_user_created_once_repeat_idempotent(monkeypatch):
    db, invoke = _run(monkeypatch, [])
    created = invoke()
    assert created["created"] is True
    assert created["data"]["auth_id"] == "auth-new"
    assert created["data"]["email"] == "person@example.com"
    assert created["data"]["identity_verified"] is False
    assert created["data"]["role_code"] == "002"
    assert len(db.inserts) == 1
    second = invoke()
    assert second["created"] is False
    assert second["data"]["id"] == created["data"]["id"]
    assert len(db.inserts) == 1


def test_matching_existing_email_is_not_used_as_other_identity(monkeypatch):
    # Explicitly demonstrate: first query by token auth_id owns the user row.
    db, invoke = _run(monkeypatch, [
        {"id": "old-user", "auth_id": "auth-legacy", "email": "other@example.com"},
        {"id": "new-user", "auth_id": "auth-new", "email": "person@example.com"},
    ])
    assert invoke()["data"]["id"] == "new-user"
    assert not db.inserts and not db.updates
