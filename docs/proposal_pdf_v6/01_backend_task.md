# 01. 백엔드 작업 지시서 — 기안 PDF v6 개편

> **담당 창:** 백엔드 창 (tai-api 레포 · Fly.io 배포)
> **작업 브랜치:** `dev`
> **예상 시간:** 2~3시간
> **관련 문서:** `./README.md` (종합 핸드오프), `./mockup.html` (시각 기준)

---

## 🎯 담당 범위

### ✅ 이 문서에서 작업하는 것
1. **DB 마이그레이션** — `anonymous_diagnosis_results` 컬럼 추가
2. **Supabase Storage 버킷** — `proposals` 신설 + RLS
3. **Python 로직** — `routers/diagnosis_proposal.py` v1.0.3 → v2.0.0 재작성

### ❌ 이 문서에서 작업하지 않는 것
- `templates/proposal_pdf.html` → **02_frontend_task.md** 창이 담당
- 마케팅 사이트 / safe.taieng.co.kr UI 변경 → 별도 작업

---

## 🔗 프론트(템플릿) 창과의 계약 (중요)

백엔드가 `_build_context`에서 반환하는 딕셔너리 = 템플릿이 받는 컨텍스트. 아래 **변수 이름·구조를 정확히 맞춰야** 프론트 작업창과 충돌이 없음.

### 계약 스펙 (v2.0.0 `_build_context` 반환)

```python
{
    # 기본 정보 (기존 유지)
    "company_name": str,          # "귀 사업장" (input 없을 시 fallback)
    "report_date": str,           # "2026년 04월 19일"
    "sector": str,                # "INDUSTRY" | "BUILDING" | "CONSTRUCTION"
    "sector_label": str,          # "산업(제조)" | "건물·시설" | "건설"
    "risk_level": str,            # "LOW" | "MEDIUM" | "HIGH"
    "workers": int,               # 45
    "report_no": str,             # "A1B2C3D4" (public_token 앞 8자)

    # 요약 수치 (기존 유지)
    "total": int,                 # 131
    "appointment": int,           # 8
    "inspection": int,            # 37
    "action": int,                # 55
    "report_notify": int,         # 31
    "law_count": int,             # 46

    # ⭐ 신규: 과태료 합산 (중대재해법 제외)
    "penalty_sum": float,         # 245000000
    "penalty_sum_text": str,      # "약 2억 4,500만원"

    # TOP 5 리스크 (기존 유지)
    "top5": list[dict],           # [{"title", "law", "penalty", "amount"}, ...]

    # 중대재해법 (기존 유지)
    "csia_applicable": bool,      # workers >= 50

    # ⭐ 신규: 섹터별 유료 티어
    "paid_tiers": dict,           # 아래 상세 참조

    # ❌ 이전 필드 중 삭제된 것들 (템플릿에서도 더 이상 사용 안 함)
    # - max_penalty_text (→ penalty_sum_text로 대체)
    # - recommended_plan_name
    # - recommended_plan_price
    # - recommended_plan_monthly
    # - plan_code
    # - annual_savings_low
    # - annual_savings_high
}
```

### `paid_tiers` 구조 (가장 중요)

**INDUSTRY 섹터 (mode = "select"):**
```python
{
    "mode": "select",
    "tiers": [
        {"badge_class": "basic",    "code": "INDUSTRY_V2",       "name": "제조·산업 기본", "price": 79000,  "pages": 20},
        {"badge_class": "standard", "code": "INDUSTRY_STANDARD", "name": "제조·산업 정밀", "price": 149000, "pages": 24},
        {"badge_class": "premium",  "code": "INDUSTRY_PREMIUM",  "name": "제조·산업 종합", "price": 249000, "pages": 28},
    ],
}
```

**BUILDING 섹터 (mode = "determined") — 면적 자동판정:**
```python
# 2,800㎡ 입력 케이스
{
    "mode": "determined",
    "determined": {
        "code": "BUILDING_V2",
        "name": "소형건물 (5,000㎡ 미만)",
        "price": 99000,
        "pages": 20,
    },
    "upper": {  # 상위 등급 힌트 (이미 대형이면 None)
        "name": "대형건물 등급",
        "price": 249000,
        "threshold": "연면적 5,000㎡ 이상",
    },
    "basis": "입력 연면적 2,800㎡ 기준 자동 판정",
}
```

**CONSTRUCTION 섹터 (mode = "determined") — 공사금액 자동판정:**
```python
# 30억원 입력 케이스
{
    "mode": "determined",
    "determined": {
        "code": "CONSTRUCTION",
        "name": "건설 기본 등급 (50억원 미만)",
        "price": 145000,
        "pages": 22,
    },
    "upper": {
        "name": "건설 종합 등급",
        "price": 299000,
        "threshold": "공사금액 50억원 이상",
    },
    "basis": "입력 공사금액 30억원 기준 자동 판정",
}
```

---

## 🛠️ Phase 1: DB + Storage 준비

### Step 1.1: DB 마이그레이션

**Supabase MCP 사용:**
```
tool: supabase:apply_migration
name: add_proposal_pdf_url_to_anonymous_diagnosis_results
query:
  ALTER TABLE anonymous_diagnosis_results
  ADD COLUMN IF NOT EXISTS proposal_pdf_url TEXT,
  ADD COLUMN IF NOT EXISTS proposal_pdf_generated_at TIMESTAMPTZ;

  CREATE INDEX IF NOT EXISTS idx_anon_diag_proposal_cache
  ON anonymous_diagnosis_results(public_token)
  WHERE proposal_pdf_url IS NOT NULL;
```

### Step 1.2: Storage 버킷 생성

```sql
-- supabase:execute_sql
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'proposals', 'proposals', true, 5242880,
  ARRAY['application/pdf']::text[]
)
ON CONFLICT (id) DO NOTHING;
```

**참고:** `public: true`로 설정 — PDF URL을 고객이 품의서 첨부 시 열어야 하므로. 단 URL은 `public_token` 기반이라 외부 노출 위험은 제한적.

### Step 1.3: RLS 정책 (Storage)

```sql
-- anon이 업로드할 수 있도록 (Fly에서 service role key 사용하지만 안전장치)
CREATE POLICY "anon_upload_proposals" ON storage.objects
FOR INSERT TO anon
WITH CHECK (bucket_id = 'proposals');

CREATE POLICY "public_read_proposals" ON storage.objects
FOR SELECT TO anon, authenticated
USING (bucket_id = 'proposals');

CREATE POLICY "service_role_all_proposals" ON storage.objects
FOR ALL TO service_role
USING (bucket_id = 'proposals');
```

### Step 1.4: 검증
```sql
-- 컬럼 확인
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'anonymous_diagnosis_results'
  AND column_name LIKE 'proposal%';

-- 버킷 확인
SELECT id, name, public, allowed_mime_types FROM storage.buckets
WHERE name = 'proposals';
```

---

## 🐍 Phase 2: Python 수정 (`routers/diagnosis_proposal.py`)

### 중요: 파일 수정 방식
- **현재 크기:** 12,278 bytes, 약 280 라인
- **수정 후 예상:** 350~400 라인
- **권장:** Claude Code 로컬 편집 + `git push` (메모리 #1)
- MCP push_files 사용 시: 커밋 후 raw URL에서 리터럴 `\n` 확인 + `py_compile` 이중검증

### Step 2.1: 삭제할 요소

```python
# 상수 삭제
_PLANS                         # SaaS 플랜 딕셔너리
_AGENCY_MONTHLY_LOW            # 대행 월비용
_AGENCY_MONTHLY_HIGH

# 함수 삭제
_recommend_plan()              # SaaS 플랜 추천 (이 PDF에서 안 씀)

# _build_context 내부에서 삭제
max_penalty = max(...)
max_penalty_text = _format_penalty(max_penalty)
plan_code, plan_info = _recommend_plan(...)
monthly = plan_info.get("monthly")
plan_price = ...
annual_savings_low = ...
annual_savings_high = ...

# 반환 딕셔너리에서 삭제 (아래 키들)
"max_penalty_text"
"recommended_plan_name"
"recommended_plan_price"
"recommended_plan_monthly"
"plan_code"
"annual_savings_low"
"annual_savings_high"
```

### Step 2.2: 추가할 함수

```python
def _compute_penalty_sum(rules_flat: List[Dict]) -> float:
    """전체 규칙의 과태료를 합산. 중대재해처벌법 항목은 제외."""
    total = 0.0
    for r in rules_flat:
        if not isinstance(r, dict):
            continue
        law_name = str(r.get("law_name") or r.get("law") or "").strip()
        if "중대재해" in law_name:
            continue
        total += _get_penalty_from_rule(r)
    return total


def _build_paid_tiers(sector: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    섹터별 유료 티어 구성을 생성.
    - INDUSTRY: 3개 티어 리스트 (사용자 선택형)
    - BUILDING: 면적 기준 자동 판정 (단일 + 상위 힌트)
    - CONSTRUCTION: 공사금액 기준 자동 판정 (단일 + 상위 힌트)
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
        try:
            area = float(input_data.get("total_floor_area") or 0)
        except (TypeError, ValueError):
            area = 0.0

        if area < 5000:
            determined = {
                "code": "BUILDING_V2",
                "name": "소형건물 (5,000㎡ 미만)",
                "price": 99000,
                "pages": 20,
            }
            upper = {
                "name": "대형건물 등급",
                "price": 249000,
                "threshold": "연면적 5,000㎡ 이상",
            }
        else:
            determined = {
                "code": "BUILDING_LARGE_V2",
                "name": "대형건물 (5,000㎡ 이상)",
                "price": 249000,
                "pages": 25,
            }
            upper = None

        return {
            "mode": "determined",
            "determined": determined,
            "upper": upper,
            "basis": f"입력 연면적 {int(area):,}㎡ 기준 자동 판정",
        }

    if sector == "CONSTRUCTION":
        try:
            # 공사금액: 원 단위로 들어오면 억원 변환, 이미 억원이면 그대로
            raw_amount = input_data.get("project_amount") or 0
            amount_won = float(raw_amount)
            # 10억 이상이면 원 단위로 가정, 아니면 억원 단위로 가정
            amount_eok = amount_won / 100_000_000 if amount_won >= 1_000_000_000 else amount_won
        except (TypeError, ValueError):
            amount_eok = 0.0

        if amount_eok < 50:
            determined = {
                "code": "CONSTRUCTION",
                "name": "건설 기본 등급 (50억원 미만)",
                "price": 145000,
                "pages": 22,
            }
            upper = {
                "name": "건설 종합 등급",
                "price": 299000,
                "threshold": "공사금액 50억원 이상",
            }
        else:
            determined = {
                "code": "CONSTRUCTION_PREMIUM",
                "name": "건설 종합 등급 (50억원 이상)",
                "price": 299000,
                "pages": 28,
            }
            upper = None

        return {
            "mode": "determined",
            "determined": determined,
            "upper": upper,
            "basis": f"입력 공사금액 {int(amount_eok):,}억원 기준 자동 판정",
        }

    # fallback
    return {"mode": "select", "tiers": []}
```

### Step 2.3: `_build_context` 리팩토링

기존 코드 중 아래 블록을 교체:

```python
# 기존 (삭제)
max_penalty = max((_get_penalty_from_rule(r) for r in all_rules_flat), default=0.0)
max_penalty_text = _format_penalty(max_penalty)
top5 = _get_top5(full)
csia_applicable = workers >= 50
plan_code, plan_info = _recommend_plan(sector, risk_level, total, workers)
monthly = plan_info.get("monthly")
plan_price = f"월 {monthly:,}원" if monthly else "맞춤 견적"
monthly_plan = monthly or 149_000
annual_savings_low  = max(0, int((_AGENCY_MONTHLY_LOW  - monthly_plan) * 12 / 10_000))
annual_savings_high = max(0, int((_AGENCY_MONTHLY_HIGH - monthly_plan) * 12 / 10_000))
```

로 바꿔서:

```python
# 신규
penalty_sum = _compute_penalty_sum(all_rules_flat)
penalty_sum_text = _format_penalty(penalty_sum)
top5 = _get_top5(full)
csia_applicable = workers >= 50
paid_tiers = _build_paid_tiers(sector, input_data)
```

그리고 return 딕셔너리를 아래처럼:

```python
return {
    "company_name": company_name,
    "report_date": report_date,
    "sector_label": sector_label,
    "sector": sector,
    "risk_level": risk_level,
    "workers": workers,
    "report_no": str(row.get("public_token", ""))[:8].upper(),
    "total": total,
    "appointment": appointment,
    "inspection": inspection,
    "action": action,
    "report_notify": report_notify,
    "law_count": law_count,
    "penalty_sum": penalty_sum,
    "penalty_sum_text": penalty_sum_text,
    "top5": top5,
    "csia_applicable": csia_applicable,
    "paid_tiers": paid_tiers,
}
```

### Step 2.4: 엔드포인트 캐싱 로직

```python
from fastapi.responses import RedirectResponse, StreamingResponse

@router.get("/proposal-pdf/{public_token}")
def get_proposal_pdf(public_token: str):
    """기안용 PDF — 품의서 첨부 근거자료 (공개 엔드포인트, 캐싱 적용)."""
    row = _fetch_row(public_token)

    # Cache hit check
    cached_url = row.get("proposal_pdf_url")
    if cached_url:
        log.info(f"[proposal-pdf] cache hit: {public_token}")
        return RedirectResponse(url=cached_url, status_code=302)

    # 생성
    context = _build_context(row)
    html    = _render_html(context)
    pdf     = _generate_pdf(html)
    filename = f"TAI_proposal_{context['report_no']}.pdf"

    # Storage 업로드 (실패 시 직접 스트리밍 fallback)
    try:
        sb = get_supabase()
        storage_path = f"{public_token}/{filename}"

        sb.storage.from_("proposals").upload(
            path=storage_path,
            file=pdf,
            file_options={
                "content-type": "application/pdf",
                "upsert": "true",
            },
        )
        public_url = sb.storage.from_("proposals").get_public_url(storage_path)

        sb.table("anonymous_diagnosis_results").update({
            "proposal_pdf_url": public_url,
            "proposal_pdf_generated_at": _now().isoformat(),
        }).eq("public_token", public_token).execute()

        log.info(f"[proposal-pdf] generated+cached: {public_token}")
        return RedirectResponse(url=public_url, status_code=302)

    except Exception as e:
        log.error(f"[proposal-pdf] storage upload failed, streaming: {e}")
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

### Step 2.5: 버전 + import 정리

```python
VERSION = "2.0.0"

# 파일 맨 위 docstring 업데이트
"""
routers/diagnosis_proposal.py — v2.0.0
기안 PDF — 품의서 첨부용 분석보고서 (v6 콘텐츠 + Storage 캐싱)

v2.0.0 (2026-04-19): v6 콘텐츠 개편, Storage 캐싱, penalty_sum/paid_tiers 신규
v1.0.3 (2026-04-18): xhtml2pdf 한글 폰트 주입
v1.0.2 (2026-04-18): str 규칙 처리 수정
v1.0.1 (2026-04-18): penalty 파싱 수정
v1.0.0 (2026-04-18): 최초 생성
"""

# import 추가
from fastapi.responses import RedirectResponse, StreamingResponse
```

---

## ✅ Phase 3: 로컬 검증

```bash
# Python 문법 검증
python -m py_compile routers/diagnosis_proposal.py

# import 정상 여부
python -c "from routers import diagnosis_proposal; print(diagnosis_proposal.VERSION)"
# 출력: 2.0.0
```

단위 테스트 (선택):
```python
# _build_paid_tiers 테스트
assert _build_paid_tiers("INDUSTRY", {})["mode"] == "select"
assert len(_build_paid_tiers("INDUSTRY", {})["tiers"]) == 3

assert _build_paid_tiers("BUILDING", {"total_floor_area": 2800})["determined"]["code"] == "BUILDING_V2"
assert _build_paid_tiers("BUILDING", {"total_floor_area": 6000})["determined"]["code"] == "BUILDING_LARGE_V2"

assert _build_paid_tiers("CONSTRUCTION", {"project_amount": 30})["determined"]["code"] == "CONSTRUCTION"
assert _build_paid_tiers("CONSTRUCTION", {"project_amount": 80})["determined"]["code"] == "CONSTRUCTION_PREMIUM"
```

---

## 🚀 Phase 4: 배포

```bash
# dev 브랜치 커밋
git checkout dev
git add routers/diagnosis_proposal.py
git commit -m "feat(proposal-pdf): v2.0.0 — v6 콘텐츠 + Storage 캐싱

- _build_context 리팩토링 (penalty_sum, paid_tiers 신규)
- _recommend_plan, annual_savings 제거 (SaaS 영업 내용 배제)
- RedirectResponse 캐싱: 첫 생성 → Storage 업로드 → 302
- 재요청: proposal_pdf_url DB 확인 → 즉시 302 redirect

Refs: tai-api #4"
git push origin dev

# PR 생성 (dev → main)
# GitHub에서 수동 또는 gh CLI 사용
gh pr create --base main --head dev \
  --title "기안 PDF v2.0.0 — v6 콘텐츠 + Storage 캐싱" \
  --body "proposal_pdf_v6_handoff 참조. 프론트 템플릿 작업과 동시 머지 필요."
```

**중요:** 템플릿(`proposal_pdf.html`) 작업과 **같은 PR 또는 연속 머지 필수**. 템플릿만 있고 context가 부재하면 Jinja2가 UndefinedError 발생.

---

## 🔍 Phase 5: E2E 검증

```bash
# 3개 섹터 샘플 토큰으로 호출
curl -I "https://api.taieng.co.kr/diagnosis/proposal-pdf/${TOKEN_INDUSTRY}"
# 첫 호출: HTTP/1.1 302 Found, location: https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/proposals/...
# 재호출: HTTP/1.1 302 Found (DB 캐시 히트)

# Storage에 파일 존재 확인
```

Supabase MCP로 확인:
```sql
SELECT public_token, proposal_pdf_url, proposal_pdf_generated_at
FROM anonymous_diagnosis_results
WHERE proposal_pdf_url IS NOT NULL
ORDER BY proposal_pdf_generated_at DESC
LIMIT 5;
```

```sql
-- Storage 파일 목록
SELECT name, bucket_id, created_at, metadata->>'size' as size_bytes
FROM storage.objects
WHERE bucket_id = 'proposals'
ORDER BY created_at DESC
LIMIT 10;
```

---

## ⚠️ 주의사항

### dev 브랜치 원칙 (메모리 #14, #28)
- 모든 커밋 → `dev` 브랜치
- `main` 직접 커밋 금지

### Fly.io 배포 (메모리 #1)
- 앱명: `tai-api-prod`
- dev → main PR 머지 → Actions 자동 배포
- 배포 후 `/health` + `/diagnosis/proposal-pdf/{token}` 양쪽 확인
- Fly lease 충돌 주의: Actions 중 재배포 금지

### 프론트 창과의 동기화
- 백엔드 v2.0.0만 배포되면 템플릿(기존 v1.0.3)과 불일치 → 500 에러 발생 가능
  - `max_penalty_text` 템플릿에서 참조하는데 context에 없으므로
- **템플릿 작업(02_frontend_task.md)과 동시 머지** 필수

### CONSTRUCTION.process_fee vs total_report_fee (메모리 #21)
- DB 실제 값: `process_fee = 385000`, `total_report_fee = 299000` 불일치
- **표시 가격은 `total_report_fee`의 299,000원** 확정
- 본 작업에서 하드코딩된 `299000` 사용 (DB 조회 안 함)

---

## 📋 최종 체크리스트

### Phase 1 — DB/Storage
- [ ] `apply_migration` PASS
- [ ] `proposal_pdf_url` 컬럼 확인
- [ ] `proposals` 버킷 확인 (public, 5MB, application/pdf)
- [ ] RLS 정책 3개 확인

### Phase 2 — Python
- [ ] `_PLANS`, `_recommend_plan` 등 삭제
- [ ] `_compute_penalty_sum`, `_build_paid_tiers` 추가
- [ ] `_build_context` 리팩토링 (반환 딕셔너리 키 정확히 일치)
- [ ] 엔드포인트에 캐싱 로직 추가
- [ ] `VERSION = "2.0.0"`
- [ ] Docstring 업데이트

### Phase 3 — 로컬 검증
- [ ] `py_compile` PASS
- [ ] 모듈 import 정상
- [ ] 단위 테스트 3개 섹터 PASS

### Phase 4 — 배포
- [ ] dev 커밋 + 푸시
- [ ] PR 생성 (프론트 PR과 연계)
- [ ] main 머지
- [ ] Fly 자동 배포 성공 확인
- [ ] `/health` 200

### Phase 5 — E2E
- [ ] INDUSTRY 샘플 토큰: 첫 302 → redirected URL 접근 시 PDF 정상
- [ ] BUILDING 샘플 토큰: 동일
- [ ] CONSTRUCTION 샘플 토큰: 동일
- [ ] 재호출 시 즉시 302 (캐시 히트)
- [ ] Storage에 PDF 3개 존재
- [ ] DB에 `proposal_pdf_url` 3건 기록

---

## 🔗 다음 단계

본 작업 완료 후:
- **tai-api #5 유료 PDF 개편** — 티어별 상세 분석 범위(시설/공정/설비) 유료 PDF에 이전
- **tai-api #3 CI/CD 파이프라인** — Actions에 `py_compile` 검증 스텝 추가
