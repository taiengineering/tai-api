# Cursor/Claude Code 작업지시: factory-list.html 법령마크 + 전체법령적용

> 대상: tai-admin `tadmin/.../factory-list.html`
> 참조 설계: taieng/docs/2026-05-26_legal_status_system.md

---

## 1. 목록 테이블에 법령마크 컨럼 추가

테이블 헤더에 "법령" 컨럼 추가 ("상태" 옆).

각 행에 법령마크 배지:
```js
function legalBadge(status, appliedAt) {
  if (status === 'APPLIED') return '<span class="badge bg-label-success" title="적용완료 ' + (appliedAt||'').slice(0,10) + '">🟢 적용</span>';
  if (status === 'NEEDS_UPDATE') return '<span class="badge bg-label-warning">🟡 재진단</span>';
  return '<span class="badge bg-label-danger">🔴 미적용</span>';
}
```

목록 렌더링에서:
```js
'<td>' + legalBadge(f.legal_status, f.legal_applied_at) + '</td>'
```

---

## 2. 상단에 "전체 법령적용" 버튼

시설목록 카드 헤더 오른쪽에 추가:
```html
<button class="btn btn-warning btn-sm" id="btnBatchLegal" onclick="openBatchLegalModal()">
  <i class="ti tabler-scale me-1"></i>전체 법령적용
  <span class="badge bg-white text-warning ms-1" id="batchLegalCount">0</span>
</button>
```

페이지 로드 시 법령 상태 요약 API 호출:
```js
async function loadLegalSummary() {
  var companyId = effectiveCompanyId || '';
  try {
    var res = await apiCall('GET', '/legal-status/summary?company_id=' + encodeURIComponent(companyId));
    var d = res.data || {};
    var pending = d.pending || 0;
    document.getElementById('batchLegalCount').textContent = String(pending);
    document.getElementById('btnBatchLegal').disabled = pending === 0;
  } catch(e) {}
}
```

---

## 3. 전체 법령적용 모달

```html
<div class="modal fade" id="batchLegalModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header">
      <h5 class="modal-title">전체 법령적용</h5>
      <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
    </div>
    <div class="modal-body">
      <p id="batchLegalDesc">미적용 N건 + 재진단 M건 = 총 K건을 법령진단하시겠습니까?</p>
      <div class="progress d-none" id="batchLegalProgress" style="height:8px">
        <div class="progress-bar" id="batchLegalBar" style="width:0%"></div>
      </div>
      <div id="batchLegalResult" class="d-none mt-3"></div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">취소</button>
      <button type="button" class="btn btn-warning" id="btnBatchLegalRun" onclick="runBatchLegal()">
        <i class="ti tabler-player-play me-1"></i>실행
      </button>
    </div>
  </div></div>
</div>
```

---

## 4. 배치 실행 JS

```js
async function openBatchLegalModal() {
  var companyId = effectiveCompanyId || '';
  var res = await apiCall('GET', '/legal-status/summary?company_id=' + encodeURIComponent(companyId));
  var d = res.data || {};
  document.getElementById('batchLegalDesc').textContent =
    '미적용 ' + d.not_applied + '건 + 재진단 ' + d.needs_update + '건 = 총 ' + d.pending + '건을 법령진단하시겠습니까?';
  document.getElementById('batchLegalProgress').classList.add('d-none');
  document.getElementById('batchLegalResult').classList.add('d-none');
  document.getElementById('btnBatchLegalRun').disabled = false;
  new bootstrap.Modal(document.getElementById('batchLegalModal')).show();
}

async function runBatchLegal() {
  var btn = document.getElementById('btnBatchLegalRun');
  btn.disabled = true;
  var prog = document.getElementById('batchLegalProgress');
  var bar = document.getElementById('batchLegalBar');
  prog.classList.remove('d-none');
  bar.style.width = '10%';

  try {
    var companyId = effectiveCompanyId || '';
    bar.style.width = '30%';
    var res = await apiCall('POST', '/legal-status/batch-apply?company_id=' + encodeURIComponent(companyId));
    bar.style.width = '100%';
    var d = res.data || {};
    var result = document.getElementById('batchLegalResult');
    result.classList.remove('d-none');
    result.innerHTML = '<div class="alert alert-' + (d.failed > 0 ? 'warning' : 'success') + ' mb-0">' +
      '성공 <strong>' + d.success + '</strong>건' +
      (d.failed > 0 ? ', 실패 <strong>' + d.failed + '</strong>건' : '') + '</div>';
    showToast('success', '전체 법령적용 완료');
    loadList();
    loadLegalSummary();
  } catch(e) {
    showToast('error', e.message || '법령적용 실패');
  } finally {
    btn.disabled = false;
  }
}
```

---

## 5. 개별 시설 법령적용 (행 클릭 시 사이드패널)

사이드패널에 법령마크 + "법령진단 실행" 버튼 추가:
- 클릭 시 `POST /legal-engine/apply/{factory_id}` 호출
- 성공 후 `POST /legal-status/factories/{factory_id}/mark-applied` 호출
- 목록 새로고침

---

## 체크리스트

- [ ] 목록 테이블: 법령 컨럼 + legalBadge()
- [ ] 상단: 전체법령적용 버튼 + 건수 배지
- [ ] 모달: 확인 + 프로그레스 + 결과
- [ ] 페이지 로드 시 loadLegalSummary() 호출
- [ ] 사이드패널: 법령마크 + 개별 진단 버튼
