"""Browser Synthetic Engine.

사용자 흐름(User Journey)을 플랫폼 Event Layer로 연결한다.

핵심 철학:
- Workflow는 상태를 만든다
- Integrity는 흐름을 평가한다
- Alert는 운영 중요도를 판단한다
- Notification은 전달한다
- Synthetic는 실제 사용자 흐름을 관측한다

절대 원칙:
- Workflow Engine 직접 제어 금지
- Business Logic 금지
- 자동 복구 금지
- 판단(Evaluation)은 Integrity Layer 책임
"""
