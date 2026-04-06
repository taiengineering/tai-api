"""
Railway 배포 완료 대기 스크립트 — GitHub Actions Job 3 전처리
==============================================================
main.py 의 APP_VERSION 을 파싱해서 예상 버전을 알고,
API 가 해당 버전을 반환할 때까지 폴링합니다.

최대 대기: 5분 (30초 간격 × 10회)
배포 미완료 시: 경고 후 현재 버전으로 테스트 계속 진행 (차단 안 함)

실행:
  API_URL=https://api.taieng.co.kr python tests/wait_for_deploy.py
"""
import os
import sys
import time
import re
import requests

API_URL = os.environ.get("API_URL", "https://api.taieng.co.kr").rstrip("/")

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def get_expected_version() -> str:
    """main.py 에서 APP_VERSION 파싱"""
    try:
        with open("main.py", "r", encoding="utf-8") as f:
            m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', f.read())
            return m.group(1) if m else ""
    except FileNotFoundError:
        return ""


def get_api_version() -> str:
    try:
        r = requests.get(f"{API_URL}/", timeout=10)
        return r.json().get("version", "") if r.status_code == 200 else ""
    except Exception:
        return ""


def main():
    expected = get_expected_version()
    print(f"\n{BOLD}Railway 배포 완료 대기{RESET}")
    print(f"  API:       {API_URL}")
    print(f"  예상 버전: {expected or '(main.py 파싱 실패)'}")
    print(f"  최대 대기: 5분 (30초 × 10회)\n")

    if not expected:
        print(f"{YELLOW}⚠️  예상 버전 파싱 실패 — 현재 버전으로 즉시 테스트 진행{RESET}")
        return

    for attempt in range(10):
        current = get_api_version()
        line = f"  [{attempt+1}/10] 현재={current or '응답없음'} / 예상={expected}"

        if current == expected:
            print(f"{GREEN}{line} → ✅ 배포 완료{RESET}")
            return
        else:
            print(f"{YELLOW}{line} → ⏳ 대기 중...{RESET}")
            if attempt < 9:
                time.sleep(30)

    current = get_api_version()
    print(f"\n{YELLOW}⚠️  5분 내 배포 미완료 (현재: {current})")
    print(f"   현재 배포 버전으로 테스트를 계속 진행합니다.{RESET}")


if __name__ == "__main__":
    main()
