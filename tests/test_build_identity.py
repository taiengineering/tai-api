"""BI01-BI07 — GET /.well-known/tai-build.json build identity endpoint tests."""
from __future__ import annotations
import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.build_identity import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


VALID_SHA = "a" * 40


def test_BI01_valid_sha_200(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", VALID_SHA)
    client = _make_client()
    resp = client.get("/.well-known/tai-build.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == "1.0"
    assert body["identity_type"] == "TAI_DEPLOYMENT_BUILD"
    assert body["git_commit_sha"] == VALID_SHA
    assert resp.headers.get("cache-control") == "no-store"


def test_BI02_invalid_sha_503(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "short")
    client = _make_client()
    resp = client.get("/.well-known/tai-build.json")
    assert resp.status_code == 503
    assert resp.json()["code"] == "DEPLOYMENT_IDENTITY_UNAVAILABLE"


def test_BI03_missing_sha_503(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    client = _make_client()
    resp = client.get("/.well-known/tai-build.json")
    assert resp.status_code == 503


def test_BI04_repository_exact(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", VALID_SHA)
    client = _make_client()
    resp = client.get("/.well-known/tai-build.json")
    assert resp.json()["repository"] == "taiengineering/tai-api"


def test_BI05_service_exact(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", VALID_SHA)
    client = _make_client()
    resp = client.get("/.well-known/tai-build.json")
    assert resp.json()["service"] == "tai-api"


def test_BI06_no_timestamp(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", VALID_SHA)
    client = _make_client()
    resp = client.get("/.well-known/tai-build.json")
    body = resp.json()
    assert "timestamp" not in body
    assert "build_time" not in body
    assert "deployment_time" not in body


def test_BI07_no_secret(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", VALID_SHA)
    monkeypatch.setenv("INTERNAL_API_SECRET", "super-secret-abc")
    client = _make_client()
    resp = client.get("/.well-known/tai-build.json")
    assert "super-secret-abc" not in resp.text
