"""
health_registry.py v1.0.0
서비스 자체 등록형 헬스체크 레지스트리.

사용법:
  각 서비스 파일 하단에서:
    from services.health_registry import register_probe
    register_probe("서비스명", check_fn, critical=True, desc_ko="한글 설명")

  /health/deep 호출 시 등록된 모든 probe 자동 실행.
  새 서비스 추가 시 register_probe 1줄만 추가하면 됨.
  yml 수정 불필요.
"""
from __future__ import annotations

import inspect
import time
from datetime import datetime, timedelta, timezone

_probes: dict = {}


def register_probe(name, fn, critical=False, desc_ko=""):
    """
    헬스체크 프로브 등록.

    Args:
        name: 영문 식별자 (예: "law_engine")
        fn: async 또는 sync 함수. dict 반환. 실패 시 exception.
        critical: True면 이 프로브 실패 시 전체 status = "critical"
        desc_ko: 한글 설명 (SMS/알림에 사용)
    """
    _probes[name] = {
        "fn": fn,
        "critical": critical,
        "desc_ko": desc_ko or name,
    }


# ═══════════════════════════════════════════
# 한글 에러 메시지 매핑
# ═══════════════════════════════════════════
ERROR_MESSAGES_KO = {
    # 프로브별 실패 메시지
    "db": "데이터베이스 연결에 실패했습니다. DB 서버를 확인하세요.",
    "law_engine": "법령 엔진이 응답하지 않습니다. 법령 진단 서비스가 중단됩니다.",
    "pdf_engine": "PDF 생성 엔진(Gotenberg)이 응답하지 않습니다. 유료 리포트 발급이 불가합니다.",
    "sms": "SMS 발송 연결이 끊겼습니다. 알림 발송이 불가합니다.",
    "storage": "파일 저장소(Supabase Storage) 연결에 실패했습니다.",
    "auth": "인증 서비스가 응답하지 않습니다. 로그인이 불가합니다.",
    "matching": "전문가 매칭 서비스에 접근할 수 없습니다.",
    "education": "교육 관리 데이터에 접근할 수 없습니다.",
    "inspection": "점검 관리 데이터에 접근할 수 없습니다.",
    "tbm": "TBM 관리 데이터에 접근할 수 없습니다.",
    "risk": "위험성평가 데이터에 접근할 수 없습니다.",
    "payment": "결제 시스템(KG이니시스) 연결을 확인할 수 없습니다.",
    "construction": "건설 관리 데이터에 접근할 수 없습니다.",
    "frontend_safe": "SaaS 사이트(safe.taieng.co.kr)에 접속할 수 없습니다.",
    "frontend_marketing": "마케팅 사이트(new.taieng.co.kr)에 접속할 수 없습니다.",
    # 상태별 종합 메시지
    "critical": "🚨 서비스 장애가 발생했습니다. 즉시 확인이 필요합니다.",
    "degraded": "⚠️ 일부 서비스가 정상적이지 않습니다. 확인이 필요합니다.",
    "healthy": "✅ 모든 서비스가 정상 운영 중입니다.",
}


def get_error_message_ko(probe_name, error_str=""):
    """프로브 이름으로 한글 에러 메시지 반환"""
    base = ERROR_MESSAGES_KO.get(probe_name, f"{probe_name} 서비스에 문제가 발생했습니다.")
    if error_str:
        return f"{base} (상세: {error_str[:80]})"
    return base


def build_alert_message_ko(status, failed_probes, results):
    """
    SMS/알림용 한글 메시지 생성.
    """
    lines = []

    if status == "critical":
        lines.append("🚨 TAI 서비스 장애 알림")
    else:
        lines.append("⚠️ TAI 서비스 경고 알림")

    lines.append("")

    for name in failed_probes:
        probe_info = _probes.get(name, {})
        error = results.get(name, {}).get("error", "")
        msg = get_error_message_ko(name, error)
        critical_mark = " [긴급]" if probe_info.get("critical") else ""
        lines.append(f"❌ {msg}{critical_mark}")

    warn_probes = [k for k, v in results.items() if v.get("status") == "warn"]
    if warn_probes:
        lines.append("")
        for name in warn_probes:
            detail = results[name].get("detail", "")
            lines.append(f"⚠️ {_probes.get(name, {}).get('desc_ko', name)}: {detail}")

    ok_probes = [k for k, v in results.items() if v.get("status") == "ok"]
    if ok_probes:
        lines.append("")
        ok_names = [_probes.get(n, {}).get("desc_ko", n) for n in ok_probes]
        lines.append(f"정상: {', '.join(ok_names)} ({len(ok_probes)}건)")

    kst = datetime.now(timezone(timedelta(hours=9)))
    lines.append(f"확인 시각: {kst.strftime('%Y-%m-%d %H:%M')} KST")

    return "\n".join(lines)


def build_sms_message_ko(status, failed_probes, results):
    """SMS용 짧은 한글 메시지 (90자 이내)"""
    if not failed_probes:
        return "[TAI] 서비스 정상"

    failed_descs = []
    for name in failed_probes[:3]:
        desc = _probes.get(name, {}).get("desc_ko", name)
        failed_descs.append(desc)

    extra = f" 외 {len(failed_probes) - 3}건" if len(failed_probes) > 3 else ""
    body = f"[TAI장애] {', '.join(failed_descs)}{extra} 즉시확인필요"
    return body[:90]


async def run_all_probes():
    """등록된 모든 probe를 실행하여 결과 반환"""
    results = {}

    for name, probe in _probes.items():
        try:
            start = time.time()
            fn = probe["fn"]
            if inspect.iscoroutinefunction(fn):
                result = await fn()
            else:
                result = fn()
            ms = int((time.time() - start) * 1000)
            results[name] = {
                "status": result.get("status", "ok"),
                "latency_ms": ms,
                "desc_ko": probe["desc_ko"],
                **{k: v for k, v in result.items() if k != "status"},
            }
        except Exception as e:
            results[name] = {
                "status": "fail",
                "error": str(e)[:100],
                "critical": probe["critical"],
                "desc_ko": probe["desc_ko"],
                "message_ko": get_error_message_ko(name, str(e)),
            }

    return results


def get_overall_status(results):
    """전체 상태 판정"""
    critical_fail = any(
        v.get("status") == "fail" and _probes.get(k, {}).get("critical") for k, v in results.items()
    )
    any_fail = any(v.get("status") == "fail" for v in results.values())
    any_warn = any(v.get("status") == "warn" for v in results.values())

    if critical_fail:
        return "critical"
    if any_fail:
        return "degraded"
    if any_warn:
        return "degraded"
    return "healthy"
