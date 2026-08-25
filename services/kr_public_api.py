"""
services/kr_public_api.py — 한국 공공 API 전용 아웃바운드 프록시 (단일 관리 지점)

Railway(해외 IP)는 data.go.kr / juso.go.kr 등 한국 공공 API에서 IP 차단되므로
한국 IP 프록시(cafe24 squid)를 경유한다. 개별 라우터가 proxies= 를 직접 다루지 않고
이 모듈만 사용한다 — 프록시 설정이 한 곳에서만 관리되어 누락·충돌을 막는다.

환경변수:
  OUTBOUND_PROXY  프록시 URL. 예) http://호스트:포트  (인증은 아래 변수로 주입)
  PROXY_USER      프록시 basic 인증 아이디 (선택)
  PROXY_PASS      프록시 basic 인증 비밀번호 (선택)
  PROXY_PORT      OUTBOUND_PROXY 에 포트가 없을 때만 사용 (선택)

사용:
  requests:  requests.get(url, ..., proxies=get_proxies())
  httpx:     httpx.Client(proxy=httpx_proxy())  또는  AsyncClient(proxy=httpx_proxy())
  둘 다 프록시 미설정 시 None 을 돌려주므로 그대로 넘기면 직접 호출이 된다.
"""
import os
from typing import Optional
from urllib.parse import quote


def _build_proxy_url() -> Optional[str]:
    """OUTBOUND_PROXY 에 PROXY_USER/PROXY_PASS 인증과 (필요시) PROXY_PORT 를 주입한 완성 URL.
    OUTBOUND_PROXY 미설정 시 None."""
    raw = os.environ.get("OUTBOUND_PROXY", "").strip()
    if not raw:
        return None
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
    else:
        scheme, rest = "http", raw
    if "@" in rest:
        creds, hostpart = rest.split("@", 1)
    else:
        creds, hostpart = "", rest
        user = os.environ.get("PROXY_USER", "").strip()
        pw = os.environ.get("PROXY_PASS", "").strip()
        if user:
            creds = f"{quote(user, safe='')}:{quote(pw, safe='')}"
    if ":" not in hostpart:
        port = os.environ.get("PROXY_PORT", "").strip()
        if port:
            hostpart = f"{hostpart}:{port}"
    if creds:
        return f"{scheme}://{creds}@{hostpart}"
    return f"{scheme}://{hostpart}"


def get_proxies() -> Optional[dict]:
    """requests 용 proxies dict ({"http": url, "https": url}) 또는 None."""
    purl = _build_proxy_url()
    if purl:
        return {"http": purl, "https": purl}
    return None


def httpx_proxy() -> Optional[str]:
    """httpx 용 proxy URL 문자열 또는 None."""
    return _build_proxy_url()


def is_configured() -> bool:
    """프록시가 설정돼 있으면 True."""
    return bool(os.environ.get("OUTBOUND_PROXY", "").strip())
