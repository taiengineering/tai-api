# 문서 엔진 아키텍처 — TAI Safe

> 작성일: 2026-04-30
> 핵심 원칙: "빈 양식을 파는 게 아니라, 사용자가 매일 입력한 데이터가 법정 문서로 자동 변환되는 엔진"

---

## 1. 흐름

```
사용자 매일 입력 (점검·TBM·교육)
       ↓
  TAI DB에 데이터 축적
       ↓
  engine-document에서 [생성하기] 클릭
       ↓
  Backend: DB 데이터 조회 → HTML 템플릿에 주입
       ↓
  미리보기 (브라우저 HTML 렌더링)
       ↓
  [확인] → Gotenberg PDF 변환 → 다운로드
       ↓
  B~D등급: 티켓 차감
```

## 2. 등급별 흐름 차이

| 등급 | 추가 입력 | 티켓 | 흐름 |
|------|----------|------|------|
| A (29건) | 없음 | 0 | 데이터 자동 주입 → 미리보기 → PDF |
| B (49건) | 2~5 필드 | 10매 | 자동 주입 + 입력폼 → 미리보기 → PDF |
| C (32건) | AI 초안 + 검토 | 30매 | AI 텍스트 생성 + 사용자 검토 → PDF |
| D (25건) | 관공서 양식 매핑 | 50매 | 자동 주입 + 양식 필드 → PDF |
| X (44건) | - | - | TAI 범위 밖 (외부기관 안내) |

## 3. 기술 구조

### 3-1. HTML 템플릿

위치: `templates/documents/{doc_id}.html`
패턴: Jinja2 변수 (`{{ factory.name }}`, `{% for item in items %}`)
용도: 미리보기(브라우저) + PDF 생성(Gotenberg) 동일 파일 사용

### 3-2. 백엔드 API

```
# 미리보기 (HTML 반환)
GET /document-forms/{doc_id}/preview
  ?factory_id=xxx
  &date_from=2026-04-01
  &date_to=2026-04-30

# PDF 생성 (Gotenberg → PDF 반환)
POST /document-forms/{doc_id}/generate
  Body: { factory_id, date_from, date_to, additional_data: {} }
  → 티켓 차감 → PDF 반환
```

### 3-3. 데이터 매핑 레지스트리

`document_forms` 테이블의 `existing_data` 컬럼이 데이터 소스를 정의:
- `inspections` → safety_inspections + safety_inspection_results
- `TBM모듈` → tbm_meetings + tbm_attendees
- `workers/교육모듈` → education_history + worker_registry
- `factory` → factories
- `법령엔진` → factory_diagnosis_results + master_legal_inspection_rules

각 doc_id별 데이터 패처(fetcher)를 서비스 레이어에 구현:
```python
# services/document_engine/fetchers/
base_fetcher.py          # 공통 인터페이스
tbm_fetcher.py           # TBM 기록
inspection_fetcher.py    # 점검일지/체크리스트
education_fetcher.py     # 교육일지
```

### 3-4. 추가 입력 처리 (B~D등급)

`document_forms.additional_input` 컬럼이 필요 필드를 정의.
프론트에서 입력폼 동적 생성 → 사용자 입력 → `additional_data` 로 backend 전달.

## 4. 구현 순서 (MVP)

### Phase 1: A등급 핵심 5건 (추가 입력 없음)
1. DOC-OSH-056 TBM 기록 ← **1호 프로토타입**
2. DOC-OSH-007 안전점검일지
3. DOC-OSH-006 안전보건교육일지
4. DOC-OSH-017 점검표(체크리스트)
5. DOC-CON-006 공사일지

### Phase 2: B등급 핵심 5건 (소량 추가 입력)
6. DOC-OSH-013 작업허가서
7. DOC-OSH-045 보호구 지급대장
8. DOC-OSH-015 안전보건협의체 회의록
9. DOC-OSH-042 위험성평가 개선조치계획서
10. DOC-CON-008 작업계획서(고위험작업)

### Phase 3: C등급 (AI 초안)
11. DOC-OSH-002 위험성평가서
12. DOC-OSH-001 안전보건관리규정
13. DOC-SERA-001 안전보건관리체계 구축계획서

## 5. 인앱 판매 흐름

```
[생성하기] 클릭
  → A등급: 바로 미리보기 → PDF
  → B~D등급: 잔여 티켓 확인
    → 충분 → 추가 입력(있으면) → 미리보기 → [확인] → 티켓 차감 → PDF
    → 부족 → 티켓 구매 페이지 → 결제 → 돌아와서 생성
```

## 6. 파일 구조

```
tai-api/
  templates/
    documents/
      DOC-OSH-056.html     # TBM 기록
      DOC-OSH-007.html     # 안전점검일지
      DOC-OSH-006.html     # 교육일지
      ...
  services/
    document_engine/
      __init__.py
      renderer.py           # HTML 렌더링 + Gotenberg PDF
      fetchers/
        __init__.py
        base_fetcher.py
        tbm_fetcher.py
        inspection_fetcher.py
        education_fetcher.py
  routers/
    document_engine.py      # /document-forms/{doc_id}/preview, /generate
```
