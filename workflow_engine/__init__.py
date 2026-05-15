"""Workflow Engine — 상태 흐름 엔진.

역할: State Transition 정의 + 이벤트 발행.
제한: Notification Runtime과 직접 연결 금지.

철학:
  Workflow는 상태를 만든다
  Integrity는 상태를 평가한다
  Alert는 운영 중요도를 판단한다
  Notification은 전달한다
"""
