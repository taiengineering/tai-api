"""Document Engine — 문서엔진 전용 라우터.

격리 필수: 이 그룹 실패해도 SaaS Core 정상 작동.
7개 라우터 등록 (2026-05-24 업데이트).
"""
ROUTERS = [
    {"module": "routers.document_engine"},       # TBM PDF (/document-forms)
    {"module": "routers.document_engine_api"},   # Runtime Document Engine (/document-engine)
    {"module": "routers.engine_document"},
    {"module": "routers.report_forms"},
    {"module": "routers.document_monitoring"},
    {"module": "routers.requirement_engine"},
    {"module": "routers.diagram_proxy"},
]
