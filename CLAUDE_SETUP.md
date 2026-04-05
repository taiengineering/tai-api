# TAI Engineering - Claude 프로젝트 설정 가이드

## 🎯 빠른 시작 (3창 설정)

### 1️⃣ MCP 설정 확인
모든 창에서 아래 설정을 참고하세요:
```
📁 .claude/mcp-config.json
```

### 2️⃣ 각 창 설정

#### 창1 (기획/메모리)
```json
{
  "name": "TAI Planning",
  "mcps": ["github-tai", "supabase-tai"],
  "usage": "전략 문서, 세션 메모리, 작업 계획"
}
```

**Settings에서**:
- ✅ GitHub MCP: `github-tai` (taiengineering/tai-api)
- ✅ Supabase MCP: `supabase-tai` (xntdkrjhgcscmqctdzyo)

---

#### 창2 (백엔드 개발)
```json
{
  "name": "TAI Backend",
  "mcps": ["github-tai", "supabase-tai"],
  "usage": "FastAPI 개발, legal_engine, 데이터베이스 작업"
}
```

**Settings에서**:
- ✅ GitHub MCP: `github-tai` (taiengineering/tai-api)
- ✅ Supabase MCP: `supabase-tai` (xntdkrjhgcscmqctdzyo)

---

#### 창3 (프론트엔드 개발)
```json
{
  "name": "TAI Frontend",
  "mcps": ["github-tai-admin", "supabase-tai"],
  "usage": "Vue HTML, 어드민 패널, UI 개발"
}
```

**Settings에서**:
- ✅ GitHub MCP: `github-tai-admin` (taiengineering/tai-admin)
- ✅ Supabase MCP: `supabase-tai` (xntdkrjhgcscmqctdzyo)

---

## 🔐 환경 변수 (필요시)

`.env.local` (로컬 전용, Git 무시):
```env
CLAUDE_GITHUB_TOKEN=ghp_xxxxxxxxxxxx
CLAUDE_SUPABASE_KEY=eyJhbGc...
CLAUDE_SUPABASE_PROJECT=xntdkrjhgcscmqctdzyo
```

---

## 📊 MCP 매핑 정보

### GitHub MCP

**github-tai** (Backend)
```
Organization: taiengineering
Repository: tai-api
Branch: main
Use: legal_engine.py, contract_kmong.py, engine_document.py
```

**github-tai-admin** (Frontend)
```
Organization: taiengineering
Repository: tai-admin
Branch: main
Use: HTML, Vue components, admin pages
```

---

### Supabase MCP (공용)

```
Project ID: xntdkrjhgcscmqctdzyo
Service: PostgreSQL Database
Auth: Service Role Key (모든 창에서 동일)

# 3개 창 모두 같은 프로젝트 접근 가능
창1 + 창2 + 창3 → 동시 쿼리 가능
```

---

## ✅ 설정 체크리스트

### 창1 설정
- [ ] Settings → Connected Services
- [ ] GitHub: `github-tai` 추가
- [ ] Supabase: `supabase-tai` 추가

### 창2 설정
- [ ] Settings → Connected Services
- [ ] GitHub: `github-tai` 추가
- [ ] Supabase: `supabase-tai` 추가

### 창3 설정
- [ ] Settings → Connected Services
- [ ] GitHub: `github-tai-admin` 추가
- [ ] Supabase: `supabase-tai` 추가

---

## 🚀 자주 사용하는 명령어

### 백엔드 작업 (창2)
```bash
# 규칙 데이터 확인
supabase:execute_sql → "SELECT COUNT(*) FROM master_building_legal_rules"

# 파일 생성
github-tai:create_or_update_file → tai-api/main

# 다중 파일 푸시
github-tai:push_files → tai-api/main
```

### 프론트엔드 작업 (창3)
```bash
# 어드민 페이지 생성
github-tai-admin:create_or_update_file → tai-admin/main

# HTML/Vue 업데이트
github-tai-admin:create_or_update_file → site/full-version/html
```

### 공용 작업 (창1, 2, 3)
```bash
# DB 쿼리 (모든 창에서 가능)
supabase:execute_sql → 동시 실행 안전

# 문서 작성 (GitHub)
github-tai:create_or_update_file → docs/SESSION_MEMORY.md
```

---

## 📝 참고 문서

- 🔗 [MCP 다중 창 설정 가이드](docs/MCP_MULTIPLE_WINDOWS_SETUP.md)
- 🔗 [Supabase 다중 창 설정](docs/SUPABASE_MULTIPLE_WINDOWS_SETUP.md)
- 🔗 [세션 메모리](docs/SESSION_MEMORY.md)
- 🔗 [다음 작업 프롬프트](docs/NEXT_SESSION_PROMPT.md)

---

## 💡 팁

**만약 설정이 리셋되면?**
```
1. 이 파일 (.claude/mcp-config.json) 확인
2. 각 창의 Settings에서 재입력
3. 또는 이 README 참고해서 빠르게 복구
```

**동시에 같은 DB 행을 수정하면?**
```
→ Last-write-wins (나중 수정이 덮어씀)
→ 해결: 다른 테이블/행 작업으로 분산
```

---

**설정 완료 후 3개 창에서 독립적으로 작업하세요!** ✅
