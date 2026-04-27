# 다음 세션 프롬프트

아래 내용을 다음 기획창 세션에 그대로 붙여넣기:

---

## Supabase 서울 이전 마무리 작업

### 현재 상태
- API (`api.taieng.co.kr`) → 서울 DB 연결 완료, `/health` healthy ✅
- 새 Supabase: `vwlahtguyggrhvslabax` (서울 ap-northeast-2)
- 기존 Supabase: `xntdkrjhgcscmqctdzyo` (싱가포르) — 아직 삭제하지 말 것

### 작업 1: Edge Function Secrets 복사
기존 프로젝트(https://supabase.com/dashboard/project/xntdkrjhgcscmqctdzyo/settings/functions)에서
새 프로젝트(https://supabase.com/dashboard/project/vwlahtguyggrhvslabax/settings/functions)로
아래 시크릿 복사:
- MESSAGEME_API_KEY
- MESSAGEME_SENDER
- TAI_INTERNAL_KEY
- KMA_SERVICE_KEY
- LAW_API_OC (값: taieng)
- TAI_COLLECT_SECRET

⚠️ 기존 프로젝트에서 시크릿 값이 마스킹되어 보이지 않으면 Railway 환경변수에서 동일 값 확인 가능

### 작업 2: 프론트엔드 Supabase URL 교체
tai-admin 레포에서 구 프로젝트 ID를 새 ID로 교체:
```bash
grep -r "xntdkrjhgcscmqctdzyo" --include="*.html" --include="*.js" -l
```
찾은 파일 전부에서:
`xntdkrjhgcscmqctdzyo` → `vwlahtguyggrhvslabax`

taieng (마케팅 사이트) 레포도 동일하게 검색+교체

### 작업 3: Storage 파일 이전 (선택)
- 51개 파일 (diagrams SVG 25개 등)
- 서비스 운영 필수는 아니지만 SVG 다이어그램이 깨질 수 있음
- Supabase CLI로 다운로드/업로드 또는 대시보드에서 수동 복사

### 작업 4: 정리
- Claude 프로젝트 설정에서 Supabase MCP 프로젝트 ID → vwlahtguyggrhvslabax 교체
- 기존 프로젝트 IPv4 비활성화 ($4/월 절약)
- 1주일 후 기존 프로젝트 삭제

### 작업 5: 오픈 전 E2E 플로우 검증
- 법령진단 → 점검세트 → 스케줄 → 작업자 체크리스트 E2E 연결 검증
- 이창은 페르소나 UX 버그 3건 수정
- weather.py 기상청 API 연동 완료
