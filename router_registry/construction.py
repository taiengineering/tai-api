"""Construction & Safety — 건설안전·교육·장비·인력 라우터."""
ROUTERS = [
    {"module": "routers.construction", "prefix": "/construction", "tags": ["건설안전"]},
    # 건설 공정별 점검항목 마스터 조회 /construction/check-templates
    # prefix 를 두지 않는다 — 모듈이 데코레이터에 절대경로를 적어 위 construction 과
    # 경로가 겹치지 않으며, prefix 를 주면 /construction/construction/... 이 된다.
    {"module": "routers.construction_check"},
    {"module": "routers.subcontractors"},
    {"module": "routers.tbm"},
    {"module": "routers.tbm_templates"},
    {"module": "routers.safety_meetings"},
    {"module": "routers.risk_assessments"},
    {"module": "routers.ra_settings"},  # 위험성평가 설정(운영 파라미터·척도) /ra/*
    {"module": "routers.ra_items"},     # 위험성평가 요인·대책·재판정 /ra/*
    {"module": "routers.ra_report"},    # 위험성평가 증적 리포트(중처법 반기 점검) /ra/semiannual-report
    {"module": "routers.worker_registry"},
    {"module": "routers.worker_check"},
    {"module": "routers.worker_home"},
    # 작업자 PWA(/app/) 전용 — 종전 서버에 부재해 404 로 실패하던 경로들
    {"module": "routers.worker_reports"},  # 안전신고 /safety-reports · 긴급신고 /emergency/report
    {"module": "routers.worker_assets"},   # 사진업로드 /uploads/inspection-photo · /work-assignments · /education/worker-complete
    {"module": "routers.worker_permits"},  # 위험성평가 참여 /risk-assessments/{id}/participate · 출퇴근 /attendance · 작업허가 /work-permits
    # TBM 리더 스코프 /leader/* — 토큰의 team_id 로만 조회, 클라이언트 team_id 불신
    # 모듈이 APIRouter(prefix="/leader") 를 이미 갖고 있어 여기서 prefix 를 주지 않는다.
    {"module": "routers.leader_scope"},
    {"module": "routers.equipment_assets"},
    {"module": "routers.equipment_checkins"},
    {"module": "routers.engine_equipment"},
    {"module": "routers.engine_model"},
    {"module": "routers.education"},
    {"module": "routers.education_assign"},
    {"module": "routers.personnel"},
    {"module": "routers.safety_info"},
]
