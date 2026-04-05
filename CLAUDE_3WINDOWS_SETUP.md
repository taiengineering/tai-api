# Claude 3개 창 설정 가이드 (macOS)
**작성일: 2026-04-05 | 완료: TAI 단일 Git 저장소 구성**

---

## 📍 현재 상태
```
✅ ~/TAI/ (단일 Git 저장소)
  ├── .git/ (루트에 하나만)
  ├── 1-planning/
  ├── 2-backend/  (tai-api 파일 있음)
  ├── 3-frontend/ (tai-admin 파일 있음)
  └── claude-config.json
```

---

## 🎯 지금 할 것: 3개 창 설정

### **창1: TAI Planning (기획/메모리)**

#### Step 1: 새 Claude 창 열기
```
맥: Cmd + N
또는 claude.ai → 새 대화
```

#### Step 2: Settings 열기
```
우측 상단 ⚙️ (설정 아이콘)
→ "Settings" 클릭
```

#### Step 3: Connected Services 추가
```
"Connected services" 또는 "Connections" 탭 찾기
→ "+ Add" 또는 "Add Connection"
```

#### Step 4-1: GitHub MCP 추가
```
Service: GitHub (또는 MCP)
이름: github-tai
저장소: taiengineering/tai-api
인증: (기존 GitHub 계정 사용)

→ "Connect" 또는 "Save"
```

#### Step 4-2: Supabase MCP 추가
```
Service: Supabase
이름: supabase-tai
Project ID: xntdkrjhgcscmqctdzyo
인증: Service Role Key

→ "Connect" 또는 "Save"
```

#### Step 5: 작업 폴더 설정
```
Settings → General 또는 "Working Directory"
폴더: ~/TAI/1-planning/

(또는 새 대화 시작할 때 자동으로 설정)
```

✅ **창1 완료!**

---

### **창2: TAI Backend (백엔드 개발)**

#### Step 1-2: 새 Claude 창 열고 Settings 열기
```
Cmd + N → ⚙️ Settings
```

#### Step 3: Connected Services 추가
```
"Connected services" 탭
→ "+ Add"
```

#### Step 4-1: GitHub MCP 추가
```
Service: GitHub
이름: github-tai
저장소: taiengineering/tai-api
인증: (기존 GitHub 계정)

→ "Connect"
```

#### Step 4-2: Supabase MCP 추가
```
Service: Supabase
이름: supabase-tai
Project ID: xntdkrjhgcscmqctdzyo
인증: Service Role Key

→ "Connect"
```

#### Step 5: 작업 폴더 설정
```
폴더: ~/TAI/2-backend/
```

✅ **창2 완료!**

---

### **창3: TAI Frontend (프론트엔드 개발)**

#### Step 1-2: 새 Claude 창 열고 Settings 열기
```
Cmd + N → ⚙️ Settings
```

#### Step 3: Connected Services 추가
```
"Connected services" 탭
→ "+ Add"
```

#### Step 4-1: GitHub MCP 추가 (주의!)
```
Service: GitHub
이름: github-tai-admin  ← "admin" 포함!
저장소: taiengineering/tai-admin ← tai-admin (다름!)
인증: (기존 GitHub 계정)

→ "Connect"
```

#### Step 4-2: Supabase MCP 추가
```
Service: Supabase
이름: supabase-tai
Project ID: xntdkrjhgcscmqctdzyo
인증: Service Role Key

→ "Connect"
```

#### Step 5: 작업 폴더 설정
```
폴더: ~/TAI/3-frontend/
```

✅ **창3 완료!**

---

## 📋 설정 완료 체크리스트

### 창1 (기획)
- [ ] Settings → Connected Services 열음
- [ ] GitHub: `github-tai` 추가 (tai-api)
- [ ] Supabase: `supabase-tai` 추가
- [ ] 작업 폴더: `~/TAI/1-planning/`

### 창2 (백엔드)
- [ ] Settings → Connected Services 열음
- [ ] GitHub: `github-tai` 추가 (tai-api)
- [ ] Supabase: `supabase-tai` 추가
- [ ] 작업 폴더: `~/TAI/2-backend/`

### 창3 (프론트엔드)
- [ ] Settings → Connected Services 열음
- [ ] GitHub: `github-tai-admin` 추가 (tai-admin) ⚠️ 이름 주의!
- [ ] Supabase: `supabase-tai` 추가
- [ ] 작업 폴더: `~/TAI/3-frontend/`

---

## 🔐 Service Role Key 찾기 (Supabase)

```
1. https://app.supabase.com 로그인
2. 프로젝트: xntdkrjhgcscmqctdzyo 선택
3. Settings (좌측 메뉴)
4. "API" 탭
5. "Service Role Key" 복사
6. Claude Settings의 Supabase 인증 필드에 붙여넣기
```

---

## ✅ 완료 후 테스트

각 창에서:

```bash
# 터미널에서 확인
pwd  # 현재 폴더가 ~/TAI/[1-planning/2-backend/3-frontend/] 인지 확인

# Claude에서 MCP 사용 가능한지 확인
"GitHub 저장소 상태를 확인해줘"
"Supabase 테이블 목록을 보여줘"
```

---

## 💡 만약 Connected Services가 안 보이면?

```
Settings → 스크롤 내려가기
또는
"Connections", "Integrations" 탭 찾기
```

---

## 🚀 설정 완료 후

각 창에서 독립적으로 작업 가능:

**창1**: 기획 문서, SESSION_MEMORY.md 작성
**창2**: tai-api 코드 수정, DB 쿼리
**창3**: tai-admin HTML/Vue 수정, UI 디자인

모두 **같은 Git 저장소 (`~/TAI/.git`)**로 관리됨 ✓

---

## 📞 문제 해결

| 문제 | 해결 |
|------|------|
| Connected Services 버튼 없음 | 설정 페이지 스크롤 또는 다른 탭 확인 |
| GitHub 연결 안 됨 | GitHub 계정이 로그인되어 있는지 확인 |
| Supabase 연결 안 됨 | Service Role Key가 올바른지 확인 |
| 작업 폴더 설정 안 됨 | 폴더 경로가 `~/TAI/[폴더명]/` 형식인지 확인 |

---

**이제 시작하세요!** 🎯
