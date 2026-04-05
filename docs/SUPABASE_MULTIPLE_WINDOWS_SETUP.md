# Supabase MCP 다중 창 설정 가이드
**작성일: 2026-04-05 | Supabase는 GitHub와 다릅니다!**

---

## 📌 GitHub vs Supabase 차이

| 특성 | GitHub MCP | Supabase MCP |
|-----|-----------|-------------|
| **저장소** | 여러 개 (tai-api, tai-admin 등) | **단일** (xntdkrjhgcscmqctdzyo) |
| **다중 등록** | ✅ 필요함 | ❌ 불필요 |
| **다중 창 동시 접근** | 별도 인스턴스 필요 | 자동 지원 |
| **연결 방식** | "저장소별" | "프로젝트별" |

---

## ✅ Supabase 다중 창 설정 (매우 간단!)

### Step 1: 모든 창에서 **같은** Supabase MCP 등록

**창1 (기획)**:
```
Settings → Connected Services → Add
┌─────────────────────────────┐
│ Service: Supabase           │
│ Name: supabase-tai          │ ← 공용명
│ Project: xntdkrjhgcscmqctdzyo │
│ Auth: (토큰 입력)            │
└─────────────────────────────┘
```

**창2 (백엔드)**:
```
Settings → Connected Services → Add
┌─────────────────────────────┐
│ Service: Supabase           │
│ Name: supabase-tai          │ ← 같은 이름!
│ Project: xntdkrjhgcscmqctdzyo │
│ Auth: (같은 토큰)            │
└─────────────────────────────┘
```

**창3 (프론트엔드)**:
```
Settings → Connected Services → Add
┌─────────────────────────────┐
│ Service: Supabase           │
│ Name: supabase-tai          │ ← 같은 이름!
│ Project: xntdkrjhgcscmqctdzyo │
│ Auth: (같은 토큰)            │
└─────────────────────────────┘
```

---

## 🎯 왜 Supabase는 별도 등록이 필요 없을까?

**GitHub의 경우**:
```
창1이 tai-api에 접근 중
창2가 tai-admin에 접근하려면 → 다른 리포이므로 별도 MCP 필요
```

**Supabase의 경우**:
```
창1이 DB 테이블 A에 접근 중
창2가 DB 테이블 B에 접근하려면 → 같은 프로젝트이므로 자동 가능!
```

**데이터베이스는 기본적으로 다중 동시 연결을 지원합니다.**

---

## 💡 각 창에서 독립적으로 사용

### 창1: 기획 문서 작성
```python
# 예: legal_rules 테이블 조회
result = supabase.execute_sql(
    "SELECT COUNT(*) FROM master_building_legal_rules"
)
# 창2, 창3와 동시 실행 가능!
```

### 창2: 백엔드 데이터 업데이트
```python
# 동시에 다른 테이블 업데이트
supabase.execute_sql(
    "UPDATE master_building_legal_rules SET condition_code = 'xxx' WHERE id = 'yyy'"
)
# 창1, 창3과 동시 실행 가능!
```

### 창3: 프론트엔드 스키마 확인
```python
# 동시에 스키마 조회
result = supabase.execute_sql(
    "SELECT * FROM information_schema.columns WHERE table_name = 'master_building_legal_rules'"
)
# 창1, 창2와 동시 실행 가능!
```

---

## ⚙️ Supabase 토큰 확인

### Service Role Key (권장)
```
Supabase Dashboard
→ Project Settings
→ API
→ "Service Role Key" 복사
→ 모든 창에서 동일하게 사용
```

### Anon Key (제한적)
```
비추천 - 보안 위험
```

---

## ✅ 최종 설정 체크리스트

- [ ] 창1: Settings → Connected Services → Supabase 추가
- [ ] 창2: Settings → Connected Services → Supabase 추가 (같은 이름)
- [ ] 창3: Settings → Connected Services → Supabase 추가 (같은 이름)
- [ ] 모든 창에서 같은 프로젝트 ID 사용: `xntdkrjhgcscmqctdzyo`
- [ ] 모든 창에서 같은 Service Role Key 사용
- [ ] tool_search("supabase execute") 각 창에서 테스트

---

## 🚀 다중 창 동시 사용 패턴

```
창1 (기획) ─┐
           ├─→ 같은 Supabase 프로젝트 (xntdkrjhgcscmqctdzyo)
창2 (백엔드) ┤
           ├─→ 다중 동시 쿼리 자동 지원 (PostgreSQL)
창3 (프론트엔드) ┘

트랜잭션 격리 (ACID):
- 창1의 UPDATE A 중 → 창2가 SELECT B 가능
- 창3의 INSERT C 중 → 창1, 창2가 읽기 가능
- 동시성 충돌 자동 처리 (DB가 관리)
```

---

## 📌 주의사항

### ✅ 안전
```python
# 각 창이 다른 테이블을 조작
창1: UPDATE legal_obligations ...
창2: UPDATE factory_diagnosis_results ...
창3: SELECT * FROM master_building_legal_rules ...
→ 동시 실행 안전 ✓
```

### ⚠️ 위험
```python
# 같은 행을 동시에 수정
창1: UPDATE legal_rules SET status = 'APPROVED' WHERE id = 'X'
창2: UPDATE legal_rules SET status = 'REJECTED' WHERE id = 'X'
→ Last-write-wins (중복 업데이트 발생 가능)
→ 해결: 트랜잭션 또는 낮은 격리 수준 사용
```

---

## 🎯 권장 워크플로우

```
## 동시에 안전하게 작업
창1 (기획):
  → condition_code 추출 전략 작성
  → docs/HAIKU_CONDITION_EXTRACT_TASK.md 업데이트

창2 (백엔드):
  → master_building_legal_rules 데이터 확인
  → rule_type_code 통계 조회

창3 (프론트엔드):
  → form_code 매핑 상태 조회
  → UI 레이아웃 스키마 확인

## 모두 **동시에** Supabase 접근 가능 ✓
```

---

## 📞 문제 해결

### "연결이 안 됨"
```
1. Service Role Key 확인 (올바른지)
2. 프로젝트 ID 확인: xntdkrjhgcscmqctdzyo
3. Supabase Dashboard 상태 확인
```

### "다른 창의 쿼리가 보이지 않음"
```
→ 정상 동작! (각 창은 독립적 세션)
→ 필요시 수동으로 새로고침
```

### "쿼리 실패"
```
→ 권한 부족: Service Role Key 사용 확인
→ 테이블 없음: 마이그레이션 확인
```
