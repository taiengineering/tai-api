"""Response Playbook — 상황 유형별 기본 대응 패턴.

운영 행동 가이드. 기술 명령 아님.
"""
from __future__ import annotations
from typing import Any

_PLAYBOOKS: dict[str, dict[str, Any]] = {
    "worsening": {
        "title": "상황 악화 대응",
        "actions": ["영향 범위를 우선 확인하세요", "최근 변경사항을 점검하세요", "악화 속도를 관찰하세요"],
        "checks": ["최근 30분 배포 여부", "외부 API 응답 시간", "tenant 확산 여부"],
        "order": ["영향 tenant 확인", "실패 증가 추세 확인", "최근 배포 확인", "escalation 여부 확인"],
    },
    "recurring": {
        "title": "재발 상황 대응",
        "actions": ["이전 해결 흐름을 비교하세요", "근본 원인이 해결되었는지 확인하세요", "재발 패턴을 파악하세요"],
        "checks": ["이전 해결 시점", "재발 간격", "동일 근본 원인 여부"],
        "order": ["이전 해결 이력 확인", "근본 원인 재검토", "영향 범위 비교", "재발 방지책 검토"],
    },
    "escalating": {
        "title": "위험 증가 대응",
        "actions": ["tenant 확산 여부를 우선 확인하세요", "고객 영향을 판단하세요", "담당자에게 전달하세요"],
        "checks": ["영향 tenant 수", "고객 대면 흐름 영향", "escalation 속도"],
        "order": ["고객 영향 확인", "tenant 확산 확인", "담당자 전달", "escalation 원인 파악"],
    },
    "stabilizing": {
        "title": "안정화 확인",
        "actions": ["recovery 효과를 확인하세요", "안정화가 지속되는지 관찰하세요", "재악화 징후를 모니터링하세요"],
        "checks": ["recovery 지속 여부", "실패 감소 추세", "재악화 징후"],
        "order": ["recovery 효과 확인", "실패 추세 확인", "재악화 모니터링"],
    },
    "payment": {
        "title": "결제 장애 대응",
        "actions": ["고객 영향을 우선 확인하세요", "결제 로그를 점검하세요", "PG사 상태를 확인하세요"],
        "checks": ["결제 실패률", "PG사 응답 시간", "영향 고객 수"],
        "order": ["고객 영향 확인", "결제 로그 확인", "PG사 상태 확인", "최근 배포 확인"],
    },
    "document": {
        "title": "문서 생성 장애 대응",
        "actions": ["문서 생성 서비스 상태를 확인하세요", "템플릿 상태를 점검하세요"],
        "checks": ["Gotenberg 서비스 상태", "템플릿 가용성", "timeout 증가 여부"],
        "order": ["Gotenberg 상태 확인", "템플릿 확인", "timeout 추세 확인"],
    },
    "timeout": {
        "title": "Timeout 증가 대응",
        "actions": ["timeout 증가 추세를 확인하세요", "외부 API 응답 시간을 점검하세요"],
        "checks": ["timeout 증가 속도", "외부 API 응답", "서버 리소스 사용량"],
        "order": ["timeout 추세 확인", "외부 API 확인", "서버 리소스 확인"],
    },
    "default": {
        "title": "일반 대응",
        "actions": ["관련 서비스 상태를 확인하세요", "최근 변경사항을 확인하세요"],
        "checks": ["서비스 상태", "최근 변경 이력"],
        "order": ["서비스 상태 확인", "최근 변경 확인"],
    },
}

def get_playbook(situation_type: str) -> dict[str, Any]:
    return _PLAYBOOKS.get(situation_type, _PLAYBOOKS["default"])

def match_playbook(snapshot: dict[str, Any]) -> dict[str, Any]:
    """snapshot에서 가장 적합한 playbook 매칭."""
    dt = snapshot.get("delta_type", "")
    status = snapshot.get("status", "")
    sid = snapshot.get("situation_id", "")
    parts = sid.split(":")
    domain = parts[1] if len(parts) >= 2 else ""
    # 우선순위: delta_type > status > domain > default
    if dt in _PLAYBOOKS: return _PLAYBOOKS[dt]
    if status in _PLAYBOOKS: return _PLAYBOOKS[status]
    if domain in _PLAYBOOKS: return _PLAYBOOKS[domain]
    flow = parts[2] if len(parts) >= 3 else ""
    if "timeout" in flow: return _PLAYBOOKS["timeout"]
    return _PLAYBOOKS["default"]

def list_playbooks() -> list[dict[str, Any]]:
    return [{"type": k, **v} for k, v in _PLAYBOOKS.items()]
