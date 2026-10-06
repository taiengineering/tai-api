# ENG_DOC_BOUNDARY_EVIDENCE

조사일: 2026-10-07
대상: 45cminc/doc (GitHub API로만 접근)

---

## Git Identity

| 항목 | 값 |
|---|---|
| current main SHA | `218091f6adc0895294ac6c9da74f565e557084ea` |
| last pushed | 2026-06-24T10:35:51Z |
| last commit message | `feat(docling): PaddleOCR 설치 추가` |
| 로컬 clone | NOT FOUND |
| 접근 방법 | GitHub CLI (gh api) |

---

## 레포지토리 구조 (top-level)

```
.env.example
.github/workflows/
.gitignore
BOUNDARY.md
Dockerfile
ENGINE_SPEC.md
README.md
docker/docling-ko/
docs/
package.json
runtime.manifest.json
runtime/
src/
```

### src/ 구조

```
src/
  archive/
  digitize/
    router.ts
    extractor/docling.ts
    v1-validator.ts
    v2-validator.ts
    doc-log.ts
    primitive-store.ts
    signal-emitter.ts
    storage.ts
    file-detector.ts
  health/
  index.ts
  render/
    render-api.ts
    render-engine.ts
  template/
    template-registry.ts
  trace/
    document-trace.ts
```

---

## 기능 상세

### digitize 기능

| 항목 | 값 |
|---|---|
| exists | YES |
| endpoint | POST /digitize |
| 구현 수준 | ACTUAL (fully implemented) |
| 처리 흐름 | multipart → V1 validate → SHA256 dedup → Storage upload → Docling extract → V2 validate → Primitive → Signal emit |

### Docling 연동

| 항목 | 값 |
|---|---|
| 구현 파일 | src/digitize/extractor/docling.ts |
| Docling URL | axios client → `POST {DOCLING_URL}/v1/convert/file` |
| default DOCLING_URL | `https://doc-docling-production.up.railway.app` |
| OCR engine | tesserocr |
| OCR 언어 | kor, eng |
| PaddleOCR | docker/docling-ko/Dockerfile에 포함 (CPU 버전) |
| Tesseract Korean tessdata | docker/docling-ko/Dockerfile에 포함 |

### render 기능

| 항목 | 값 |
|---|---|
| exists | YES (src/render/render-engine.ts) |
| pdf_renderer | PLACEHOLDER |
| docx_renderer | PLACEHOLDER |
| markdown_renderer | ACTUAL |
| json_renderer | ACTUAL |
| evidence_bundle_renderer | ACTUAL |

#### PDF/DOCX placeholder 코드 (실측)
```typescript
content = `[${outputType.toUpperCase()} placeholder] Template: ${template.name}, Data keys: ${Object.keys(req.data).join(', ')}`
// comment: "Placeholder — actual PDF/DOCX rendering requires libraries"
```

### Template Registry

| 항목 | 값 |
|---|---|
| 방식 | static hardcoded array (DB 없음) |
| 등록 템플릿 수 | 6 |
| 템플릿 목록 | tmpl-ops-incident, tmpl-ops-health, tmpl-gov-audit, tmpl-mkt-channel, tmpl-common-timeline, tmpl-common-snapshot |

---

## Gotenberg

| 항목 | 값 |
|---|---|
| Gotenberg client 코드 | NOT FOUND |
| Gotenberg 참조 | NONE |

---

## Railway 설정

| 항목 | 값 |
|---|---|
| railway.toml | NOT FOUND |
| railway.json | NOT FOUND |
| Dockerfile | EXISTS (port 3206, CMD ["node", "dist/index.js"]) |

---

## TAI Safe 문서 엔진과 관계

| 항목 | 값 |
|---|---|
| PDF 실제 renderer | PLACEHOLDER (45cminc/doc) vs ACTUAL Jinja2+Gotenberg (TAI Safe) |
| 공통 template store | NONE |
| 공통 DB | NONE |
| signal integration | src/digitize/signal-emitter.ts 존재 (TAI Safe와 연결 여부 UNCLEAR) |
| master plan 규정 | "eng:DOC는 디지털화/마이그레이션 보조 엔진으로만 사용" |

---

## 결론 (사실만)

- `45cminc/doc`의 PDF/DOCX renderer는 PLACEHOLDER 상태 (2026-06-24 기준)
- TAI Safe 문서 생성은 Jinja2+Gotenberg 경로 사용 (완전히 별도)
- digitize(OCR) 기능은 실제 구현 완료 상태
- Gotenberg 미사용
