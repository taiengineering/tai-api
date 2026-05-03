# diagnosis.html — 가격 직전 사고 경고 섹션 추가

**작성일**: 2026-05-03
**대상 파일**: `taiengineering/taieng` 레포의 `nexas/service/diagnosis.html`
**작업 도구**: Cursor (200줄+ 파일이므로 MCP 직접 수정 금지)

## 콘티

가격 섹션(보호 영역) 직전에 신규 섹션 ⑦-2 신설:

- 메인멘트 + 서브멘트 (다크 배경 + 흰 텍스트)
- 이미지 6장 그리드 (3×2, 반응형)
- 톤: 딥 다크 navy 그라데이션. 가격 섹션의 회색으로 자연스럽게 전환.
- 흐름: ⑦신뢰(다크navy) → ⑦-1앱프리뷰(회색) → ⑦-2신규(딥다크) → 가격(회색) → CTA(navy→blue 그라데이션)

## 보호 영역 절대 수정 금지

다음 마커 이하는 일체 손대지 말 것 (KG이니시스 카드 심사 중):

```
<!-- 가격 (보호 영역 — 카드 심사 중, 절대 수정 금지) -->
```

## 변경점 1 — CSS 추가

**위치**: `<style>` 블록 내, 다음 줄 **바로 위**에 삽입

```
  /* ── 가격 (보호 영역) ── */
```

**삽입할 내용**:

```css
  /* ── 사고 경고 + 진단 시각화 (가격 직전) ── */
  .alert-vis-section {
    background: linear-gradient(180deg, #0a1424 0%, #0f2b4a 100%);
    padding: 100px 0 90px;
    color: #fff;
  }
  .av-msg {
    text-align: center;
    max-width: 720px;
    margin: 0 auto 56px;
  }
  .av-msg h2 {
    font-size: clamp(1.55rem, 3.3vw, 2.15rem);
    font-weight: 900;
    line-height: 1.45;
    color: #fff;
    margin-bottom: 24px;
    letter-spacing: -.02em;
  }
  .av-msg p {
    font-size: 1rem;
    line-height: 1.85;
    color: rgba(255,255,255,.78);
    margin: 0;
  }
  .av-card {
    background: #fff;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 18px 50px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.06);
    transition: transform .2s, box-shadow .2s;
  }
  .av-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 24px 60px rgba(0,0,0,.45);
  }
  .av-card img {
    width: 100%;
    height: auto;
    display: block;
  }
  @media (max-width: 991px) {
    .alert-vis-section { padding: 64px 0 56px; }
    .av-msg { margin-bottom: 36px; }
  }
```

## 변경점 2 — HTML 섹션 추가

**위치**: 다음 줄 **바로 위**에 삽입

```
<!-- 가격 (보호 영역 — 카드 심사 중, 절대 수정 금지) -->
```

**삽입할 내용**:

```html
<!-- ⑦-2 사고 경고 + 진단 시각화 (가격 직전) -->
<section class="alert-vis-section">
  <div class="container">
    <div class="av-msg">
      <h2>사고는 준비되지 않은 순간에 발생합니다<br>그래서 미리 확인해야 합니다</h2>
      <p>지금 상태를 모른 채 운영하는 것이 가장 위험합니다<br>법령진단은 현재 상태를 기준으로 보여줍니다</p>
    </div>
    <div class="row g-4">
      <div class="col-md-6 col-lg-4">
        <div class="av-card">
          <img src="https://vwlahtguyggrhvslabax.supabase.co/storage/v1/object/public/site-assets/diagnosis/diagnosis1.png" alt="법령진단 1" loading="lazy">
        </div>
      </div>
      <div class="col-md-6 col-lg-4">
        <div class="av-card">
          <img src="https://vwlahtguyggrhvslabax.supabase.co/storage/v1/object/public/site-assets/diagnosis/diagnosis2.png" alt="법령진단 2" loading="lazy">
        </div>
      </div>
      <div class="col-md-6 col-lg-4">
        <div class="av-card">
          <img src="https://vwlahtguyggrhvslabax.supabase.co/storage/v1/object/public/site-assets/diagnosis/diagnosis3.png" alt="법령진단 3" loading="lazy">
        </div>
      </div>
      <div class="col-md-6 col-lg-4">
        <div class="av-card">
          <img src="https://vwlahtguyggrhvslabax.supabase.co/storage/v1/object/public/site-assets/diagnosis/diagnosis4.png" alt="법령진단 4" loading="lazy">
        </div>
      </div>
      <div class="col-md-6 col-lg-4">
        <div class="av-card">
          <img src="https://vwlahtguyggrhvslabax.supabase.co/storage/v1/object/public/site-assets/diagnosis/diagnosis5.png" alt="법령진단 5" loading="lazy">
        </div>
      </div>
      <div class="col-md-6 col-lg-4">
        <div class="av-card">
          <img src="https://vwlahtguyggrhvslabax.supabase.co/storage/v1/object/public/site-assets/diagnosis/diagnosis6.png" alt="법령진단 6" loading="lazy">
        </div>
      </div>
    </div>
  </div>
</section>
```

## 검증 체크리스트

- [ ] CSS 삽입 후 `.price-section` 스타일이 그대로 남아 있음
- [ ] HTML 삽입 후 `<section class="price-section" id="pricing">` 시작 태그 변동 없음
- [ ] 결제 form `#diag_inicis_form` 변동 없음
- [ ] `diagPay()` 스크립트 변동 없음
- [ ] 데스크톱(>=992px): 이미지 3열
- [ ] 태블릿(768~991px): 이미지 2열
- [ ] 모바일(<768px): 이미지 1열
- [ ] 6장 이미지 모두 로드 확인 (Storage 공개 버킷 site-assets/diagnosis/)

## 후속 옵션 (요청 시 반영)

1. 이미지에 캡션 표시 필요 시: `.av-card` 하단에 `.av-caption` 추가
2. 다크 톤이 부담스러우면 흰 배경 + navy 텍스트 버전으로 톤다운 가능
3. 이미지 클릭 시 라이트박스(magnific-popup, 이미 로드됨) 연동 가능
