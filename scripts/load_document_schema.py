#!/usr/bin/env python3
"""
load_document_schema.py — compiled JSON → document_schema_registry DB 적재

compiled JSON의 field_candidates를 document_schema_registry에 적재.
AI 추론 없음. 컴파일된 데이터 그대로 적재.

실행:
  cd ~/Desktop/tai-engineering/tai-api
  railway run python3 scripts/load_document_schema.py --dry-run
  railway run python3 scripts/load_document_schema.py
"""
import argparse, json, os, sys, glob, re
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: railway run 으로 실행하세요."); sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
KST = timezone(timedelta(hours=9))
COMPILED_DIR = Path("./form_originals_hwp/compiled")

# 섹션 추론 규칙 (필드 위치 기반, deterministic)
SECTION_MAP = {
    'site_name': ('BASIC_INFO', '기본정보'),
    'business_registration_no': ('BASIC_INFO', '기본정보'),
    'site_management_no': ('BASIC_INFO', '기본정보'),
    'address': ('BASIC_INFO', '기본정보'),
    'industry_type': ('BASIC_INFO', '기본정보'),
    'representative': ('BASIC_INFO', '기본정보'),
    'phone': ('BASIC_INFO', '기본정보'),
    'worker_count': ('BASIC_INFO', '기본정보'),
    'business_start_no': ('BASIC_INFO', '기본정보'),
    'author_name': ('AUTHOR_INFO', '작성자정보'),
    'verifier_name': ('AUTHOR_INFO', '작성자정보'),
    'date_field': ('AUTHOR_INFO', '작성자정보'),
    'signature': ('SIGNATURE', '서명'),
    'submit_to': ('SUBMISSION', '제출'),
    'attachment': ('EVIDENCE', '증빙자료'),
    'remarks': ('REMARKS', '비고'),
    'corrective_action': ('ACTION', '조치사항'),
    'inspection_result': ('INSPECTION', '점검결과'),
    'accident_death_count': ('ACCIDENT_STATS', '재해현황'),
    'disease_death_count': ('ACCIDENT_STATS', '재해현황'),
    'accident_casualty_count': ('ACCIDENT_STATS', '재해현황'),
    'disease_casualty_count': ('ACCIDENT_STATS', '재해현황'),
    'accident_rate': ('ACCIDENT_STATS', '재해현황'),
    'death_rate_per_10k': ('ACCIDENT_STATS', '재해현황'),
    'appointment_date': ('APPOINTMENT', '선임정보'),
    'license_no': ('APPOINTMENT', '선임정보'),
    'permit_no': ('PERMIT', '허가정보'),
    'construction_name': ('CONSTRUCTION', '공사정보'),
    'construction_period': ('CONSTRUCTION', '공사정보'),
    'construction_amount': ('CONSTRUCTION', '공사정보'),
    'client_name': ('CONSTRUCTION', '공사정보'),
    'contractor_name': ('CONSTRUCTION', '공사정보'),
    'supervisor_name': ('CONSTRUCTION', '공사정보'),
    'designer_name': ('CONSTRUCTION', '공사정보'),
    'retention_period': ('ADMIN', '관리정보'),
    'report_no': ('ADMIN', '관리정보'),
}

FIELD_TYPE_MAP = {
    'date_field': 'date',
    'signature': 'signature',
    'attachment': 'image',
    'worker_count': 'number',
    'accident_death_count': 'number',
    'disease_death_count': 'number',
    'accident_casualty_count': 'number',
    'disease_casualty_count': 'number',
    'accident_rate': 'number',
    'death_rate_per_10k': 'number',
    'construction_amount': 'number',
}

RENDER_MAP = {
    'text': 'text-input',
    'number': 'number-input',
    'date': 'date-picker',
    'signature': 'signature-pad',
    'image': 'image-gallery',
    'select': 'select-dropdown',
    'checkbox': 'checkbox-group',
    'table': 'data-table',
    'evidence_ref': 'evidence-viewer',
}


def convert_document_type(doc_id: str) -> str:
    """doc_id를 document_type으로 변환 (하이픈→언더스코어)"""
    return doc_id.replace('-', '_').upper()


def load_compiled_json(path: Path) -> dict:
    return json.load(open(path, encoding='utf-8'))


def process_one(pkg: dict) -> list[dict]:
    """compiled JSON 1건 → document_schema_registry 행들"""
    doc_id = pkg.get('document_id', '')
    doc_type = convert_document_type(doc_id)
    form_name = pkg.get('form_name', doc_id)
    fields = pkg.get('field_candidates', [])

    rows = []
    sections_seen = set()
    section_rows = []

    for i, fc in enumerate(fields):
        canon = fc.get('canonical_field_candidate', 'unclassified_field')
        raw_label = fc.get('raw_label', '')
        # 긴 라벨에서 핵심만 추출
        label = raw_label[:80].strip()

        # 섹션 결정 (deterministic)
        sec_code, sec_title = SECTION_MAP.get(canon, ('GENERAL', '일반'))
        if canon in ('numbered_field', 'unclassified_field'):
            sec_code, sec_title = 'FORM_BODY', '서식본문'

        # 필드 타입
        field_type = FIELD_TYPE_MAP.get(canon, 'text')

        # 렌더 컴포넌트
        render = RENDER_MAP.get(field_type, 'text-input')

        # 필수 수준 (서명/작성자/날짜는 MANDATORY 후보)
        req_level = 'OPTIONAL'
        if canon in ('signature', 'author_name', 'date_field', 'site_name'):
            req_level = 'MANDATORY'
        elif canon in ('worker_count', 'business_registration_no', 'address'):
            req_level = 'RECOMMENDED'

        # field_code: canonical + 순번 (중복 방지)
        field_code = f"{canon}_{i+1:03d}"

        rows.append({
            'document_type': doc_type,
            'schema_version': '1.0.0',
            'section_code': sec_code,
            'section_title': sec_title,
            'field_code': field_code,
            'field_label': label,
            'field_type': field_type,
            'field_order': i + 1,
            'required_level': req_level,
            'repeatable': False,
            'source_mapping': None,
            'validation_rule': json.dumps({'rules': ['required']}) if req_level == 'MANDATORY' else None,
            'render_component': render,
            'source_trace': None,
            'source_reason': f"HWP 원문 추출: {raw_label[:100]}",
            'enabled': True,
            'status': 'CANDIDATE',
        })

        # 섹션 수집
        if sec_code not in sections_seen:
            sections_seen.add(sec_code)
            section_rows.append({
                'document_type': doc_type,
                'schema_version': '1.0.0',
                'section_code': sec_code,
                'section_title': sec_title,
                'section_order': len(sections_seen),
                'enabled': True,
            })

    return rows, section_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--file', type=str, default=None)
    args = ap.parse_args()

    print('='*70)
    print('  Document Schema Registry Loader')
    print('='*70)

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(COMPILED_DIR.glob('*.json'))
    if args.limit:
        files = files[:args.limit]

    print(f'\n  대상: {len(files)}건')

    total_fields = 0
    total_sections = 0

    for i, f in enumerate(files, 1):
        pkg = load_compiled_json(f)
        doc_id = pkg.get('document_id', f.stem)
        rows, sec_rows = process_one(pkg)

        if args.dry_run:
            print(f'  [{i:3}/{len(files)}] {doc_id:30} fields={len(rows):3d} sections={len(sec_rows)}')
        else:
            doc_type = convert_document_type(doc_id)
            # 기존 데이터 삭제 (upsert 대신 replace)
            sb.table('document_schema_registry').delete().eq('document_type', doc_type).execute()
            sb.table('document_schema_section').delete().eq('document_type', doc_type).execute()

            # 섹션 INSERT
            if sec_rows:
                for chunk in [sec_rows[i:i+50] for i in range(0, len(sec_rows), 50)]:
                    sb.table('document_schema_section').insert(chunk).execute()

            # 필드 INSERT (100건씩 청크)
            for chunk in [rows[i:i+100] for i in range(0, len(rows), 100)]:
                sb.table('document_schema_registry').insert(chunk).execute()

            print(f'  [{i:3}/{len(files)}] {doc_id:30} ✓ F={len(rows)} S={len(sec_rows)}')

        total_fields += len(rows)
        total_sections += len(sec_rows)

    print(f'\n{"="*70}')
    print(f'  완료: {len(files)}건')
    print(f'  총 필드: {total_fields}건')
    print(f'  총 섹션: {total_sections}건')
    print(f'  상태: 전부 CANDIDATE (Human Review 필요)')
    print(f'={""*69}')


if __name__ == '__main__':
    main()
