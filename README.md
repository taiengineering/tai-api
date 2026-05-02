# tai-api

## 네이버 지식iN 모니터링 (`naver_monitor.py`)

`taiengineering/taieng` 저장소의 `docs/TASK_NAVER_KIN_MONITOR.md`와 동일 목적 — **자동 게시/답변 로직은 포함하지 않습니다.** 지식iN **검색 API 조회**와 **Supabase 로그 적재**만 수행합니다.

### Supabase: `naver_kin_log` 테이블

Supabase SQL Editor에서 아래를 실행하세요. `naver_monitor.py`가 보내는 컬럼과 맞춰 두었습니다.

`question_link`에 **유일 제약**이 있어야 동일 질문 URL은 한 번만 저장됩니다(이후 `409`로 스킵).

```sql
-- gen_random_uuid() : PostgreSQL 13+ (Supabase 기본)
create table if not exists public.naver_kin_log (
  id uuid primary key default gen_random_uuid(),
  question_link text not null,
  question_title text,
  question_description text,
  search_keyword text not null,
  sort_mode text not null default 'date',
  api_total integer,
  item_index integer,
  raw_item jsonb,
  run_at timestamptz not null,
  constraint naver_kin_log_question_link_key unique (question_link)
);

create index if not exists naver_kin_log_run_at_idx
  on public.naver_kin_log (run_at desc);
create index if not exists naver_kin_log_search_keyword_idx
  on public.naver_kin_log (search_keyword, run_at desc);

comment on table public.naver_kin_log is '네이버 지식iN 검색 API 모니터링 로그 (읽기·적재 전용, 자동 게시 없음)';
```

크론에 쓰는 **Service Role** 키는 RLS를 우회할 수 있으니 배포·로그에 노출하지 마세요.

### 환경 변수

| 변수 | 필수 | 설명 |
| --- | --- | --- |
| `NAVER_CLIENT_ID` | 예 | 네이버 개발자센터 앱 Client ID |
| `NAVER_CLIENT_SECRET` | 예 | 네이버 개발자센터 앱 Client Secret |
| `SUPABASE_URL` | 예 | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | 예 | 서버 전용(크론) — insert용 |
| `NAVER_KIN_KEYWORDS` | 아니오 | 쉼표로 구분. 미설정 시 `산업안전,과태료,안전관리책임자` |
| `NAVER_KIN_DISPLAY` | 아니오 | 1~100, 기본 `30` |
| `NAVER_KIN_SORT` | 아니오 | `sim` / `date` / `point`, 기본 `date` |

### Railway 크론

Railway `railway.toml`의 `cronSchedule`은 **UTC** 기준입니다. **KST 09:00 = UTC 00:00** → `0 0 * * *`. 서비스는 **한 번 실행 후 종료**하는 형태에 맞게 스크립트가 exit 하도록 구성합니다.

### 로컬 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
python naver_monitor.py
```
