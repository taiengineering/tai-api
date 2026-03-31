# TAI Cursor 작업지시서 — 공정 수동 등록 (백엔드)

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: `routers/factory_process.py` (수정)

---

## 배경

SaaS 고객이 법령엔진으로 진단 후 실제 운영 중인 공정을 등록하려 할 때,
KCSC 표준 공정 목록에 없는 공정(예: 회사 자체 명칭, 특수 공정)을 직접 입력할 수 없습니다.

**현재 상태:**
- `factory_process` 테이블에 `process_name_manual` 컬럼 이미 있음 ✅
- `source` 컬럼 있음 (기본값 'DB') ✅
- API `/factory-process/{factory_id}/processes` 존재하나 MANUAL 처리 미흡 ⚠️

**목표:** `source='MANUAL'` 공정을 등록/수정/삭제/조회할 수 있도록 API 보완

---

## DB 구조 (이미 완료 — DDL 불필요)

```sql
factory_process (
  id               UUID PK,
  factory_id       UUID FK -> factories,
  process_id       TEXT,          -- KCSC 공정 코드 (MANUAL이면 NULL)
  process_lv1      TEXT,          -- 대분류
  process_lv2      TEXT,          -- 중분류
  process_lv3      TEXT,          -- 소분류
  process_lv4      TEXT,          -- 세분류
  process_path     TEXT,          -- 경로 문자열
  process_name_manual TEXT,       -- 수동 입력 공정명
  is_primary       BOOLEAN,
  is_active        BOOLEAN,
  source           TEXT,          -- 'DB' | 'MANUAL'
  created_at       TIMESTAMPTZ
)
```

---

## 작업 1: POST /factory-process/{factory_id}/processes — MANUAL 공정 등록

### 현재 엔드포인트 수정

기존 body에 `source`, `process_name_manual` 필드 추가 처리:

```python
class ProcessCreateBody(BaseModel):
    process_id:          Optional[str] = None   # KCSC 코드 (MANUAL이면 생략)
    process_name_manual: Optional[str] = None   # 수동 공정명 (MANUAL이면 필수)
    source:              str = 'DB'             # 'DB' | 'MANUAL'
    process_lv1:         Optional[str] = None
    process_lv2:         Optional[str] = None
    process_lv3:         Optional[str] = None
    process_lv4:         Optional[str] = None
    is_primary:          bool = False
```

### 검증 로직 추가
```python
if body.source == 'MANUAL':
    if not body.process_name_manual or not body.process_name_manual.strip():
        raise HTTPException(status_code=422,
            detail='수동 공정 등록 시 process_name_manual은 필수입니다.')
    # process_id는 자동 생성 (MANUAL-{timestamp})
    import time
    process_id = f'MANUAL-{int(time.time())}'
else:
    if not body.process_id:
        raise HTTPException(status_code=422,
            detail='KCSC 공정 등록 시 process_id는 필수입니다.')
    process_id = body.process_id
```

### INSERT 데이터 구성
```python
insert_data = {
    'factory_id':          factory_id,
    'process_id':          process_id,
    'process_name_manual': body.process_name_manual,
    'process_lv1':         body.process_lv1 or '기타',
    'process_lv2':         body.process_lv2,
    'process_lv3':         body.process_lv3,
    'process_lv4':         body.process_lv4,
    'process_path':        ' > '.join(filter(None, [
                               body.process_lv1, body.process_lv2,
                               body.process_lv3, body.process_name_manual
                           ])),
    'is_primary':          body.is_primary,
    'is_active':           True,
    'source':              body.source,
}
```

---

## 작업 2: GET /factory-process/{factory_id}/processes — 목록 조회 보완

현재 응답에 MANUAL 공정이 포함되지 않거나 `process_name_manual`이 빠진 경우 수정:

```python
# select에 process_name_manual, source 반드시 포함
res = supabase.table('factory_process').select(
    'id, process_id, process_lv1, process_lv2, process_lv3, process_lv4, '
    'process_path, process_name_manual, source, is_primary, is_active, created_at'
).eq('factory_id', factory_id).eq('is_active', True).execute()

# 응답 정규화: display_name 필드 추가
for p in (res.data or []):
    p['display_name'] = p.get('process_name_manual') or p.get('process_lv3') or p.get('process_lv2') or p.get('process_lv1') or p.get('process_id', '')
    p['is_manual'] = (p.get('source') == 'MANUAL')
```

---

## 작업 3: DELETE /factory-process/{factory_id}/processes/{process_id} — 삭제

```python
@router.delete('/{factory_id}/processes/{process_record_id}')
async def delete_factory_process(factory_id: str, process_record_id: str):
    supabase = get_supabase()
    # soft delete
    supabase.table('factory_process').update({'is_active': False}) \
        .eq('id', process_record_id).eq('factory_id', factory_id).execute()
    return {'status': 'success', 'message': '공정이 삭제되었습니다.'}
```

---

## 작업 4: PATCH /factory-process/{factory_id}/processes/{process_record_id} — 수정

```python
class ProcessUpdateBody(BaseModel):
    process_name_manual: Optional[str] = None
    process_lv1:         Optional[str] = None
    process_lv2:         Optional[str] = None
    is_primary:          Optional[bool] = None

@router.patch('/{factory_id}/processes/{process_record_id}')
async def update_factory_process(factory_id: str, process_record_id: str, body: ProcessUpdateBody):
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=422, detail='수정할 내용이 없습니다.')
    supabase.table('factory_process').update(update_data) \
        .eq('id', process_record_id).eq('factory_id', factory_id).execute()
    return {'status': 'success'}
```

---

## 완료 체크리스트

```
□ POST /factory-process/{factory_id}/processes — source=MANUAL 처리 추가
□ GET  /factory-process/{factory_id}/processes — process_name_manual, source, display_name, is_manual 포함
□ DELETE 엔드포인트 추가 (soft delete)
□ PATCH  엔드포인트 추가 (수정)
□ Railway 배포 후 버전 확인
```

## 검증

```bash
# MANUAL 공정 등록
curl -X POST https://api.taieng.co.kr/factory-process/{factory_id}/processes \
  -d '{"source":"MANUAL","process_name_manual":"도금공정","process_lv1":"표면처리"}'
# → id, process_id(MANUAL-xxx), is_manual:true 포함 응답

# 목록 조회
curl https://api.taieng.co.kr/factory-process/{factory_id}/processes
# → MANUAL 공정이 display_name으로 표시
```
