# 작업지시서: diagnosis_report.py Gotenberg 전환

## 목적
`routers/diagnosis_report.py`의 PDF 엔진을 **xhtml2pdf → Gotenberg**(Chromium)로 교체.
`routers/diagnosis_proposal.py` v2.1.0과 동일한 패턴 적용.

## 현재 상태
- `diagnosis_report.py` v1.0.1 — xhtml2pdf 사용 중 → PDF 깨짐
- `diagnosis_proposal.py` v2.1.0 — Gotenberg 전환 완료 → 정상 동작
- Gotenberg 서버: `tai-gotenberg.fly.dev` (Fly.io, .internal DNS 안 됨)

## 변경 대상 파일
- `routers/diagnosis_report.py` (14KB, 약 350줄)

## 변경 사항

### 1. 상단 import 및 상수 추가
```python
import httpx  # 추가
from fastapi.responses import Response, RedirectResponse, StreamingResponse  # StreamingResponse 추가

GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://tai-gotenberg.internal:3000")
```

### 2. `_html_to_pdf()` 함수 교체
기존 (삭제):
```python
def _html_to_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    html = _replace_css_vars(html)
    buf = io.BytesIO()
    result = pisa.pisaDocument(...)
    return buf.getvalue()
```

신규 (교체) — `diagnosis_proposal.py`의 `_generate_pdf()`와 동일:
```python
async def _generate_pdf(html: str) -> bytes:
    """Gotenberg Chromium PDF 엔진으로 HTML → PDF 변환."""
    url = f"{GOTENBERG_URL}/forms/chromium/convert/html"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            files={"files": ("index.html", html.encode("utf-8"), "text/html")},
            data={
                "paperWidth": "8.27",
                "paperHeight": "11.69",
                "marginTop": "0",
                "marginBottom": "0",
                "marginLeft": "0",
                "marginRight": "0",
                "printBackground": "true",
                "scale": "1",
            },
        )
    if response.status_code != 200:
        log.error(f"[REPORT PDF] Gotenberg 오류: {response.status_code} {response.text[:200]}")
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: Gotenberg {response.status_code}")
    return response.content
```

### 3. 삭제할 코드
- `_replace_css_vars()` 함수 전체 삭제
- `_CSS_VAR_MAP` 딕셔너리 전체 삭제
- `from xhtml2pdf import pisa` 관련 코드 전체 삭제

### 4. 엔드포인트 async 전환
기존:
```python
@router.get("/report-pdf/{public_token}")
def get_paid_report_pdf(public_token: str):
```

변경:
```python
@router.get("/report-pdf/{public_token}")
async def get_paid_report_pdf(public_token: str):
```

### 5. PDF 생성 호출부 변경
기존:
```python
    try:
        pdf_bytes = _html_to_pdf(html)
    except HTTPException:
        raise
    except Exception as e:
        ...
```

변경:
```python
    try:
        pdf_bytes = await _generate_pdf(html)
    except HTTPException:
        raise
    except Exception as e:
        log.error("[REPORT PDF] PDF 변환 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF 변환 실패: {e}")
```

### 6. Storage 캐싱 (선택사항)
proposal처럼 Storage 캐싱 추가 가능하나, report는 매번 최신 데이터 반영 필요할 수 있으므로 직접 스트리밍 유지 가능.

### 7. 버전 업데이트
```python
VERSION = "2.0.0"
```

docstring:
```python
"""
routers/diagnosis_report.py — v2.0.0

v2.0.0 (2026-04-20):
  - xhtml2pdf → Gotenberg Chromium PDF 엔진 전환
  - _replace_css_vars() 제거 (Gotenberg는 CSS 변수 지원)
v1.0.1 (2026-04-19):
  - xhtml2pdf CSS 변수 치환
v1.0.0 (2026-04-18):
  - 최초 생성
"""
```

## 참조 파일
- `routers/diagnosis_proposal.py` v2.1.0 — Gotenberg 패턴 참조 (특히 `_generate_pdf()` 함수)
- `templates/diagnosis_report_paid.html` — 템플릿 파일 (변경 불필요)

## 환경변수
- `GOTENBERG_URL` — 이미 Fly.io secrets에 등록됨 (tai-gotenberg.fly.dev)

## 테스트
```bash
# 서버 warm-up
curl https://api.taieng.co.kr/

# 테스트 토큰으로 PDF 생성
curl -s -o /tmp/test-report.pdf -w "HTTP %{http_code}\n" \
  "https://api.taieng.co.kr/diagnosis/report-pdf/e2e-ind-paid-c1269589a61e61091c8d"

# PDF 열기
open /tmp/test-report.pdf
```

## 커밋
- 브랜치: `dev`
- 메시지: `fix(report): xhtml2pdf → Gotenberg Chromium PDF 엔진 전환 (v2.0.0)`

## 주의사항
1. `import io` 유지 (StreamingResponse fallback에서 사용)
2. `from db.supabase_client import get_supabase` 유지
3. 엔드포인트를 `async def`로 변경하는 것 잊지 말 것
4. `_render_html()` 함수는 변경 불필요 (Jinja2 렌더링은 동일)
5. `_CSS_VAR_MAP`과 `_replace_css_vars` 완전 삭제 — Gotenberg(Chromium)은 CSS 변수 지원
