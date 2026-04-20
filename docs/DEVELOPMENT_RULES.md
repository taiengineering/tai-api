# 개발 규칙 (2026-04-20 확정)

1. main push → Railway 자동배포 (staging 없음)
2. /health 절대 503 금지 (200 고정, 실패시 "degraded")
3. 200줄+ 파일 MCP 수정 금지 → Cursor/Claude Code 사용
4. `from db.supabase_client import get_supabase`
5. `git checkout origin/dev` 전 `git fetch` 필수
6. Branch protection → 터미널 직접 push 안됨, admin MCP 필요
7. dev → PR → main → 자동배포 흐름 (긴급시 admin MCP로 main 직접 push)
8. 장시간 API 호출(Sonnet 등) → BackgroundTasks 필수, 동기 처리 금지
9. 크론 엔드포인트 미구현 시 is_active=false로 비활성화
10. process_equipment_map: MUST+CORE만 유지 (OPTIONAL/REFERENCE 삭제됨)
