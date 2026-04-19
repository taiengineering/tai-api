# 02. 프론트(템플릿) 작업 지시서 — 기안 PDF v6 개편

> **담당 창:** 프론트(템플릿) 창 (tai-api 레포의 `templates/` 디렉토리)
> **작업 브랜치:** `dev`
> **예상 시간:** 2시간
> **관련 문서:** `./README.md` (종합 핸드오프), `./mockup.html` (시각 기준), `./01_backend_task.md` (백엔드 계약)

---

## 🎯 담당 범위

### ✅ 이 문서에서 작업하는 것
- **`templates/proposal_pdf.html` 전면 재작성**
  - v6 mockup (`./mockup.html`) 기반으로 CSS/HTML 구조 이전
  - 하드코딩 값을 Jinja2 변수로 치환
  - 섹터별 분기 (`{% if sector == "INDUSTRY" %}`)

### ❌ 이 문서에서 작업하지 않는 것
- `routers/diagnosis_proposal.py` → **01_backend_task.md** 창이 담당
- DB 마이그레이션 / Storage 버킷 → 백엔드 담당
- 마케팅 사이트·프론트엔드 앱의 다운로드 버튼 → 별도 작업

---

## 🔗 백엔드 창과의 계약 (중요)

백엔드가 제공하는 Jinja2 컨텍스트:

| 변수 | 타입 | 예시 | 비고 |
|---|---|---|---|
| `company_name` | str | "귀 사업장" | |
| `report_date` | str | "2026년 04월 19일" | |
| `sector` | str | `"INDUSTRY"` \| `"BUILDING"` \| `"CONSTRUCTION"` | **분기 기준** |
| `sector_label` | str | "산업(제조)" | 표시용 한글 |
| `risk_level` | str | `"LOW"` \| `"MEDIUM"` \| `"HIGH"` | 배지 색상 결정 |
| `workers` | int | 45 | |
| `report_no` | str | "A1B2C3D4" | 문서번호 suffix |
| `total` | int | 131 | 법적 의무 총계 |
| `appointment` | int | 8 | 선임 |
| `inspection` | int | 37 | 점검·검사 |
| `action` | int | 55 | 조치 |
| `report_notify` | int | 31 | 보고·신고 |
| `law_count` | int | 46 | 적용 법령 수 |
| **`penalty_sum_text`** ⭐ | str | "약 2억 4,500만원" | **신규 — 합산·중대재해 제외** |
| `top5` | list[dict] | `[{title, law, penalty, amount}, ...]` | |
| `csia_applicable` | bool | workers ≥ 50 | 중대재해법 적용 여부 |
| **`paid_tiers`** ⭐ | dict | 아래 참조 | **신규 — 섹터별 구조 다름** |

### `paid_tiers` 구조 (섹터별 상이)

**INDUSTRY (mode="select"):**
```python
{
    "mode": "select",
    "tiers": [
        {"badge_class": "basic",    "name": "제조·산업 기본", "price": 79000,  "pages": 20},
        {"badge_class": "standard", "name": "제조·산업 정밀", "price": 149000, "pages": 24},
        {"badge_class": "premium",  "name": "제조·산업 종합", "price": 249000, "pages": 28},
    ],
}
```

**BUILDING / CONSTRUCTION (mode="determined"):**
```python
{
    "mode": "determined",
    "determined": {"code": "...", "name": "소형건물 (5,000㎡ 미만)", "price": 99000, "pages": 20},
    "upper": {"name": "대형건물 등급", "price": 249000, "threshold": "연면적 5,000㎡ 이상"} or None,
    "basis": "입력 연면적 2,800㎡ 기준 자동 판정",
}
```

### ⚠️ 삭제되는 변수 (기존 템플릿에서 참조하지 말 것)
- `max_penalty_text` → `penalty_sum_text` 로 교체
- `recommended_plan_name`, `recommended_plan_price`, `recommended_plan_monthly`, `plan_code`
- `annual_savings_low`, `annual_savings_high`

---

## 📄 작업 순서

### Step 1: Mockup 구조 파악

`./mockup.html` 을 브라우저에서 열어 5페이지 구조 확인:
- 페이지 1: 표지 + 진단 요약 (공통)
- 페이지 2: 중대재해법 + 관리방법 비교 + 분석 요지 (공통)
- 페이지 3: INDUSTRY P3 (3개 티어)
- 페이지 4: BUILDING P3 (단일 + 상위 힌트)
- 페이지 5: CONSTRUCTION P3 (단일 + 상위 힌트)

### Step 2: Jinja 템플릿 골격

```jinja2
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<title>산업안전 법령진단 분석 보고서</title>
<style>
/* mockup의 <style>을 그대로 이전 */
/* .page, .sh, .exec-box, .tier-card, .single-tier-box, .safety-value-box, .company-info 등 */
/* ⚠️ .viewer-note, .sector-switch 는 제거 (mockup 전용) */
/* ⚠️ body { background: #e2e8f0; padding: 20px; } 는 제거 (PDF는 background white) */
/* ⚠️ .page { box-shadow, margin, border-radius } 는 제거 (PDF 한 장씩 렌더) */
</style>
</head>
<body>

{# ========== PAGE 1: 표지 + 진단 요약 ========== #}
<div class="page">
  {# 헤더 #}
  <table style="width:100%; border-bottom: 3px solid #1A5FD4; ...">
    <tr>
      <td>
        <span style="font-size:17pt; font-weight:bold; color:#1A5FD4;">TAI</span>
        <span style="font-size:9pt; color:#64748b;">Engineering · taieng.co.kr</span>
      </td>
      <td style="text-align:right;">
        <span style="font-size:13.5pt; font-weight:bold;">산업안전 법령진단 분석 보고서</span><br/>
        <span style="font-size:7.5pt; color:#64748b;">Legal Compliance Analysis Report</span>
      </td>
    </tr>
  </table>

  {# 진단 정보 (좌/우 2열) #}
  <table style="width:100%; ...">
    <tr>
      <td style="width:49%; ...">
        <table>
          <tr><td>진단 대상</td><td>{{ company_name }}</td></tr>
          <tr><td>작성일</td><td>{{ report_date }}</td></tr>
          <tr><td>사업장 유형</td><td>{{ sector_label }}</td></tr>
        </table>
      </td>
      <td style="width:49%; ...">
        <table>
          <tr><td>문서번호</td><td>TAI-2026-DR-{{ report_no }}</td></tr>
          <tr>
            <td>상시 인원</td>
            <td>
              {{ workers }}명
              {% if csia_applicable %}
                <span style="color:#dc2626;">(중대재해법 적용)</span>
              {% else %}
                <span style="color:#64748b;">(중대재해법 미적용 · 50인 기준)</span>
              {% endif %}
            </td>
          </tr>
          <tr>
            <td>위험도</td>
            <td>
              {% if risk_level == "HIGH" %}
                <span class="badge b-high">높음 (HIGH)</span>
              {% elif risk_level == "LOW" %}
                <span class="badge b-low">낮음 (LOW)</span>
              {% else %}
                <span class="badge b-med">보통 (MEDIUM)</span>
              {% endif %}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>

  {# 경영진 요약 박스 (⭐ penalty_sum_text 사용) #}
  <div class="exec-box">
    <div class="exec-main">
      귀 사업장은 <span style="color:#f59e0b;">{{ total }}건</span>의 법적 의무를 이행해야 하며,
      미이행 시 <span style="color:#f59e0b;">{{ penalty_sum_text }}</span> 규모의 과태료에 노출되어 있습니다.
    </div>
    <table style="width:100%;">
      <tr>
        <td style="text-align:center; ...">
          <div class="exec-num-val">{{ law_count }}</div>
          <div class="exec-num-label">적용 법령 수</div>
        </td>
        <td style="text-align:center; ...">
          <div class="exec-num-val">{{ total }}</div>
          <div class="exec-num-label">법적 의무 총계</div>
        </td>
        <td style="text-align:center; ...">
          <div class="exec-num-val" style="color:#f87171;">{{ penalty_sum_text }}</div>
          <div class="exec-num-label">과태료 노출 총액</div>
          <div class="exec-num-sub">(합산 · 중대재해법 제외)</div>
        </td>
      </tr>
    </table>
  </div>

  {# 법적 의무 유형별 요약 4카드 #}
  <div class="sh"><h2>법적 의무 유형별 요약</h2></div>
  <table style="width:100%;">
    <tr>
      <td style="width:25%; padding:3px;"><div class="sc"><div class="k">선임 의무</div><div class="v">{{ appointment }}</div><div class="k">건</div></div></td>
      <td style="width:25%; padding:3px;"><div class="sc"><div class="k">점검·검사</div><div class="v">{{ inspection }}</div><div class="k">건</div></div></td>
      <td style="width:25%; padding:3px;"><div class="sc"><div class="k">조치 의무</div><div class="v">{{ action }}</div><div class="k">건</div></div></td>
      <td style="width:25%; padding:3px;"><div class="sc"><div class="k">보고·신고</div><div class="v">{{ report_notify }}</div><div class="k">건</div></div></td>
    </tr>
  </table>

  {# TOP 5 리스크 #}
  <div class="sh" style="margin-top:13px;">
    <h2>주요 리스크 TOP 5</h2>
    <p>과태료 금액 기준 상위 5건 — 법령을 정밀 분석하여 도출</p>
  </div>
  <table class="top5-table">
    <thead>
      <tr>
        <th style="width:6%;">순위</th>
        <th style="width:42%;">위반 사항</th>
        <th style="width:31%;">근거 법령</th>
        <th style="width:21%;">처벌 내용</th>
      </tr>
    </thead>
    <tbody>
      {% for item in top5 %}
      <tr>
        <td style="text-align:center; font-weight:bold; color:#1A5FD4;">{{ loop.index }}위</td>
        <td>{{ item.title }}</td>
        <td style="color:#64748b; font-size:8pt;">{{ item.law }}</td>
        <td style="color:#dc2626; font-weight:bold;">{{ item.penalty }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {# 푸터 #}
  <div class="pf">
    <table style="width:100%;">
      <tr>
        <td>TAI Engineering · taieng.co.kr · contact@taieng.co.kr</td>
        <td style="text-align:right;">1 / 3</td>
      </tr>
    </table>
  </div>
</div>{# /page 1 #}


{# ========== PAGE 2: 중대재해법 + 관리방법 + 분석 요지 ========== #}
<div class="page" style="page-break-before: always;">
  {# 간략 헤더 #}
  <table style="border-bottom:2px solid #1A5FD4; ...">
    <tr>
      <td>
        <span style="font-size:12pt; font-weight:bold; color:#1A5FD4;">TAI</span>
        <span style="font-size:7.5pt; color:#64748b;">산업안전 법령진단 분석 보고서</span>
      </td>
      <td style="text-align:right;">{{ company_name }} · {{ report_date }}</td>
    </tr>
  </table>

  {# 중대재해법 박스 #}
  <div class="sh"><h2>중대재해처벌법 적용 여부</h2></div>
  {% if csia_applicable %}
    <div style="background:#fef2f2; border:1px solid #dc2626; ...">
      <strong style="color:#dc2626; font-size:10.5pt;">⚠️ 즉시 적용 대상입니다 (상시 {{ workers }}명)</strong><br/>
      <span style="font-size:8.8pt;">
        중대재해처벌법에 따라 경영책임자는 산재 발생 시 1년 이상 징역 또는 10억원 이하 벌금에 처해질 수 있습니다.
        즉시 안전보건관리체계 구축 및 이행이 필요합니다.
      </span>
    </div>
  {% else %}
    <div style="background:#fffbeb; border:1px solid #fcd34d; ...">
      <strong style="color:#b45309; font-size:10.5pt;">현재 상시 {{ workers }}인 — 즉시 적용 대상은 아닙니다</strong><br/>
      <span style="font-size:8.8pt;">
        상시 근로자 50인 이상 사업장에 중대재해처벌법이 적용됩니다.
        {% set remaining = 50 - workers %}
        {% if remaining > 0 and remaining <= 10 %}
          현재 {{ workers }}명으로 {{ remaining }}명 증가 시 즉시 적용되며,
        {% endif %}
        5인 이상 사업장은 이미 산업안전보건법 처벌 대상이므로 사전 대비가 필요합니다.
      </span>
    </div>
  {% endif %}

  {# 안전관리 방법별 비용·리스크 비교 #}
  {# mockup P2의 cost-table + risk-bar-table 그대로 이전 #}
  {# 변수 없이 정적 테이블 (모든 섹터 공통) #}

  {# 분석 요지 #}
  <div class="sh" style="margin-top:13px;"><h2>분석 요지</h2></div>
  <div style="background:#f1f5f9; ...">
    본 무료 진단 결과, 귀 사업장은
    <strong class="text-blue">{{ total }}건</strong>의 법적 의무에 대하여
    <strong class="text-red">{{ penalty_sum_text }}</strong> 규모의 과태료 노출(합산, 중대재해법 제외)이 확인되었으며,
    {% if csia_applicable %}
      중대재해처벌법이 적용되므로 경영책임자의 형사처벌 리스크까지 존재합니다.
    {% else %}
      중대재해처벌법 위반 시에는 별도로 경영책임자의 형사처벌이 가능합니다.
    {% endif %}
    <br/>
    본 진단은 사업장 기본 정보만으로 도출된 일반 분석이며,
    설비·공정·작업 단위의 개별 의무는 <strong>정밀 진단</strong>을 통해서만 확인할 수 있습니다.
    다음 페이지에서 정밀 진단의 상세 구성과 예상 비용을 안내합니다.
  </div>

  <div class="pf">
    <table style="width:100%;">
      <tr>
        <td>TAI Engineering · taieng.co.kr · contact@taieng.co.kr</td>
        <td style="text-align:right;">2 / 3</td>
      </tr>
    </table>
  </div>
</div>{# /page 2 #}


{# ========== PAGE 3: 섹터별 분기 ========== #}
<div class="page" style="page-break-before: always;">
  {# 간략 헤더 — 섹터별 제목 변경 #}
  <table style="border-bottom:2px solid #1A5FD4; ...">
    <tr>
      <td>
        <span style="font-size:12pt; font-weight:bold; color:#1A5FD4;">TAI</span>
        <span style="font-size:7.5pt; color:#64748b;">
          산업안전 법령진단 분석 보고서
          {% if sector == "BUILDING" %} — 건물
          {% elif sector == "CONSTRUCTION" %} — 건설
          {% endif %}
        </span>
      </td>
      <td style="text-align:right;">{{ company_name }} · {{ report_date }}</td>
    </tr>
  </table>

  {# 1. 확인된 영역 (섹터별 멘트 다름) #}
  <div class="sh"><h2>1. 본 무료 진단에서 확인된 영역</h2></div>
  <div class="area-box area-confirmed">
    <div class="area-title">분석 완료된 항목</div>
    {% if sector == "INDUSTRY" %}
      <div class="area-item">· 사업장 기본 정보 기반 법령 매칭 (업종·규모·위치)</div>
      <div class="area-item">· 일반 법령 의무 {{ total }}건 도출</div>
      <div class="area-item">· 주요 리스크 TOP 5 식별 및 근거 법령 제시</div>
      <div class="area-item">· 중대재해처벌법 적용 여부 자동 판정</div>
    {% elif sector == "BUILDING" %}
      <div class="area-item">· 건축물대장 기반 법령 매칭 (용도·규모·층수)</div>
      <div class="area-item">· 건물 일반 법령 의무 {{ total }}건 도출</div>
      <div class="area-item">· 소방·승강기·전기안전 선임 의무</div>
      <div class="area-item">· 중대재해처벌법 적용 여부 자동 판정</div>
    {% elif sector == "CONSTRUCTION" %}
      <div class="area-item">· 현장 기본 정보 기반 법령 매칭 (공사금액·기간·인원)</div>
      <div class="area-item">· 건설업 일반 법령 의무 {{ total }}건 도출</div>
      <div class="area-item">· 안전관리자·보건관리자 선임 요건 판정</div>
      <div class="area-item">· 중대재해처벌법 적용 여부 자동 판정</div>
    {% endif %}
  </div>

  {# 2. 확인되지 않은 영역 (섹터별 멘트 다름) #}
  <div class="sh" style="margin-top:10px;"><h2>2. 본 무료 진단에서 확인되지 않은 영역</h2></div>
  <div class="area-box area-unconfirmed">
    <div class="area-title">정밀 진단을 통해서만 확인 가능한 항목</div>
    {% if sector == "INDUSTRY" %}
      <div class="area-item">· <strong>시설별 상세 법령</strong> — 건축물·부속시설 개별 의무</div>
      <div class="area-item">· <strong>위험물 취급 규정</strong> — 보유 위험물 종류·수량 기반 의무</div>
      <div class="area-item">· <strong>공정 단위 안전의무</strong> — 작업 공정별 규정 (정밀 등급 이상)</div>
      <div class="area-item">· <strong>설비별 개별 의무</strong> — 보유 설비 개별 점검·검사 규정 (종합 등급)</div>
    {% elif sector == "BUILDING" %}
      <div class="area-item">· 건물 규모 기반 적용 법령 세부 매핑</div>
      <div class="area-item">· 용도별 특수 규정 (근린·의료·판매 등)</div>
      <div class="area-item">· 관리 주체·임차인 책임 구분</div>
      <div class="area-item">· 세부 점검 주기 및 담당자 지정 기준</div>
    {% elif sector == "CONSTRUCTION" %}
      <div class="area-item">· 공사금액 기반 적용 법령 세부 매핑</div>
      <div class="area-item">· 안전관리비 산정 기준 및 요율</div>
      <div class="area-item">· 원청·하청 안전 책임 분배 상세</div>
      <div class="area-item">· 세부 점검 주기 및 담당자 지정 기준</div>
    {% endif %}
  </div>

  {# 3. 정밀 진단 안내 — 섹터별 분기 (핵심!) #}
  {% if paid_tiers.mode == "select" %}
    {# === INDUSTRY: 3개 티어 === #}
    <div class="sh" style="margin-top:11px;">
      <h2>3. 정밀 진단 (유료) — 3개 등급 안내</h2>
      <p>사업장 특성에 맞는 등급을 선택하실 수 있습니다</p>
    </div>
    <div class="tier-grid">
      {% for tier in paid_tiers.tiers %}
      <div class="tier-card">
        <div class="tier-badge {{ tier.badge_class }}">
          {% if tier.badge_class == "basic" %}기본
          {% elif tier.badge_class == "standard" %}정밀
          {% elif tier.badge_class == "premium" %}종합
          {% endif %}
        </div>
        <div class="tier-name">{{ tier.name }}</div>
        <div class="tier-price">{{ "{:,}".format(tier.price) }}원</div>
        <div class="tier-price-note">VAT 별도 · 1회성</div>
        <div class="tier-output-title">산출물</div>
        <div class="tier-output-item">상세 PDF 리포트</div>
        <div class="tier-output-pages">약 {{ tier.pages }}페이지</div>
      </div>
      {% endfor %}
    </div>
    <div style="font-size:8pt; color:#64748b; margin-top:6px;">
      ※ 공통 산출물: 전체 적용 법령 테이블 · 점검 일정 캘린더 · 선임 의무 양식 · 조항별 과태료 시뮬레이션<br>
      ※ 등급별 상세 분석 범위는 safe.taieng.co.kr 신청 페이지에서 확인하실 수 있습니다.
    </div>

  {% else %}
    {# === BUILDING / CONSTRUCTION: 단일 티어 + 상위 힌트 === #}
    <div class="sh" style="margin-top:11px;">
      <h2>
        3. 귀 {% if sector == "BUILDING" %}사업장{% else %}현장{% endif %} 해당 정밀 진단
      </h2>
      <p>
        {% if sector == "BUILDING" %}연면적{% else %}공사금액{% endif %} 자동 판정 결과에 따라 아래 등급이 적용됩니다
      </p>
    </div>

    <div class="single-tier-box">
      <span class="single-tier-badge">
        귀 {% if sector == "BUILDING" %}사업장{% else %}현장{% endif %} 해당
      </span>
      <div style="font-size:12pt; font-weight:bold; color:#0f172a; margin-bottom:4px;">
        {{ paid_tiers.determined.name }}
      </div>
      <div style="font-size:8.5pt; color:#64748b;">{{ paid_tiers.basis }}</div>

      <div class="single-tier-row">
        <div class="single-tier-cell">
          <div class="dlabel">비용</div>
          <div class="dval">{{ "{:,}".format(paid_tiers.determined.price) }}원</div>
          <div style="font-size:7.5pt; color:#64748b;">VAT 별도 · 1회성</div>
        </div>
        <div class="single-tier-cell">
          <div class="dlabel">소요 시간</div>
          <div class="dval">즉시</div>
          <div style="font-size:7.5pt; color:#64748b;">결제 후 자동 분석</div>
        </div>
        <div class="single-tier-cell">
          <div class="dlabel">산출물</div>
          <div class="dval">상세 PDF</div>
          <div style="font-size:7.5pt; color:#64748b;">약 {{ paid_tiers.determined.pages }}페이지</div>
        </div>
      </div>

      <div style="margin-top:10px; padding-top:9px; border-top:1px dashed #cbd5e1;">
        {% if sector == "BUILDING" %}
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· 전체 적용 법령 테이블</div>
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· 층별·용도별 의무 매핑</div>
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· 선임 의무자 양식 (소방·전기·승강기)</div>
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· 건축물 정기점검 일정 캘린더</div>
        {% else %}
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· 공종별 적용 법령 상세</div>
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· 안전관리비 산정 가이드</div>
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· TBM·위험성평가 일정 캘린더</div>
          <div style="font-size:8.8pt; color:#334155; margin:3px 0 3px 8px;">· 원청·하청 안전 책임 구분표</div>
        {% endif %}
      </div>
    </div>

    {# 상위 등급 힌트 (이미 최상위면 표시 안 함) #}
    {% if paid_tiers.upper %}
    <div style="background:#f8fafc; border:1px solid #e2e8f0; ...">
      ※ {{ paid_tiers.upper.threshold }}은 <strong>{{ paid_tiers.upper.name }}({{ "{:,}".format(paid_tiers.upper.price) }}원)</strong>이 적용됩니다.
      입력 항목은 동일하나, 규모 기준에 따라 적용 법령 세트와 분석 결과가 달라집니다.
    </div>
    {% endif %}
  {% endif %}

  {# 활용 포인트 박스 (전 섹터 공통) #}
  <div class="safety-value-box">
    <strong>활용 포인트</strong><br>
    본 유료 리포트는 <strong>관공서 안전감독 시</strong> 법적 의무 이행을 입증하는 근거자료로 활용하실 수 있습니다.
  </div>

  {# TAI 회사 정보 #}
  <div class="company-info">
    <div class="company-info-title">TAI Engineering</div>
    <div class="company-info-row">
      <div class="company-info-cell">
        <div><span class="cil">사업자</span><span class="civ">723-39-01422</span></div>
        <div><span class="cil">주소</span><span class="civ">서울시 강남구 테헤란로79길 6 JS타워 3층</span></div>
        <div><span class="cil">이메일</span><span class="civ">contact@taieng.co.kr</span></div>
        <div><span class="cil">홈페이지</span><span class="civ">taieng.co.kr</span></div>
      </div>
      <div class="company-info-cell" style="border-left: 1px solid #e2e8f0; padding-left: 12px;">
        <div style="font-size:8pt; color:#0f172a; font-weight:bold; margin-bottom:3px;">지식재산권</div>
        <div style="font-size:7.8pt; color:#334155; line-height:1.55;">
          · 법령 자동진단 엔진 외 <strong>특허 출원 8건</strong><br>
          · TAI 상표 등록 완료<br>
          · 법령·시설·공정·설비·작업 연계 분석 기술
        </div>
      </div>
    </div>
  </div>

  {# 4. 활용 안내 #}
  <div class="sh" style="margin-top:10px;"><h2>4. 본 보고서 활용 안내</h2></div>
  <div class="usage-box">
    본 분석 보고서는 귀사의 내부 품의 진행 시 <strong>첨부 근거자료</strong>로 활용하실 수 있습니다.
    품의서 본문에 정밀 진단 신청의 필요성을 기술하시고 본 보고서를 첨부하시면,
    경영진이 법적 의무 건수와 과태료 노출 규모를 객관적으로 확인하실 수 있습니다.
    정밀 진단은 <strong>safe.taieng.co.kr</strong>에서 직접 신청하실 수 있습니다.
  </div>

  <div class="pf" style="margin-top:10px;">
    <table style="width:100%;">
      <tr>
        <td style="font-size:7pt; color:#94a3b8;">※ 본 보고서는 공개된 법령을 기반으로 정밀 분석하여 도출한 참고 자료이며 법적 효력이 없습니다. 실제 적용 여부는 관할 행정기관 또는 법률 전문가에게 확인하시기 바랍니다.</td>
        <td style="text-align:right; white-space:nowrap; vertical-align:top;">3 / 3</td>
      </tr>
    </table>
  </div>
</div>{# /page 3 #}

</body>
</html>
```

---

## 🔧 xhtml2pdf 호환성 주의사항

### ⚠️ 지원 안 되는 CSS
- `flexbox` (display: flex)
- `grid` (display: grid)
- `transform`, `box-shadow`, `filter`
- 복잡한 selector (`:nth-of-type` 일부)

### ✅ 대안 사용
- 레이아웃: `<table>` 사용 (mockup에 이미 적용됨)
- 카드 그리드: `display: table` + `display: table-cell` (✅ 지원)
- 둥근 모서리: `border-radius` (✅ 지원)

### 한글 폰트 — 백엔드에서 자동 주입
백엔드의 `_render_html`이 렌더링 후 `@font-face` CSS + `font-family: "NanumGothic"` 을 자동으로 주입함.
템플릿에서는 그냥 `font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;` 정도로 작성 (백엔드가 덮어씀).

**중요:** 기존 템플릿의 font-family 문자열 형식을 유지해야 백엔드의 `.replace()` 가 정상 동작:
```python
# routers/diagnosis_proposal.py 의 _render_html
html = html.replace(
    'font-family: "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", Arial, sans-serif;',
    'font-family: "NanumGothic", sans-serif;',
)
```

따라서 템플릿에서는 `font-family: "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", Arial, sans-serif;` **정확한 문자열**로 작성.

### 페이지 분리
```css
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
```
또는 각 `.page` 에 `style="page-break-before: always;"` (첫 페이지 제외).

---

## ⚠️ 작업 시 주의사항

### 파일 크기 (메모리 #1)
- 예상 크기: 800~1,000 라인 (현재 proposal_pdf.html보다 약간 큼)
- **권장: Claude Code 로컬 편집 + `git push`**
- MCP `push_files` / `create_or_update_file` 사용 시 커밋 후 GitHub raw URL 에서 직접 파일 열어 리터럴 `\n` 유무 확인 필수

### 이미지·아이콘 사용 금지
- xhtml2pdf는 외부 이미지 로딩 불안정
- 이모지(💡 🏢 🏗️ 등) → **텍스트로 대체** (mockup에 있는 이모지는 viewer-note/sector-switch 영역만이고, 실제 PDF 페이지엔 없음)

### 페이지 페이지 구조 엄수
- PDF는 3페이지 고정 (섹터별로 내용이 달라도 페이지 번호는 `1/3`, `2/3`, `3/3`)
- mockup의 5페이지 (P3 3가지 변형)는 **비교용 표시**일 뿐, 실제 PDF는 선택된 섹터의 **3페이지만** 렌더링

### dev 브랜치 원칙
- 모든 커밋 → `dev`
- 백엔드 PR과 **연계 머지 필수** (템플릿만 먼저 배포되면 UndefinedError)

---

## ✅ 검증

### Step 1: Jinja 문법 검증
```bash
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'), autoescape=False)
tmpl = env.get_template('proposal_pdf.html')
print('Jinja syntax OK')
"
```

### Step 2: 3개 섹터 샘플로 로컬 렌더
```python
# tests/test_proposal_template.py
from routers.diagnosis_proposal import _render_html

contexts = [
    {  # INDUSTRY
        "company_name": "테스트공업", "report_date": "2026년 04월 19일",
        "sector": "INDUSTRY", "sector_label": "산업(제조)",
        "risk_level": "MEDIUM", "workers": 45, "report_no": "TEST0001",
        "total": 131, "appointment": 8, "inspection": 37, "action": 55, "report_notify": 31,
        "law_count": 46, "penalty_sum_text": "약 2억 4,500만원",
        "top5": [
            {"title": "산업재해 발생 보고 미이행", "law": "산업안전보건법 제57조", "penalty": "1,000만원", "amount": 10000000},
            # ...
        ],
        "csia_applicable": False,
        "paid_tiers": {
            "mode": "select",
            "tiers": [
                {"badge_class": "basic", "name": "제조·산업 기본", "price": 79000, "pages": 20},
                {"badge_class": "standard", "name": "제조·산업 정밀", "price": 149000, "pages": 24},
                {"badge_class": "premium", "name": "제조·산업 종합", "price": 249000, "pages": 28},
            ],
        },
    },
    # BUILDING, CONSTRUCTION 케이스도 추가
]

for ctx in contexts:
    html = _render_html(ctx)
    print(f"{ctx['sector']}: {len(html)} bytes, OK")
```

### Step 3: PDF 생성 확인
```python
from routers.diagnosis_proposal import _generate_pdf
pdf_bytes = _generate_pdf(html)
with open(f"/tmp/test_{ctx['sector']}.pdf", "wb") as f:
    f.write(pdf_bytes)
# 생성된 PDF를 열어 시각 확인
```

---

## 📋 최종 체크리스트

- [ ] `mockup.html` 의 `<style>` 섹션을 템플릿에 이전 (viewer-note/sector-switch 제외)
- [ ] 페이지 헤더/푸터 작성
- [ ] P1: 진단 정보 + 경영진 요약 박스 + 법적 의무 카드 4개 + TOP5
- [ ] P2: 중대재해법 + 관리방법 비교 + 분석 요지
- [ ] P3: `{% if paid_tiers.mode == "select" %}` 분기 (INDUSTRY 3카드 vs BUILDING/CONSTRUCTION 단일)
- [ ] 활용 포인트 박스 (공통)
- [ ] TAI 회사 정보 박스 (공통)
- [ ] 활용 안내 (공통)
- [ ] `{{ penalty_sum_text }}` 사용 (P1 경영진 박스 + P2 분석 요지)
- [ ] `font-family` 문자열 유지 (백엔드 `.replace()` 호환)
- [ ] Jinja 문법 검증 PASS
- [ ] 3개 섹터 샘플 렌더링 테스트 PASS
- [ ] PDF 시각 검증 (mockup과 일치)
- [ ] dev 브랜치 커밋·푸시
- [ ] PR 생성 (백엔드 PR과 연계)

---

## 🔗 백엔드 창과의 동기화

| 순서 | 창 | 작업 |
|---|---|---|
| 1 | 백엔드 | DB 마이그레이션 + Storage 버킷 생성 |
| 2 | 백엔드 | `diagnosis_proposal.py` v2.0.0 dev 커밋 |
| 3 | **프론트** | **템플릿 v6 dev 커밋** |
| 4 | 양쪽 | dev → main PR (1개 PR에 2 커밋 포함 권장) |
| 5 | 양쪽 | main 머지 → Fly 배포 → E2E 검증 |

**중요:** 백엔드만 먼저 배포 → context에 `max_penalty_text` 없음 → 기존 템플릿에서 Undefined → 500 에러
**중요:** 템플릿만 먼저 배포 → `paid_tiers` 변수 없음 → Jinja UndefinedError

⇒ **반드시 한 번에 머지** 또는 dev에서 양쪽 완료 후 같은 PR로 main 올리기.
