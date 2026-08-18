"""Document Engine — 문서엔진 전용 라우터.

격리 필수: 이 그룹 실패해도 SaaS Core 정상 작동.
9개 라우터 등록 (2026-07-24: compliance_report 추가 / 2026-08-18: document_forms 추가).
"""
ROUTERS = [
    {"module": "routers.document_engine"},       # TBM PDF (/document-forms/{doc_id}/preview·generate)
    # LEDGER §17: 서식 목록·상세(/document-forms, /stats, /{doc_id})는 이 모듈에 있는데
    # 어느 ROUTERS 에도 등록되지 않아 전부 404 였다. 봉투 수정(7b99a57)을 해도
    # 화면이 그 코드에 닿지 못했다. §32(alert_messages)와 같은 형태다.
    # 위 document_engine 과 prefix 는 같으나 경로 모양이 겹치지 않는다
    # (여기: "" · /stats · /{doc_id} / 위: /{doc_id}/preview · /{doc_id}/generate).
    {"module": "routers.document_forms"},
    {"module": "routers.document_engine_api"},   # Runtime Document Engine (/document-engine)
    {"module": "routers.engine_document"},
    {"module": "routers.report_forms"},
    {"module": "routers.document_monitoring"},
    {"module": "routers.requirement_engine"},
    {"module": "routers.diagram_proxy"},
    {"module": "routers.compliance_report"},      # P2-3 증빙 이행 리포트 (/compliance-report)
]
