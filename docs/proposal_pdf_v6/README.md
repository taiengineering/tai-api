# 기안 PDF 개편 구현 핸드오프 문서 (v6 기반)

**작성일:** 2026-04-19
**작업 브랜치:** `dev`
**PR 대상:** `main` (머지 후 자동 배포)
**관련 이슈:** tai-api #4 (기안 PDF 내용 수정)
**참조 Mockup:** `/mnt/user-data/outputs/proposal_mockup_v6.html`

---

## 🎯 A. 작업 개요

### A-1. 배경
현행 `routers/diagnosis_proposal.py` + `templates/proposal_pdf.html`은 **TAI SaaS 플랜 영업자료** 성격이 강함. 고객사의 실제 사용 맥락은 **"무료 진단을 받은 안전관리자가 경영진에게 유료 정밀 진단 승인을 받기 위한 품의서의 첨부 근거자료"**. 따라서 PDF의 포지션을 재정의하고 콘텐츠를 전면 교체해야 함.

### A-2. 목적
기안 PDF를 **"품의서 첨부용 분석 보고서"**로 재포지셔닝:
- ❌ 결재란 없음 (고객사 품의서가 결재받음)
- ❌ TAI SaaS 영업 내용 제거 (이건 별도 건)
- ✅ 법적 리스크 분석 결과 객관 제시
- ✅ 유료 정밀 진단의 비용·산출물 안내
- ✅ "관공서 안전감독 시 활용 가능" 전환 포인트 추가

### A-3. 완료 기준
1. 3개 섹터(INDUSTRY / BUILDING / CONSTRUCTION) 기안 PDF 정상 렌더링
2. `penalty_sum` 합산 계산 정상 동작
3. Supabase Storage 캐싱 로직 동작 (첫 생성 → 저장, 재요청 → 302 redirect)
4. `GET /diagnosis/proposal-pdf/{public_token}` 엔드포인트 200/302 응답 확인

---

## 📐 B. v6 설계 명세

### B-1. 페이지 구조 (3페이지)

#### P1: 분석 보고서 표지 + 진단 요약
- TAI 헤더 (로고·도메인 `taieng.co.kr`)
- 진단 대상 / 작성일 / 사업장 유형 / 문서번호 / 상시 인원 / 위험도
- **경영진 요약 박스** (네이비 배경)
  - 메인 문구: "귀 사업장은 N건의 법적 의무를 이행해야 하며, 미이행 시 약 XX원 규모의 과태료에 노출되어 있습니다"
  - 3개 수치: 적용 법령 수 / 법적 의무 총계 / **과태료 노출 총액 (합산·중대재해법 제외)**
- 법적 의무 유형별 요약 (선임·점검·조치·보고 4개 카드)
- 주요 리스크 TOP 5 테이블

#### P2: 중대재해법 + 관리방법 비교 + 분석 요지
- 중대재해처벌법 적용 여부 박스 (상시 인원 기준)
- 안전관리 방법별 비용·리스크 비교표 (방치 / 엑셀 / 대행 — **TAI 행 없음**)
- 관리 방식별 법적 리스크 수준 (막대 그래프)
- 분석 요지 (다음 페이지 연결)

#### P3: 섹터별 분기
공통 구조: `1. 확인된 영역` → `2. 확인되지 않은 영역` → `3. 정밀 진단 안내` → `4. TAI 회사 정보` → `5. 본 보고서 활용 안내`

**INDUSTRY** (3개 티어 카드):
- 기본 79,000원 (상세 PDF 약 20p)
- 정밀 149,000원 (상세 PDF 약 24p)
- 종합 249,000원 (상세 PDF 약 28p)
- 카드 하단: 배지 색상만 단계감 (회색/브랜드파랑/진네이비), **"추천" 배지 없음**

**BUILDING** (면적 자동 판정 → 단일 티어):
- 면적 < 5,000㎡ → 소형건물 99,000원 (약 20p)
- 면적 ≥ 5,000㎡ → 대형건물 249,000원 (약 25p)
- 현재 선택된 티어를 메인 박스로, 상위 티어는 하단 "※ 힌트" 박스

**CONSTRUCTION** (공사금액 자동 판정 → 단일 티어):
- 공사금액 < 50억원 → 건설 기본 145,000원 (약 22p)
- 공사금액 ≥ 50억원 → 건설 종합 299,000원 (약 28p)
- 현재 선택된 티어를 메인 박스로, 상위 티어는 하단 "※ 힌트" 박스

**전 섹터 공통 — 정밀 진단 박스 직후:**
```
┌─ 활용 포인트 ─────────────────────────────┐
│ 본 유료 리포트는 관공서 안전감독 시        │
│ 법적 의무 이행을 입증하는 근거자료로       │
│ 활용하실 수 있습니다.                      │
└────────────────────────────────────────────┘
```
스타일: 초록 배경 `#f0fdf4`, 좌측 포인트 `#16a34a` 4px

### B-2. 삭제되는 요소 (현행 v1.0.3 대비)
- ❌ TAI Safe 도입 4단계
- ❌ Before/After 업무구조 비교
- ❌ 추천 플랜 박스 (네이비 강조)
- ❌ 연간 절감액 숫자 (`annual_savings_*`)
- ❌ `recommended_plan_*` 필드 전부
- ❌ `_recommend_plan` 호출
- ❌ `max_penalty_text` (중대재해법 포함되어 왜곡) → `penalty_sum_text`로 교체

---

## 🗃️ C. 변경 대상 파일

### C-1. DB 마이그레이션 (Supabase)
**마이그레이션명:** `add_proposal_pdf_url_to_anonymous_diagnosis_results`

```sql
ALTER TABLE anonymous_diagnosis_results
ADD COLUMN IF NOT EXISTS proposal_pdf_url TEXT,
ADD COLUMN IF NOT EXISTS proposal_pdf_generated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_anon_diag_proposal_cache
ON anonymous_diagnosis_results(public_token)
WHERE proposal_pdf_url IS NOT NULL;
```

### C-2. Supabase Storage 버킷 생성
**버킷명:** `proposals`
- Public: `false` (공개 안함, 서명 URL 사용)
- File size limit: `5242880` (5MB)
- Allowed MIME: `["application/pdf"]`
- RLS: anon role에 대해 INSERT/SELECT 허용 (public_token 경로 한정)

버킷 생성 SQL:
```sql
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'proposals', 'proposals', false, 5242880,
  ARRAY['application/pdf']::text[]
)
ON CONFLICT (id) DO NOTHING;
```

RLS 정책 (Storage):
```sql
-- anon 사용자도 자신의 token으로 PDF 업로드/조회 가능
CREATE POLICY "anon_upload_proposals" ON storage.objects
FOR INSERT TO anon
WITH CHECK (bucket_id = 'proposals');

CREATE POLICY "anon_read_proposals" ON storage.objects
FOR SELECT TO anon
USING (bucket_id = 'proposals');

CREATE POLICY "service_role_all_proposals" ON storage.objects
FOR ALL TO service_role
USING (bucket_id = 'proposals');
```

### C-3. Backend: `routers/diagnosis_proposal.py`
v1.0.3 → **v2.0.0** 대폭 재작성. 주요 변경:

#### C-3-1. `_build_context` 확장

**삭제:**
```python
# 이 필드들 전부 제거
max_penalty, max_penalty_text
_recommend_plan, recommended_plan_name, recommended_plan_price
recommended_plan_monthly, plan_code
annual_savings_low, annual_savings_high
_PLANS, _AGENCY_MONTHLY_LOW, _AGENCY_MONTHLY_HIGH (상수)
```

**추가:**
```python
# 1. 과태료 합산 (중대재해법 제외)
def _compute_penalty_sum(rules_flat: List[Dict]) -> float:
    total = 0.0
    for r in rules_flat:
        law_name = (r.get('law_name') or r.get('law') or '').strip()
        if '중대재해' in law_name:
            continue
        total += _get_penalty_from_rule(r)
    return total

penalty_sum = _compute_penalty_sum(all_rules_flat)
penalty_sum_text = _format_penalty(penalty_sum)

# 2. 섹터별 유료 티어 생성
def _build_paid_tiers(sector: str, input_data: Dict) -> Dict[str, Any]:
    """
    INDUSTRY: 3개 티어 리스트 반환
    BUILDING: 1개 확정 + 상위 힌트
    CONSTRUCTION: 1개 확정 + 상위 힌트
    """
    if sector == "INDUSTRY":
        return {
            "mode": "select",
            "tiers": [
                {"badge_class": "basic",    "code": "INDUSTRY_V2",       "name": "제조·산업 기본", "price": 79000,  "pages": 20},
                {"badge_class": "standard", "code": "INDUSTRY_STANDARD", "name": "제조·산업 정밀", "price": 149000, "pages": 24},
                {"badge_class": "premium",  "code": "INDUSTRY_PREMIUM",  "name": "제조·산업 종합", "price": 249000, "pages": 28},
            ],
        }
    if sector == "BUILDING":
        area = float(input_data.get("total_floor_area") or 0)
        if area < 5000:
            determined = {"code": "BUILDING_V2", "name": "소형건물 (5,000㎡ 미만)", "price": 99000, "pages": 20}
            upper = {"name": "대형건물 등급", "price": 249000, "threshold": "연면적 5,000㎡ 이상"}
        else:
            determined = {"code": "BUILDING_LARGE_V2", "name": "대형건물 (5,000㎡ 이상)", "price": 249000, "pages": 25}
            upper = None
        return {
            "mode": "determined",
            "determined": determined,
            "upper": upper,
            "basis": f"입력 연면적 {int(area):,}㎡ 기준 자동 판정",
        }
    if sector == "CONSTRUCTION":
        amount = float(input_data.get("project_amount") or 0)  # 억원 단위
        if amount < 50:
            determined = {"code": "CONSTRUCTION", "name": "건설 기본 등급 (50억원 미만)", "price": 145000, "pages": 22}
            upper = {"name": "건설 종합 등급", "price": 299000, "threshold": "공사금액 50억원 이상"}
        else:
            determined = {"code": "CONSTRUCTION_PREMIUM", "name": "건설 종합 등급 (50억원 이상)", "price": 299000, "pages": 28}
            upper = None
        return {
            "mode": "determined",
            "determined": determined,
            "upper": upper,
            "basis": f"입력 공사금액 {int(amount):,}억원 기준 자동 판정",
        }
    # fallback
    return {"mode": "select", "tiers": []}

paid_tiers_data = _build_paid_tiers(sector, input_data)
```

#### C-3-2. 캐싱 로직 추가

```python
from fastapi.responses import RedirectResponse

@router.get("/proposal-pdf/{public_token}")
def get_proposal_pdf(public_token: str):
    row = _fetch_row(public_token)

    # 캐시 hit check
    cached_url = row.get("proposal_pdf_url")
    if cached_url:
        log.info(f"[proposal-pdf] 캐시 hit: {public_token}")
        return RedirectResponse(url=cached_url, status_code=302)

    # PDF 생성
    context = _build_context(row)
    html    = _render_html(context)
    pdf     = _generate_pdf(html)

    # Storage 업로드
    try:
        sb = get_supabase()
        filename = f"TAI_proposal_{context['report_no']}.pdf"
        storage_path = f"{public_token}/{filename}"

        sb.storage.from_("proposals").upload(
            path=storage_path,
            file=pdf,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        public_url = sb.storage.from_("proposals").get_public_url(storage_path)

        # DB에 URL 기록
        sb.table("anonymous_diagnosis_results").update({
            "proposal_pdf_url": public_url,
            "proposal_pdf_generated_at": _now().isoformat(),
        }).eq("public_token", public_token).execute()

        log.info(f"[proposal-pdf] 생성+캐싱 완료: {public_token} → {public_url}")
        return RedirectResponse(url=public_url, status_code=302)

    except Exception as e:
        # Storage 업로드 실패 시 fallback: 직접 스트리밍
        log.error(f"[proposal-pdf] Storage 업로드 실패, 직접 전송: {e}")
        return StreamingResponse(
            io.BytesIO(pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf)),
                "Cache-Control": "no-store",
            },
        )
```

#### C-3-3. VERSION 문자열 업데이트
```python
VERSION = "2.0.0"  # v6 콘텐츠 + Storage 캐싱
```

### C-4. Template: `templates/proposal_pdf.html`
**전면 재작성.** v6 mockup(`/mnt/user-data/outputs/proposal_mockup_v6.html`) 구조 그대로 Jinja2로 변환.

주요 변수 바인딩:
- `{{ company_name }}`, `{{ report_date }}`, `{{ sector_label }}`, `{{ workers }}`, `{{ risk_level }}`
- `{{ report_no }}`, `{{ total }}`, `{{ appointment }}`, `{{ inspection }}`, `{{ action }}`, `{{ report_notify }}`
- `{{ law_count }}`, **`{{ penalty_sum_text }}`** (기존 `max_penalty_text` 대체)
- `{% for item in top5 %}...{% endfor %}`

P3 섹터 분기:
```jinja2
{% if sector == "INDUSTRY" %}
  {# 3개 티어 카드 #}
  <div class="tier-grid">
    {% for tier in paid_tiers.tiers %}
      <div class="tier-card">
        <div class="tier-badge {{ tier.badge_class }}">{{ tier.badge_class|upper }}</div>
        <div class="tier-name">{{ tier.name }}</div>
        <div class="tier-price">{{ "{:,}".format(tier.price) }}원</div>
        <div class="tier-price-note">VAT 별도 · 1회성</div>
        <div class="tier-output-title">산출물</div>
        <div class="tier-output-item">상세 PDF 리포트</div>
        <div class="tier-output-pages">약 {{ tier.pages }}페이지</div>
      </div>
    {% endfor %}
  </div>
{% else %}
  {# BUILDING / CONSTRUCTION 단일 티어 #}
  <div class="single-tier-box">
    <span class="single-tier-badge">귀 사업장 해당</span>
    <div style="font-size:12pt; font-weight:bold;">{{ paid_tiers.determined.name }}</div>
    <div style="font-size:8.5pt; color:#64748b;">{{ paid_tiers.basis }}</div>
    {# ... 비용/소요/산출물 3열 테이블 ... #}
  </div>

  {% if paid_tiers.upper %}
    <div style="...">
      ※ {{ paid_tiers.upper.threshold }}은 <strong>{{ paid_tiers.upper.name }}({{ "{:,}".format(paid_tiers.upper.price) }}원)</strong>이 적용됩니다. 입력 항목은 동일하나, 규모 기준에 따라 적용 법령 세트와 분석 결과가 달라집니다.
    </div>
  {% endif %}
{% endif %}

{# 전 섹터 공통: 활용 포인트 #}
<div class="safety-value-box">
  <strong>활용 포인트</strong><br>
  본 유료 리포트는 <strong>관공서 안전감독 시</strong> 법적 의무 이행을 입증하는 근거자료로 활용하실 수 있습니다.
</div>
```

---

## 🛠️ D. 단계별 실행 체크리스트

### Phase 1: DB 준비 (Supabase MCP)
- [ ] `apply_migration` 실행: `add_proposal_pdf_url_to_anonymous_diagnosis_results`
- [ ] Storage 버킷 `proposals` 생성 + RLS 정책
- [ ] 스키마 확인: `proposal_pdf_url` 컬럼 존재 확인

### Phase 2: Template 교체
- [ ] `/mnt/user-data/outputs/proposal_mockup_v6.html` 참조
- [ ] `templates/proposal_pdf.html`을 v6 mockup 구조로 재작성
- [ ] Jinja2 변수 바인딩 (`{{ penalty_sum_text }}`, `{% if sector %}` 등)
- [ ] **주의: 파일 크기 600+라인 예상 → Claude Code 로컬 편집 + git push 권장 (메모리 #1)**
- [ ] MCP push_files 사용 시: 커밋 후 GitHub raw URL에서 파일 직접 확인 (리터럴 \n 유무)

### Phase 3: Backend 수정
- [ ] `routers/diagnosis_proposal.py` v2.0.0
  - [ ] `_PLANS`, `_AGENCY_MONTHLY_*`, `_recommend_plan` 제거
  - [ ] `_compute_penalty_sum` 추가
  - [ ] `_build_paid_tiers` 추가 (섹터별 분기)
  - [ ] `_build_context` 리팩토링 (삭제 필드 제거, 신규 필드 추가)
  - [ ] 엔드포인트 캐싱 로직 추가 (RedirectResponse)
- [ ] 로컬 `py_compile routers/*.py` 전체 검사 PASS
- [ ] dev 브랜치 커밋 + 푸시

### Phase 4: PR + 배포
- [ ] dev → main PR 생성 (#N)
- [ ] PR body에 변경 내역 + 테스트 결과 기재
- [ ] GitHub Actions CI 통과 확인
- [ ] main 머지
- [ ] Fly 자동 배포 완료 확인 (app name: `tai-api-prod`, 양쪽 machine healthy)

### Phase 5: E2E 검증
- [ ] INDUSTRY 샘플 토큰으로 `GET /diagnosis/proposal-pdf/{token}` 호출
  - 첫 요청: 200 → PDF 생성 → Storage 업로드 → DB URL 기록 → 302 redirect
  - 재요청: 302 redirect 즉시 응답
- [ ] BUILDING 샘플 토큰으로 동일 검증
- [ ] CONSTRUCTION 샘플 토큰으로 동일 검증
- [ ] Storage 버킷에서 PDF 파일 존재 확인
- [ ] PDF 열어서 v6 mockup과 시각적 일치 확인

---

## ⚠️ E. 주의사항

### E-1. dev 브랜치 원칙 (메모리 #14, #28)
- **모든 커밋 → `dev` 브랜치**
- `main` 직접 커밋 금지 (긴급 핫픽스만)
- `github-tai:push_files` 호출 시 `"branch": "dev"` 명시 필수

### E-2. 파일 크기 + MCP 안정성 (메모리 #1)
- `templates/proposal_pdf.html`은 v6 기준 600~800 라인 예상
- GitHub MCP의 `create_or_update_file` / `push_files` 사용 시 리터럴 `\n` 저장 사고 가능
- **우선 전략: Claude Code 로컬 편집 + `git push`**
- 불가피하게 MCP 사용 시:
  1. 커밋 후 GitHub raw URL 열어 파일 직접 확인 (`\n`이 실제 개행인지)
  2. 로컬에서 `python -m py_compile routers/diagnosis_proposal.py` 실행 후 푸시
  3. Actions 배포 성공까지 모니터링

### E-3. 유료 PDF와의 경계
- 기안 PDF에는 **티어별 상세 분석 범위(시설/공정/설비)를 넣지 않음** (대표님 지시)
- 이 내용은 **유료 PDF** 작업 시 이전 예정 → 별도 작업 (tai-api #5)

### E-4. 중대재해법 처리
- `penalty_sum`은 **중대재해법 제외** 합산 (오해 방지)
- 판단 기준: `law_name`에 `"중대재해"` 포함 여부
- P1 경영진 요약 박스 + P2 분석 요지 모두 **"약 2억 4,500만원 규모의 과태료 노출(합산, 중대재해법 제외)"** 톤 통일

### E-5. 카카오 API 금지 (메모리 #23)
- 이번 작업에 카카오 API 사용 없음 — 참고

### E-6. Storage 캐싱 무효화
- 이번 작업에는 캐시 무효화 로직 미포함 (최초 생성된 PDF가 영구 사용)
- 추후 필요 시: `expires_at` 이후 자동 삭제 cron 또는 re-generate 엔드포인트 추가

---

## 📊 F. 참조 데이터

### F-1. 가격 테이블 (DB: price_diagnosis_report)
| 섹터 | 등급 | facility_type_code | 가격 | 판정 기준 |
|---|---|---|---|---|
| BUILDING | 소형 | BUILDING_V2 | 99,000원 | 연면적 < 5,000㎡ |
| BUILDING | 대형 | BUILDING_LARGE_V2 | 249,000원 | 연면적 ≥ 5,000㎡ |
| INDUSTRY | 기본 | INDUSTRY_V2 | 79,000원 | 사용자 선택 |
| INDUSTRY | 정밀 | INDUSTRY_STANDARD | 149,000원 | 사용자 선택 |
| INDUSTRY | 종합 | INDUSTRY_PREMIUM | 249,000원 | 사용자 선택 |
| CONSTRUCTION | 기본 | CONSTRUCTION | 145,000원 | 공사금액 < 50억 |
| CONSTRUCTION | 종합 | CONSTRUCTION_PREMIUM | 299,000원 (`total_report_fee`) | 공사금액 ≥ 50억 |

⚠️ `CONSTRUCTION_PREMIUM.process_fee`는 385,000원이지만 **실제 표시 가격은 `total_report_fee`의 299,000원** (메모리 #21 확정).

### F-2. 현행 파일 정보
- `routers/diagnosis_proposal.py` (dev 브랜치 최신)
  - SHA: `44c9c1a83c5db86dba0998f15d397fae4b5f91c5`
  - 버전: v1.0.3 (2026-04-18, xhtml2pdf 한글 폰트 주입)
  - 크기: 12,278 bytes
- `templates/proposal_pdf.html` (dev 브랜치)
  - 버전: v1.0.3
  - 크기: 약 26.6 KB
  - 구조: 표지 / 리스크 / TAI 도입제안 (3페이지)

### F-3. DB 테이블 스키마 (anonymous_diagnosis_results)
기존 컬럼:
```
id, public_token, input_data(jsonb), partial_result(jsonb), full_result(jsonb),
created_at, expires_at, claimed_user_id, status, source_type,
engine_version, rule_version, ci_hash, auth_log_id, disclaimer_log_id,
tier_code, paid_amount, payment_ref
```
**추가 예정 컬럼:** `proposal_pdf_url TEXT`, `proposal_pdf_generated_at TIMESTAMPTZ`

### F-4. mockup 파일 (시각 기준)
`/mnt/user-data/outputs/proposal_mockup_v6.html`
- 브라우저에서 열면 A4 프레임으로 5페이지 렌더링
  - P1~P3: INDUSTRY 기준 3페이지
  - P4: BUILDING P3 변형
  - P5: CONSTRUCTION P3 변형
- 하드코딩된 값:
  - 회사명: "귀 사업장"
  - 작성일: "2026년 4월 19일"
  - 인원: 45명
  - 법적 의무: 131건
  - 과태료 노출: 약 2억 4,500만원
  - 문서번호: TAI-2026-DR-A1B2C3D4

---

## 🔗 G. 향후 연계 작업 (이번 작업 범위 외)

1. **유료 PDF 개편 (tai-api #5)**
   - 티어별 상세 분석 범위(시설/공정/설비)를 유료 PDF 내부에 명시
   - "본 진단은 X 등급으로 진행되었으며, 다음 범위까지 분석되었습니다"
   - 별도 작업으로 분리

2. **PDF 엔진 교체 (Phase 3)**
   - xhtml2pdf → WeasyPrint 또는 Gotenberg 검토
   - Storage 캐싱 적용 후 진행 (메모리 #28)

3. **CI/CD 검증 파이프라인 (tai-api #3)**
   - GitHub Actions에 `py_compile routers/*.py` 검증 스텝 추가
   - MCP `\n` 버그 재발 방지

---

## ✅ H. 최종 확인 (PR 머지 전 필수)

- [ ] `python -m py_compile routers/diagnosis_proposal.py` 통과
- [ ] 로컬 또는 staging에서 3개 섹터 샘플로 PDF 생성 성공
- [ ] 생성된 PDF가 v6 mockup과 시각적으로 일치 (결재란 없음, TAI 영업 내용 없음, 활용 포인트 박스 존재)
- [ ] `penalty_sum_text`가 중대재해법 제외한 합산값으로 정상 표시
- [ ] Storage 캐싱 동작: 첫 호출과 두 번째 호출 응답 시간 차이 확인 (두 번째는 캐시 redirect로 매우 빠름)
- [ ] `engine_version` 컬럼에 버전 기록 (선택, 로그 추적용)

---

**작성자:** 기획창 (Claude)
**핸드오프 대상:** Claude Code (또는 백엔드 구현 창)
**작업 예상 시간:** Phase 1 (30분) + Phase 2~3 (2~3시간) + Phase 4~5 (30분) = **3~4시간**
