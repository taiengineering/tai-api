# MCP 다중 창 독립 연결 가이드
**작성일: 2026-04-03 | 목표: 3개 창에서 동시에 GitHub/Supabase MCP 사용**

---

## 🎯 현재 상황

```
❌ 창1 (TAI 기획) ←── MCP 점유 (GitHub 연결됨)
❌ 창2 (TAI 백엔드) ←── 대기 상태 (GitHub 미연결)
❌ 창3 (TAI 프론트엔드) ←── 대기 상태 (GitHub 미연결)
```

---

## ✅ 해결 방법 2: 별도 MCP 인스턴스 등록

### 📋 Step 1: 각 창에서 Settings 열기

**창1 (TAI 기획)**:
```
1. 창 우측 상단 ⚙️ Settings 클릭
2. "Connected services" 또는 "Connections" 찾기
3. 현재 활성 MCP 확인 (github-tai)
```

**창2 (TAI 백엔드)**:
```
1. 같은 경로에서 Settings 열기
2. 현재 상태: GitHub 미연결
```

**창3 (TAI 프론트엔드)**:
```
1. 같은 경로에서 Settings 열기
2. 현재 상태: GitHub 미연결
```

---

## 🔧 Step 2: 새로운 MCP 등록 (각 창별)

### 창2에 "GitHub TAI API" 등록

```
Connected Services → Add Connection
┌──────────────────────────────────┐
│ Service: GitHub (또는 MCP)        │
│ Name: github-tai-backend         │ ← 구분명
│ Scope: taiengineering/tai-api    │
│ Auth: (기존 토큰 재사용)           │
└──────────────────────────────────┘
✓ Connect
```

### 창3에 "GitHub TAI Admin" 등록

```
Connected Services → Add Connection
┌──────────────────────────────────┐
│ Service: GitHub (또는 MCP)        │
│ Name: github-tai-admin           │ ← 구분명
│ Scope: taiengineering/tai-admin  │
│ Auth: (기존 토큰 재사용)           │
└──────────────────────────────────┘
✓ Connect
```

---

## 📌 등록 후 각 창에서의 MCP 호출

### 창1 (기획) — 모든 리포 접근
```python
# 기존처럼 사용 (변경 없음)
from github_tai import list_issues
```

### 창2 (백엔드) — tai-api만 사용
```
tool_search(query="github create file") 
→ "github-tai-backend" 선택
→ owner: "taiengineering"
→ repo: "tai-api"
```

### 창3 (프론트엔드) — tai-admin만 사용
```
tool_search(query="github create file")
→ "github-tai-admin" 선택
→ owner: "taiengineering"
→ repo: "tai-admin"
```

---

## ⚡ Step 3: 즉시 적용 가능한 대안 (더 간단함)

Claude.ai UI의 MCP 설정이 복잡하면, **더 실용적인 방법**:

### 방안 A: 각 창을 "역할별 전문화"

| 창 | 역할 | MCP 사용 | 방식 |
|-----|------|---------|------|
| 창1 | 기획/메모리/문서 | GitHub (공용) | 활성 (기본) |
| 창2 | 백엔드 API 개발 | **비활성** | 필요시만 한번에 |
| 창3 | 프론트엔드 UI 개발 | **비활성** | 필요시만 한번에 |

**사용 패턴**:
```
창1 활성 중 (문서 작성) → 완료
  ↓
창1 MCP 비활성화 (Settings에서 Disconnect)
  ↓
창2 MCP 활성화 (Settings에서 Connect)
  ↓
창2 백엔드 작업 (fast context switch)
```

---

### 방안 B: 각 창을 "브라우저 프로필"로 분리

Chrome의 **프로필 기능** 사용:

```
Chrome → Settings → People → Add person

Profile 1: "TAI Planning" (Claude 창1)
  - hetto@kakao.com 로그인
  - MCP: GitHub (github-tai)

Profile 2: "TAI Backend" (Claude 창2)
  - hetto@kakao.com 로그인
  - MCP: GitHub (github-tai-backend) ← 별도 등록

Profile 3: "TAI Frontend" (Claude 창3)
  - hetto@kakao.com 로그인
  - MCP: GitHub (github-tai-admin) ← 별도 등록
```

각 프로필별 MCP 설정이 **완전히 독립적**

---

## 🎯 최종 권장사항

### **지금 바로 할 것** (5분)

1. **창2 Settings** → Connected Services
2. **Add** → GitHub MCP
3. **Name**: `github-tai-backend`
4. **Connect** (기존 토큰으로 재사용 가능)
5. 창3도 반복 (name: `github-tai-admin`)

### **불가능한 경우** (UI에서 지원 안 함)

**방안 A로 전환**: 각 창을 순차적으로 사용
- 창1 (기획) ← 항상 활성
- 창2 (백엔드) ← 필요시 MCP 켜기
- 창3 (프론트엔드) ← 필요시 MCP 켜기

---

## 📞 문제 해결

### "Connected Services에 GitHub가 없다"

```
Settings → Connections → Browse available
→ "GitHub" 또는 "MCP" 검색
→ Install / Enable
```

### "같은 계정으로 여러 개 등록할 수 없다"

```
→ 각 창마다 다른 GitHub 토큰 사용
  또는
→ 방안 A (순차 사용)로 전환
```

### "MCP 등록 후에도 하나만 활성화됨"

```
→ 이는 정상 동작 (MCP 서버 제한)
→ 하지만 빠르게 전환 가능 (5초)
→ 방안 A 권장
```

---

## 🔄 추천 워크플로우

```python
# 창1 (항상 활성)
claude_window1 = "기획/메모리/문서 작성"

# 창2 (필요시 MCP 켜기)
def window2_backend_work():
    mcp.connect("github-tai-backend")  # 켜기
    # 백엔드 파일 작성
    github.create_file(repo="tai-api", ...)
    mcp.disconnect()  # 끄기

# 창3 (필요시 MCP 켜기)
def window3_frontend_work():
    mcp.connect("github-tai-admin")  # 켜기
    # 프론트엔드 파일 작성
    github.create_file(repo="tai-admin", ...)
    mcp.disconnect()  # 끄기
```

---

## ✨ 설정 체크리스트

- [ ] 창1: Settings → Connected Services 확인 (github-tai)
- [ ] 창2: Settings → Add Connection (github-tai-backend)
- [ ] 창3: Settings → Add Connection (github-tai-admin)
- [ ] 각 창에서 독립적으로 tool_search 호출 테스트
- [ ] 필요시 MCP 연결/해제 순환 테스트
