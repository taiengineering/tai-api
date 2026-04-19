import os
import sys
import httpx

API = os.environ["API_URL"]
failures = []

def check(name, fn):
    try:
        fn()
        print(f"  \u2713 {name}")
    except Exception as e:
        msg = f"{name}: {e}"
        print(f"  \u2717 {msg}")
        failures.append(msg)

def send_alert(text):
    phone = os.environ.get("ALERT_PHONE")
    if not phone:
        print(f"[ALERT] {text}")
        return
    try:
        r = httpx.get(
            f"{API}/messaging/debug-send",
            params={"receiver": phone, "message": text[:90]},
            timeout=15,
        )
        print(f"[SMS] status={r.status_code}")
    except Exception as e:
        print(f"[SMS FAIL] {e}")

# S1: Health
def s1():
    r = httpx.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    status = r.json()["status"]
    assert status in ("healthy", "degraded"), f"unexpected status: {status}"
check("S1 /health", s1)

# S2: Fix Chat session
def s2():
    r = httpx.post(f"{API}/fix/chat/start",
        json={"user_type": "GUEST"}, timeout=10)
    assert r.status_code == 200
    assert r.json().get("session_id")
check("S2 fix/chat/start", s2)

# S3: Login
def s3():
    email = os.environ.get("TEST_EMAIL")
    pw = os.environ.get("TEST_PASSWORD")
    if not email:
        return
    r = httpx.post(f"{API}/auth/login",
        json={"email": email, "password": pw}, timeout=10)
    assert r.status_code == 200
check("S3 auth/login", s3)

# S4: Diagnosis (60s timeout - cold start + law engine)
def s4():
    r = httpx.post(f"{API}/diagnosis/free",
        json={"sector": "BUILDING", "area": 500,
              "building_use": "OFFICE", "completion_year": 2010},
        timeout=60)
    assert r.status_code == 200
check("S4 diagnosis/free", s4)

print(f"\nResult: {4 - len(failures)}/4 passed")

if failures:
    alert_msg = f"[TAI Smoke] {len(failures)} failed: {failures[0][:60]}"
    send_alert(alert_msg)
    sys.exit(1)
