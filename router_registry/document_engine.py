"""Document Engine — 문서엔진 전용 라우터.

격리 필수: 이 그룹 실패해도 SaaS Core 정상 작동.
8개 라우터 등록 (2026-07-24: compliance_report 추가).
"""
ROUTERS = [
    {"module": "routers.document_engine"},       # TBM PDF (/document-forms)
    {"module": "routers.document_engine_api"},   # Runtime Document Engine (/document-engine)
    {"module": "routers.engine_document"},
    {"module": "routers.report_forms"},
    {"module": "routers.document_monitoring"},
    {"module": "routers.requirement_engine"},
    {"module": "routers.diagram_proxy"},
    {"module": "routers.compliance_report"},      # P2-3 증빙 이행 리포트 (/compliance-report)
]
