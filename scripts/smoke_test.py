import os
import sys
import httpx

API = os.environ["API_URL"]
failures = []

def check(name, fn):
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as e:
        msg = f"{name}: {e}"
        print(f"  ✗ {msg}")
        failures.append(msg)

def send_alert(text):
    key = os.environ.get("MESSAGEMI_KEY")
    phone = os.environ.get("ALERT_PHONE")
    if not key or not phone:
        print(f"[ALERT] {text}")
        return
    httpx.post(
        "https://api.messagemi.com/v1/send",
        headers={"Authorization": f"Bearer {key}"},
        json={"to": phone, "content": text[:90]}
    )

# S1: Health
def s1():
    r = httpx.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
check("S1 /health", s1)

# S2: Fix Chat 세션 생성
def s2():
    r = httpx.post(f"{API}/fix/chat/start",
        json={"user_type": "GUEST"}, timeout=10)
    assert r.status_code == 200
    assert r.json().get("session_id")
check("S2 fix/chat/start", s2)

# S3: 로그인
def s3():
    email = os.environ.get("TEST_EMAIL")
    pw = os.environ.get("TEST_PASSWORD")
    if not email:
        return  # 테스트 계정 없으면 skip
    r = httpx.post(f"{API}/auth/login",
        json={"email": email, "password": pw}, timeout=10)
    assert r.status_code == 200
check("S3 auth/login", s3)

# S4: 법령진단 (최소 입력)
def s4():
    r = httpx.post(f"{API}/diagnosis/free",
        json={"sector": "BUILDING", "area": 500,
              "building_use": "OFFICE", "completion_year": 2010},
        timeout=30)
    assert r.status_code == 200
check("S4 diagnosis/free", s4)

print(f"\n결과: {4 - len(failures)}/4 성공")

if failures:
    alert_msg = f"[TAI Smoke] {len(failures)}건 실패: {failures[0][:60]}"
    send_alert(alert_msg)
    sys.exit(1)
