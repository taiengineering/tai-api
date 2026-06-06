"""[ROLLBACK 2026-06-06] 비활성화됨.

이 라우터(diagnosis_input_draft)는 입력부 표준화 방향과 어긋나 되돌렸다.
입력부 표준은 factories(시설) → factory_process(공정) → equipment_assets(설비)
계층이며, 임시저장도 factories.diagnosis_status='DRAFT' 표준 경로를 사용한다.
별도 draft 버퍼 테이블(archive.diagnosis_input_draft 로 격리)은 사용하지 않는다.

router_registry/diagnosis.py 등록에서 제외되어 로드되지 않는다.
"""
