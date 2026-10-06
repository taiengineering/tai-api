# RENDERER_INFRA_EVIDENCE

조사일: 2026-10-07
대상: Gotenberg service (taiengineering/tai-api main aa46bbb7)

---

## Gotenberg 통합 상세

### Integration A — services/document_engine/renderer.py (문서 템플릿용)

| 항목 | 값 |
|---|---|
| URL env var | `GOTENBERG_URL` |
| fallback | `http://gotenberg.railway.internal:3000` |
| transport | httpx.AsyncClient (비동기) |
| endpoint | `{GOTENBERG_URL}/forms/chromium/convert/html` |
| request params | paperWidth=8.27, paperHeight=11.69, marginTop/Bottom/Left/Right=0.4, printBackground=true |
| multipart key | `"index.html"` |
| callers | routers/document_engine.py (TBM), routers/compliance_report.py, services/document_engine/generator.py |
| production 최근 성공 증거 | UNVERIFIED — logs 미접근 |

### Integration B — services/gotenberg_svc.py (견적서용)

| 항목 | 값 |
|---|---|
| URL env var | `GOTENBERG_URL` |
| fallback | NONE (strict fail-closed — env 없으면 PdfRenderError 503) |
| transport | httpx.post (동기) |
| endpoint | `{GOTENBERG_URL}/forms/chromium/convert/html` |
| request params | preferCssPageSize=true, printBackground=true |
| multipart key | `"files"` |
| callers | services/member_quote_pdf_svc.py |
| production 최근 성공 증거 | documents 테이블 4건 (견적서 PDF, 가장 최근 2026-09-30) |

### Integration C — routers/diagnosis_report.py (진단 PDF용, inline)

| 항목 | 값 |
|---|---|
| URL env var | `GOTENBERG_URL` |
| fallback | `http://tai-gotenberg.internal:3000` (Integration A와 다름) |
| transport | httpx async inline |
| callers | routers/diagnosis_report.py, routers/diagnosis_proposal.py |

---

## Railway Gotenberg 서비스 (CORR-E)

| 항목 | 값 |
|---|---|
| Railway project | tai-api (7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b) |
| Gotenberg service 존재 여부 | NOT_ACCESSIBLE |
| renderer.py fallback hostname | `gotenberg.railway.internal` |
| diagnosis_report.py fallback hostname | `tai-gotenberg.internal` |

```
NOT_ACCESSIBLE
reason = Railway deployment/service API 접근 권한 부족
tool/access limitation = mcp__claude_ai_guri__list_deployments → UNAUTHORIZED
attempted evidence source = Railway GraphQL API (project 7c3ab53b, env 9dacb6f0)
fallback evidence = renderer.py hardcoded fallback hostname "gotenberg.railway.internal:3000"
                    — hostname 존재가 service 실행을 보장하지 않음
indirect evidence = documents 테이블 4건 (견적서 PDF, 2026-09-30 최근) — gotenberg_svc.py 경로 성공 확인
                    but: renderer.py 경로 (문서 템플릿) 성공 증거는 storage_path=NULL로 인해 미확인
```

---

## Railway Production Deployed Commit (CORR-E)

```
NOT_ACCESSIBLE
reason = Railway API token 권한 부족
tool/access limitation = mcp__claude_ai_guri__list_deployments → UNAUTHORIZED
attempted evidence source = Railway project 7c3ab53b, env 9dacb6f0
known = origin/main = 939ef60ba3c43f2ac0ff6a0256a787ebf05bd1aa
deployed_commit = NOT_CONFIRMED
```

---

## .env 설정 상태

| 항목 | 값 |
|---|---|
| .env.example 에 GOTENBERG_URL | 미문서화 (NOT PRESENT) |
| .env 에 GOTENBERG_URL | 로컬 값 UNVERIFIED |

---

## 실제 PDF 생성 성공 증거

| 경로 | 마지막 성공 | 증거 |
|---|---|---|
| 견적서 (gotenberg_svc.py) | 2026-09-30 | documents 테이블 4건 |
| TBM/Compliance (renderer.py) | UNVERIFIED | generated_document GENERATED 9건 — storage_path=NULL |
| document_generate (renderer.py) | UNVERIFIED | storage/log 접근 불가 |

---

## fallback 불일치 목록

| 위치 | fallback hostname |
|---|---|
| services/document_engine/renderer.py | `gotenberg.railway.internal:3000` |
| routers/diagnosis_report.py | `tai-gotenberg.internal:3000` |
| services/gotenberg_svc.py | NONE |
