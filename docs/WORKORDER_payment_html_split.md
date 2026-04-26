# payment.py HTML 분리 + 잔여 로직 분리 — Cursor 작업지시서 (2차)

> 선행 작업: STEP 0~5 완료 (helpers, schemas, payment_svc 분리, 15 tests pass)
> 현재 상태: `routers/payment.py` **62KB** — DEV_RULES 기준 15KB 초과
> 원인: HTML 인라인 문자열 3개 (~35KB) + 잔여 비즈니스 로직
> 브랜치: `dev` (main 직접 push 금지)

---

## 작업 A: HTML 템플릿 파일 분리 (최우선)

### A-1. 디렉토리 생성

```
templates/
templates/payment/
```

### A-2. HTML 파일 3개 생성

#### 파일 1: `templates/payment/pricing.html`

`routers/payment.py`에서 `_PRICING_HTML = """` 시작 ~ 다음 `"""` 끝까지의 내용을 **그대로** 복사.
`"""` 따옴표는 제외하고 HTML만 저장.

#### 파일 2: `templates/payment/result.html`

`routers/payment.py`에서 `_RESULT_HTML = """` 시작 ~ 다음 `"""` 끝까지의 내용을 **그대로** 복사.

#### 파일 3: `templates/payment/billing_terms.html`

`routers/payment.py`에서 `_BILLING_TERMS_HTML = """` 시작 ~ 다음 `"""` 끝까지의 내용을 **그대로** 복사.

### A-3. 로더 함수 추가

`services/payment_helpers.py`에 아래 함수 추가:

```python
import os as _os
from functools import lru_cache

_TEMPLATE_DIR = _os.path.join(_os.path.dirname(__file__), "..", "templates", "payment")

@lru_cache(maxsize=4)
def load_template(name: str) -> str:
    """템플릿 파일을 읽어 문자열로 반환. 최초 1회만 디스크 IO."""
    path = _os.path.join(_TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
```

### A-4. 라우터에서 인라인 HTML 삭제 + 로더 호출로 교체

`routers/payment.py`에서:

1. **삭제**: `_PRICING_HTML = """..."""`  변수 전체 (약 150줄)
2. **삭제**: `_RESULT_HTML = """..."""`  변수 전체 (약 30줄)
3. **삭제**: `_BILLING_TERMS_HTML = """..."""`  변수 전체 (약 170줄)

4. **import 추가**:
```python
from services.payment_helpers import load_template
```

5. **엔드포인트 교체** (3곳):

```python
# pricing
def payment_pricing_page():
    return HTMLResponse(content=load_template("pricing.html"), status_code=200)

# result
def payment_result_page():
    return HTMLResponse(content=load_template("result.html"), status_code=200)

# billing terms
def payment_billing_terms_page():
    return HTMLResponse(content=load_template("billing_terms.html"), status_code=200)
```

### A-5. 검증

```bash
pytest tests/test_payment_current.py tests/test_payment_helpers.py tests/test_payment_svc.py -v
wc -c routers/payment.py   # 30KB 이하
python -c "from routers.payment import router; print('OK')"
```

### A-6. 커밋

```
refactor: payment HTML 템플릿 3개 분리 → templates/payment/
```

---

## 작업 B: 잔여 비즈니스 로직 서비스 이전 (작업 A 완료 후)

### B-1. `services/payment_svc.py`에 함수 추가

```python
def process_card_success(payment: dict, auth_result: dict, paymethod: str) -> dict:
    """카드 결제 승인 성공 처리 — DB UPDATE + 계약 활성화.
    반환: {"qs_params": dict}"""

def process_vbank_issued(payment_id: str, order_id: str, auth_result: dict) -> dict:
    """가상계좌 발급 완료 처리.
    반환: {"qs_params": dict}"""

def process_auth_failure(payment_id: str, fail_msg: str, auth_result: dict) -> None:
    """승인 실패 처리."""

def create_vbank_record(body, sign_key: str) -> dict:
    """vbank_prepare의 DB INSERT + 서명 생성."""

def process_vbank_deposit(order_id: str, result_code: str, depositor: str, raw_data: dict) -> str:
    """vbank_noti의 입금확인 → 전체 처리. 반환: 'OK'"""
```

### B-2. 라우터 슬림화

각 엔드포인트는 HTTP 수신 → 서비스 호출 → 응답 반환 패턴만.

### B-3. 검증

```bash
pytest tests/test_payment_current.py tests/test_payment_helpers.py tests/test_payment_svc.py -v
wc -c routers/payment.py   # 15KB 이하
```

### B-4. 커밋

```
refactor: payment 잔여 비즈니스 로직 → payment_svc.py 이전
```

---

## 절대 하지 말 것

- HTML 내용을 수정하거나 포맷팅하지 말 것 — 100% 원본 그대로 복사
- `_PRICING_HTML` 변수를 삭제하지 않고 `load_template()`만 추가하지 말 것 — 반드시 변수 삭제
- 테스트 실행 없이 다음 단계로 넘어가지 말 것
- main에 직접 push하지 말 것 — dev 브랜치에 커밋

---

## 완료 기준

| 항목 | 기준 |
|------|------|
| `templates/payment/pricing.html` | 존재, HTML 원본 그대로 |
| `templates/payment/result.html` | 존재, HTML 원본 그대로 |
| `templates/payment/billing_terms.html` | 존재, HTML 원본 그대로 |
| `payment_helpers.py`에 `load_template()` | 존재, lru_cache 적용 |
| `routers/payment.py` | 인라인 HTML 변수 3개 없음 |
| `routers/payment.py` 크기 | 작업A 후 ~27KB, 작업B 후 ~15KB |
| 테스트 | 15개 전부 PASS |
| 서버 import | 성공 |
| 브랜치 | dev |
