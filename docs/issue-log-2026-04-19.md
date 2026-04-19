# 이슈 로그 — 2026-04-19

---

## 이슈#2 (해결): /transform 엔드포인트 미존재

**발견:** JS 코드에서 `fetch(\`${API}/anonymous-diagnosis/${token}/transform\`)` 호출  
**원인:** 백엔드에 `/transform` 엔드포인트 없음 → 404  
**결정:** JS 수정 없이 백엔드에서 처리 (목적이 `/{token}`과 다름)
- `/{token}`: 인증 조건에 따라 partial/full 조건부 반환
- `/{token}/transform`: 항상 표준 스키마 반환 (인증 불필요)

**해결:** `anonymous_diagnosis.py`에 `GET /{token}/transform` 추가  
커밋: `cf08b6ba`

---

## 이슈: BE-10 오타 및 보안 문제 5건

**발견:** 기획창 코드 리뷰 (`docs/fix-be10-review.md`)  
**내용:**

| # | 분류 | 상세 |
|---|---|---|
| FIX-1 | 오타 | "면접" → "면책" 8곳 |
| FIX-2 | 문구 | DISCLAIMER_TEXT 확정 문구 미적용 |
| FIX-3 | 오타 | 가격판정 설명 "으로" → "로" 4곳, "권로" → "으로" 2곳 |
| FIX-4 | 인코딩 | callback docstring 깨짐 문자 |
| FIX-5 | 보안 | CI 평문을 DB에 저장하는 문제 |

**해결:** diagnosis_integrated.py v1.0.1  
커밋: `ae849a39`

---

## 이슈: API 서버 과부하 (대량 업데이트 시 서버 다운)

**현상:** 대량 업데이트(법령엔진 rule 비활성화, 일정 재생성 등) 진행 시 서버 느려짐 또는 다운  
**원인 3가지:**
1. supabase-py가 동기(sync) 클라이언트 → FastAPI thread 풀 고갈
2. `get_supabase()` 매 호출마다 새 연결 → Supabase connection pool 초과
3. Fly.io shared-cpu-1x (256MB) → 대량 JSONB 적재 시 OOM

**청크 처리의 문제점:**
- supabase-py에서 `UPDATE + .in_()` 미지원
- asyncio.sleep()이 엔드포인트 응답 블로킹
- 트랜잭션 없어 부분 실패 시 DB 불일치 위험
- APScheduler 중복 실행 시 race condition

**권장 해결책:**
- 단기: `fly scale memory 512` (OOM 해소)
- 중기: 대량 작업은 `BackgroundTasks`로 분리 → 즉시 응답
- 중기: 다단계 트리 순회를 재귀 쿼리 → PostgreSQL CTE 한 방으로
- 장기: CRUD → Supabase PostgREST Direct (이미 계획 중)

**즉시 위험 지점:** law_rule_generator, schedule_pipeline, precedents/collect 루프

**상태:** 미해결 (하드웨어 증설 없이 코드 패턴 변경 필요)
