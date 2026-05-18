"""Domain Dictionary — Core + Domain 2계층 번역 사전.

구조:
  Core Dictionary (공통) → Domain Dictionary (도메인별 확장)

매칭 우선순위:
  1. Domain 정확 매칭 → confidence 0.95
  2. Domain 패턴 매칭 → confidence 0.85
  3. Core 정확 매칭   → confidence 0.80
  4. Core 패턴 매칭   → confidence 0.70
  5. 기본 템플릿      → confidence 0.50
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DictionaryEntry:
    """번역 사전 항목."""

    operator_title: str
    operator_summary: str
    admin_title: str
    admin_summary: str
    recommended_checks: list[str]
    recommended_actions: list[str] | None = None
    impact: str = "확인 필요"


# ──────────────────────────────────────────
# Core Dictionary
# ──────────────────────────────────────────
CORE_DICTIONARY: dict[str, DictionaryEntry] = {
    "workflow.failed": DictionaryEntry(
        operator_title="작업이 완료되지 못했습니다",
        operator_summary="진행 중이던 작업이 정상적으로 완료되지 못했습니다.",
        admin_title="워크플로우 실패 발생",
        admin_summary="워크플로우 실행 중 실패가 발생했습니다.",
        recommended_checks=["관련 서비스 상태를 확인하세요", "최근 변경사항을 확인하세요"],
        impact="일부 사용자 영향 가능",
    ),
    "step.failed": DictionaryEntry(
        operator_title="처리 중 문제가 발생했습니다",
        operator_summary="작업의 일부 단계에서 문제가 발생했습니다.",
        admin_title="처리 단계 실패",
        admin_summary="워크플로우 내 특정 단계에서 실패가 발생했습니다.",
        recommended_checks=["실패한 단계의 입력 데이터를 확인하세요"],
        impact="해당 작업 영향",
    ),
    "degradation": DictionaryEntry(
        operator_title="서비스 안정성이 낮아지고 있습니다",
        operator_summary="서비스 처리 속도나 안정성이 평소보다 낮아지고 있습니다.",
        admin_title="성능 저하 감지",
        admin_summary="시스템 성능 지표가 기준치 이하로 하락하고 있습니다.",
        recommended_checks=["시스템 리소스 사용량을 확인하세요", "외부 서비스 응답 시간을 확인하세요"],
        impact="전체 서비스 영향 가능",
    ),
    "repeated_failure": DictionaryEntry(
        operator_title="같은 문제가 반복되고 있습니다",
        operator_summary="동일한 문제가 여러 번 반복 발생하고 있습니다.",
        admin_title="반복 실패 패턴 감지",
        admin_summary="동일 유형의 실패가 반복적으로 발생하고 있습니다.",
        recommended_checks=["반복 원인을 파악하세요", "근본 원인 분석이 필요합니다"],
        recommended_actions=["담당자에게 전달하세요"],
        impact="지속적 서비스 영향",
    ),
    "escalation": DictionaryEntry(
        operator_title="운영 위험이 증가하고 있습니다",
        operator_summary="문제가 확대되어 추가 주의가 필요합니다.",
        admin_title="에스컬레이션 발생",
        admin_summary="문제 심각도가 상승하여 상위 대응이 필요합니다.",
        recommended_checks=["현재 영향 범위를 확인하세요", "관련 담당자에게 전달하세요"],
        recommended_actions=["즉시 담당자에게 전달하세요"],
        impact="확대 중 — 즉시 확인 필요",
    ),
    "recovery.started": DictionaryEntry(
        operator_title="문제 해결이 진행 중입니다",
        operator_summary="발생한 문제에 대한 복구 절차가 시작되었습니다.",
        admin_title="복구 절차 시작",
        admin_summary="자동 복구 프로세스가 시작되었습니다.",
        recommended_checks=["복구 진행 상황을 지켜봐 주세요"],
        impact="복구 진행 중",
    ),
    "recovery.completed": DictionaryEntry(
        operator_title="문제가 해결되었습니다",
        operator_summary="이전에 발생한 문제가 정상적으로 해결되었습니다.",
        admin_title="복구 완료",
        admin_summary="복구 프로세스가 성공적으로 완료되었습니다.",
        recommended_checks=["서비스가 정상 동작하는지 확인하세요"],
        impact="해소됨",
    ),
    "runtime.degraded": DictionaryEntry(
        operator_title="시스템 성능이 저하되고 있습니다",
        operator_summary="시스템 전반의 처리 성능이 낮아지고 있습니다.",
        admin_title="런타임 성능 저하",
        admin_summary="런타임 환경의 전반적 성능이 저하되고 있습니다.",
        recommended_checks=["서버 리소스를 확인하세요", "최근 배포 이력을 확인하세요"],
        impact="전체 서비스 영향",
    ),
    "health.warning": DictionaryEntry(
        operator_title="시스템 상태에 주의가 필요합니다",
        operator_summary="시스템 상태 점검에서 주의가 필요한 항목이 감지되었습니다.",
        admin_title="헬스체크 경고",
        admin_summary="헬스체크에서 경고 수준의 이상이 감지되었습니다.",
        recommended_checks=["해당 서비스의 상태를 확인하세요"],
        impact="잠재적 영향",
    ),
}

# ──────────────────────────────────────────
# Domain Dictionaries
# ──────────────────────────────────────────
DOMAIN_DICTIONARIES: dict[str, dict[str, DictionaryEntry]] = {
    "payment": {
        "payment.failed": DictionaryEntry(
            operator_title="결제 처리에 문제가 발생했습니다",
            operator_summary="일부 사용자가 결제를 완료하지 못할 수 있습니다.",
            admin_title="결제 흐름 실패",
            admin_summary="결제 처리 흐름에서 실패가 발생했습니다.",
            recommended_checks=["결제 로그를 확인하세요", "PG사 상태를 확인하세요"],
            impact="일부 사용자 영향 가능",
        ),
        "payment.timeout": DictionaryEntry(
            operator_title="결제 응답 대기 시간이 초과되었습니다",
            operator_summary="결제 처리 응답이 지연되고 있습니다.",
            admin_title="결제 타임아웃",
            admin_summary="결제 PG 응답 시간이 기준치를 초과했습니다.",
            recommended_checks=["PG사 상태를 확인하세요"],
            impact="결제 사용자 영향",
        ),
        "payment.retry_exhausted": DictionaryEntry(
            operator_title="결제 재시도가 모두 실패했습니다",
            operator_summary="결제 재시도 한도에 도달했습니다. 수동 확인이 필요합니다.",
            admin_title="결제 재시도 한도 초과",
            admin_summary="자동 결제 재시도가 모두 소진되었습니다.",
            recommended_checks=["실패 건별 상세를 확인하세요", "수동 재처리 필요 여부를 판단하세요"],
            recommended_actions=["담당자에게 전달하세요"],
            impact="해당 결제 건 영향",
        ),
    },
    "document": {
        "document.failed": DictionaryEntry(
            operator_title="문서 생성이 실패했습니다",
            operator_summary="요청한 문서가 정상적으로 생성되지 못했습니다.",
            admin_title="문서 생성 실패",
            admin_summary="문서 생성 파이프라인에서 실패가 발생했습니다.",
            recommended_checks=["문서 생성 로그를 확인하세요", "템플릿 상태를 확인하세요"],
            impact="해당 문서 요청 영향",
        ),
        "document.timeout": DictionaryEntry(
            operator_title="문서 처리 시간이 초과되었습니다",
            operator_summary="문서 생성에 예상보다 오래 걸리고 있습니다.",
            admin_title="문서 생성 타임아웃",
            admin_summary="문서 렌더링 시간이 기준치를 초과했습니다.",
            recommended_checks=["Gotenberg 상태를 확인하세요"],
            impact="문서 생성 지연",
        ),
        "document.template_missing": DictionaryEntry(
            operator_title="문서 양식을 찾을 수 없습니다",
            operator_summary="요청한 문서의 양식이 시스템에 등록되어 있지 않습니다.",
            admin_title="템플릿 누락",
            admin_summary="요청된 문서 템플릿이 존재하지 않습니다.",
            recommended_checks=["템플릿 등록 상태를 확인하세요"],
            impact="해당 문서 유형 영향",
        ),
    },
    "construction": {
        "inspection.overdue": DictionaryEntry(
            operator_title="점검 기한이 지났습니다",
            operator_summary="예정된 점검의 기한이 초과되었습니다.",
            admin_title="점검 기한 초과",
            admin_summary="점검 스케줄의 기한이 초과되었습니다.",
            recommended_checks=["미완료 점검 목록을 확인하세요"],
            recommended_actions=["점검 담당자에게 전달하세요"],
            impact="법령 준수 영향 가능",
        ),
        "schedule.conflict": DictionaryEntry(
            operator_title="일정이 겹칩니다",
            operator_summary="같은 시간대에 여러 일정이 배정되어 있습니다.",
            admin_title="일정 충돌 감지",
            admin_summary="스케줄 간 충돌이 감지되었습니다.",
            recommended_checks=["겹치는 일정을 확인하세요"],
            impact="스케줄 영향",
        ),
        "compliance.gap": DictionaryEntry(
            operator_title="법령 준수 사항을 확인하세요",
            operator_summary="법령에서 요구하는 준수 사항 중 미이행 항목이 있습니다.",
            admin_title="컴플라이언스 갭 감지",
            admin_summary="법령 준수 항목에서 미이행 건이 감지되었습니다.",
            recommended_checks=["미이행 법령 항목을 확인하세요", "기한 내 이행 계획을 수립하세요"],
            recommended_actions=["안전관리자에게 전달하세요"],
            impact="법적 위험 가능",
        ),
    },
    "marketing": {
        "campaign.failed": DictionaryEntry(
            operator_title="캠페인 발행이 실패했습니다",
            operator_summary="예정된 캠페인이 정상적으로 발행되지 못했습니다.",
            admin_title="캠페인 발행 실패",
            admin_summary="캠페인 발행 프로세스에서 실패가 발생했습니다.",
            recommended_checks=["캠페인 설정을 확인하세요"],
            impact="캠페인 발행 영향",
        ),
        "campaign.low_engagement": DictionaryEntry(
            operator_title="캠페인 반응이 낮습니다",
            operator_summary="발행된 캠페인의 반응률이 기대 수준보다 낮습니다.",
            admin_title="캠페인 참여율 저조",
            admin_summary="캠페인 참여 지표가 기준치 미달입니다.",
            recommended_checks=["캠페인 타겟 설정을 확인하세요", "메시지 내용을 검토하세요"],
            impact="마케팅 효과 저하",
        ),
    },
    "tai": {
        "diagnosis.failed": DictionaryEntry(
            operator_title="법령진단 처리가 실패했습니다",
            operator_summary="법령진단 요청이 정상적으로 처리되지 못했습니다.",
            admin_title="진단 처리 실패",
            admin_summary="법령진단 엔진에서 처리 실패가 발생했습니다.",
            recommended_checks=["진단 요청 데이터를 확인하세요", "법령엔진 상태를 확인하세요"],
            impact="해당 진단 요청 영향",
        ),
        "diagnosis.timeout": DictionaryEntry(
            operator_title="법령진단 응답이 지연되고 있습니다",
            operator_summary="법령진단 처리에 예상보다 시간이 걸리고 있습니다.",
            admin_title="진단 타임아웃",
            admin_summary="법령진단 처리 시간이 기준치를 초과했습니다.",
            recommended_checks=["법령엔진 부하를 확인하세요"],
            impact="진단 응답 지연",
        ),
        "subscription.failed": DictionaryEntry(
            operator_title="구독 처리가 실패했습니다",
            operator_summary="구독 결제 또는 활성화 과정에서 문제가 발생했습니다.",
            admin_title="구독 결제 실패",
            admin_summary="구독 활성화 흐름에서 실패가 발생했습니다.",
            recommended_checks=["결제 상태를 확인하세요", "구독 활성화 로그를 확인하세요"],
            impact="해당 사용자 구독 영향",
        ),
    },
}

# ──────────────────────────────────────────
# Lookup
# ──────────────────────────────────────────

_SEVERITY_URGENCY: dict[str, str] = {
    "CRITICAL": "즉시 확인 필요",
    "WARNING": "주의 필요",
    "INFO": "참고",
}


def severity_to_urgency(severity: str) -> str:
    """Severity → Urgency 운영 표현 변환."""
    return _SEVERITY_URGENCY.get(severity.upper(), "참고")


def lookup(
    event_type: str,
    domain: str | None = None,
) -> tuple[DictionaryEntry | None, float]:
    """event_type + domain 으로 사전 검색.

    Returns:
        (entry, confidence) — 없으면 (None, 0.5)
    """
    # 1) Domain exact
    if domain and domain in DOMAIN_DICTIONARIES:
        dd = DOMAIN_DICTIONARIES[domain]
        if event_type in dd:
            return dd[event_type], 0.95
        # 2) Domain pattern — event_type 이 domain prefix로 시작
        for key, entry in dd.items():
            if event_type.startswith(key.split(".")[0] + "."):
                return entry, 0.85

    # 3) Core exact
    if event_type in CORE_DICTIONARY:
        return CORE_DICTIONARY[event_type], 0.80

    # 4) Core pattern
    for key, entry in CORE_DICTIONARY.items():
        if event_type.startswith(key.split(".")[0] + "."):
            return entry, 0.70

    return None, 0.50
