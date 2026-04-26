# 작업지시서 보충: 이미지 압축 모듈 연동

**작성일**: 2026-04-25
**상태**: tai-image-compress.js 배포 완료 → tai-document.js 연동 필요

---

## 구조

```
tai-image-compress.js  ← 독립 모듈 (배포 완료)
  │
  ├── 단독 사용 가능 (inspect.html, tbm.html 등)
  │     const compressed = await TaiImageCompress.compress(file, { category: 'inspection' });
  │
  └── tai-document.js 내부에서 자동 호출
        upload() → 이미지면 자동 압축 → Storage 업로드
```

## tai-image-compress.js (배포 완료)

**위치**: `tadmin/full-version/assets/js/tai/tai-image-compress.js`
**레포**: tai-admin (main)

### 핵심 API

```javascript
// 단일 압축
const compressed = await TaiImageCompress.compress(file, { category: 'inspection' });

// 다중 압축
const results = await TaiImageCompress.compressMultiple(files, { category: 'corrective' });

// 커스텀 설정
const small = await TaiImageCompress.compress(file, { maxWidth: 800, quality: 0.6 });

// 결과 요약
const summary = TaiImageCompress.getSummary(originalFile, compressedFile);
// → { originalKB: 5120, compressedKB: 280, savedPercent: 95 }
```

### 카테고리별 프리셋 (자동 적용)

| 카테고리 | maxWidth | quality | format | 용도 |
|---|---|---|---|---|
| inspection | 1920 | 80% | WebP | 점검 사진 |
| corrective | 1920 | 80% | WebP | 시정조치 전/후 |
| tbm | 1280 | 75% | WebP | TBM 서명/기록 |
| certificate | 2560 | 85% | WebP | 인증서 (글씨 가독성) |
| equipment | 1920 | 80% | WebP | 설비 사진 |
| facility_drawing | null | - | - | **압축 안 함** (도면 원본 보존) |
| general | 1920 | 80% | WebP | 기타 |

### 안전장치

- 이미지가 아닌 파일 → 원본 그대로 반환
- HEIC/HEIF (iPhone) → 원본 반환 (Canvas 미지원)
- 이미 작은 파일 (500KB 이하 + 해상도 이내) → 원본 반환
- 압축 후 오히려 커지면 → 원본 반환
- Canvas 오류 시 → 원본 반환 (절대 실패하지 않음)

---

## tai-document.js 수정 사항

### 1. HTML에서 로드 순서

```html
<script src="/assets/js/tai/tai-image-compress.js"></script>
<script src="/assets/js/tai/tai-document.js"></script>
```

### 2. _handleFiles 메서드 수정

기존 작업지시서의 `_handleFiles`에 압축 로직 추가:

```javascript
async _handleFiles(files, opts, listEl) {
  for (const f of files) {
    const item = document.createElement('div');
    item.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 12px;' +
      'background:#f1f5f9;border-radius:10px;margin-bottom:6px;font-size:14px;';
    item.innerHTML = `<span>${TaiDocument.getFileIcon(f.name.split('.').pop())}</span>
      <span style="flex:1;">${f.name}</span>
      <span style="color:#94a3b8;">${TaiDocument.formatFileSize(f.size)}</span>
      <span class="status" style="color:#6366f1;">압축 중...</span>`;
    listEl.appendChild(item);

    try {
      // ★ 이미지 자동 압축
      let uploadFile = f;
      if (typeof TaiImageCompress !== 'undefined' && TaiImageCompress.isImage(f)) {
        uploadFile = await TaiImageCompress.compress(f, { category: opts.category });
        if (uploadFile._compressed) {
          item.querySelector('.status').textContent = 
            `${uploadFile._ratio}% 절감 → 업로드 중...`;
        } else {
          item.querySelector('.status').textContent = '업로드 중...';
        }
      } else {
        item.querySelector('.status').textContent = '업로드 중...';
      }

      await this.upload(uploadFile, opts);
      const sizeText = TaiDocument.formatFileSize(uploadFile.size);
      item.querySelector('.status').textContent = `✅ ${sizeText}`;
      item.querySelector('.status').style.color = '#22c55e';
    } catch (err) {
      item.querySelector('.status').textContent = '❌ 실패';
      item.querySelector('.status').style.color = '#ef4444';
    }
  }
  if (opts.onComplete) opts.onComplete();
}
```

### 3. upload 메서드에도 자동 압축 옵션

`upload()` 직접 호출 시에도 압축 적용:

```javascript
async upload(file, opts = {}) {
  // 자동 압축 (autoCompress: false로 비활성화 가능)
  let uploadFile = file;
  if (opts.autoCompress !== false && 
      typeof TaiImageCompress !== 'undefined' && 
      TaiImageCompress.isImage(file)) {
    uploadFile = await TaiImageCompress.compress(file, { category: opts.category });
  }

  const fd = new FormData();
  fd.append('file', uploadFile);
  // ... 나머지 기존 로직
}
```

---

## 단독 사용 예시 (tai-document.js 없이)

### PWA 점검 화면 (inspect.html)

```html
<script src="tai-image-compress.js"></script>
<script>
document.getElementById('photo-input').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  const compressed = await TaiImageCompress.compress(file, { category: 'inspection' });
  
  // 압축 결과 표시
  const summary = TaiImageCompress.getSummary(file, compressed);
  console.log(`${summary.originalKB}KB → ${summary.compressedKB}KB (${summary.savedPercent}% 절감)`);
  
  // FormData에 압축된 파일 사용
  const fd = new FormData();
  fd.append('photo', compressed);
  await fetch('/api/inspections/photo', { method: 'POST', body: fd });
});
</script>
```

### 시정조치 전/후 사진

```html
<script src="tai-image-compress.js"></script>
<script>
async function handleCorrectivePhoto(file, type) {
  const compressed = await TaiImageCompress.compress(file, { category: 'corrective' });
  // type = 'before' 또는 'after'
  // ... 업로드 로직
}
</script>
```

---

## 검증 체크리스트

- [ ] tai-image-compress.js 로드 확인 (`typeof TaiImageCompress !== 'undefined'`)
- [ ] 8MB JPEG → 300KB WebP 압축 확인
- [ ] PDF 파일 → 원본 그대로 반환 확인
- [ ] 300KB 작은 이미지 → 원본 반환 확인 (불필요한 재압축 방지)
- [ ] facility_drawing 카테고리 → 압축 안 함 확인
- [ ] 모바일 (375px) 카메라 촬영 → 압축 후 업로드 정상
- [ ] WebP 미지원 브라우저 → JPEG fallback (TaiImageCompress.supportsWebP())
- [ ] tai-document.js 없이 단독 사용 정상
