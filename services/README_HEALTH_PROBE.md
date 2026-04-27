# 서비스 헬스체크 프로브 등록 가이드

## 새 서비스에 프로브 추가하기

서비스 파일 하단에 아래 패턴만 추가하면 `/health/deep`에 자동 반영됩니다.

```python
from services.health_registry import register_probe

async def _probe_my_service():
    # 정상: return {"key": "value"}
    # 경고: return {"status": "warn", "detail": "경고 사유"}
    # 실패: raise RuntimeError("에러 내용")
    return {"items_count": 42}

register_probe(
    "my_service",
    _probe_my_service,
    critical=True,
    desc_ko="내 서비스",
)
```

## yml 수정 필요 없음

`register_probe` 호출만으로 `/health/deep`에 자동 등록됩니다.

## 한글 에러 메시지 추가

`services/health_registry.py`의 `ERROR_MESSAGES_KO`에 키를 추가합니다.

```python
ERROR_MESSAGES_KO["my_service"] = "내 서비스가 응답하지 않습니다. OOO를 확인하세요."
```
