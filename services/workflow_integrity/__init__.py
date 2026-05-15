"""Workflow Integrity Evaluation Layer.

이 패키지는 Workflow 흐름의 정상성(Integrity)을 평가한다.

핵심 철학:
- Workflow는 상태를 만든다
- Integrity는 상태를 평가한다
- Alert는 운영 중요도를 판단한다
- Notification은 전달한다

절대 원칙:
- 상태 변경 금지 (판단만 수행)
- Notification 직접 호출 금지
- 자동 수정/복구 금지
- AI 판단 금지
"""
