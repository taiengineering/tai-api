# 엔진 모델 마스터 API 작업 지시서
## 날짜: 2026-03-30
## 대상: tai-api (`routers/engine_model.py`, `main.py`)

---

## PART 1. `routers/engine_model.py` 신규 + `main.py` 등록

### 목표

1. **`routers/engine_model.py`** 신규 생성  
   - FastAPI `APIRouter`  
   - Supabase 클라이언트: `from db.supabase_client import get_supabase`
2. **`main.py`** 에서 해당 라우터 import 후 `app.include_router(...)` 등록

### 라우터 규격

| 항목 | 값 |
|------|-----|
| `prefix` | `/engine-model` |
| `tags` | `["엔진모델마스터"]` |
| 대상 테이블 | `equipment_model_master` |

### 엔드포인트 (선언 순서: 고정 경로 → `/{id}`)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/engine-model/stats` | 전체 통계 |
| GET | `/engine-model/filters` | 필터용 옵션 목록 |
| GET | `/engine-model/list` | 목록 (페이지네이션·필터) |
| GET | `/engine-model/{model_id}` | 단건 상세 |
| PATCH | `/engine-model/{model_id}` | 수정 (허용 필드만) |

> `/{model_id}` 는 `/stats`, `/filters`, `/list` **이후**에 정의해 경로 충돌을 방지한다.

### `main.py` 등록 예시

```python
from routers.engine_model import router as engine_model_router
# ...
app.include_router(engine_model_router)
```

### 구현 상태

- **PART 1** 는 위 규격으로 `routers/engine_model.py` 및 `main.py` 반영 완료.

---

## PART 2. (후속)

프론트 `engine-model.html` 연동·추가 필드·배치 작업 등은 별도 지시서로 진행.
