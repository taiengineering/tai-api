"""Precompiled Profile Matcher — MVP onboarding seed generation.

Batch precompile 철학 유지.
30개 precompiled factory 중 고객 입력과 가장 가까운 프로필을 deterministic 매칭.
결과는 "초기 runtime seed"이지 최종 법률 판단 아님.

매칭 기준 (deterministic, similarity scoring 아님):
1. sector 완전 일치 (BUILDING/CONSTRUCTION/INDUSTRIAL)
2. employee_count 거리 (가장 가까운 구간)
3. sector별 보조 기준:
   - BUILDING: building_area
   - CONSTRUCTION: construction_amount
   - INDUSTRIAL: ksic_code 2자리 일치 + hazardous_material
"""
import os
from typing import Optional, Dict, Any, List


def _get_sb():
    from supabase import create_client
    return create_client(
        os.environ.get('SUPABASE_URL', ''),
        os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    )


PRECOMPILED_SECTORS = {'BUILDING', 'CONSTRUCTION', 'INDUSTRIAL'}


class ProfileMatcher:
    """Deterministic profile matcher.
    All outputs are SEED CANDIDATES for onboarding.
    Not legal conclusions.
    """

    @staticmethod
    def match(sb, input_data: Dict[str, Any]) -> Dict[str, Any]:
        sector = (input_data.get('sector') or '').upper()
        if sector not in PRECOMPILED_SECTORS:
            return {
                'matched': False,
                'reason': f'UNSUPPORTED_SECTOR: {sector}',
                'supported_sectors': list(PRECOMPILED_SECTORS),
            }

        emp = input_data.get('employee_count') or 0
        try:
            emp = int(emp)
        except (ValueError, TypeError):
            emp = 0

        profiles = sb.table('factories').select(
            'id, name, sector, ksic_code, employee_count, '
            'building_area, construction_amount, hazardous_material, '
            'electrical_capacity_kw, contractor_count'
        ).eq('sector', sector).in_(
            'id',
            sb.table('facility_applicability').select('factory_id').limit(1000).execute().data
            and [r['factory_id'] for r in
                 sb.rpc('get_precompiled_factory_ids', {}).execute().data]
            if False else []  # fallback below
        ).execute()

        # Direct approach: get factories that have precompiled data
        precompiled_ids_r = sb.table('facility_applicability').select(
            'factory_id'
        ).limit(1).execute()
        # Get all distinct factory_ids from facility_applicability
        all_app = sb.rpc('', {})  # can't use DISTINCT via supabase-py easily
        # Simpler: query factories with sector filter, then check which have data
        candidates = sb.table('factories').select(
            'id, name, sector, ksic_code, employee_count, '
            'building_area, construction_amount, hazardous_material, '
            'electrical_capacity_kw, contractor_count'
        ).eq('sector', sector).not_.is_('employee_count', 'null').order(
            'employee_count'
        ).execute()

        if not candidates.data:
            return {
                'matched': False,
                'reason': f'NO_PROFILES_FOR_SECTOR: {sector}',
            }

        # Filter to only factories with precompiled applicability
        # (check via a single count query per candidate)
        valid = []
        for c in candidates.data:
            check = sb.table('facility_applicability').select(
                'id', count='exact'
            ).eq('factory_id', c['id']).limit(1).execute()
            if check.count and check.count > 0:
                valid.append(c)

        if not valid:
            return {
                'matched': False,
                'reason': 'NO_PRECOMPILED_DATA',
            }

        best = ProfileMatcher._find_closest(valid, input_data, sector, emp)
        unsupported = ProfileMatcher._check_unsupported(input_data, best)

        return {
            'matched': True,
            'matched_factory_id': best['id'],
            'matched_factory_name': best.get('name', ''),
            'match_method': 'PRECOMPILED_PROFILE_MATCH',
            'match_detail': {
                'sector': sector,
                'input_employee_count': emp,
                'matched_employee_count': best.get('employee_count'),
                'input_ksic': input_data.get('ksic_code'),
                'matched_ksic': best.get('ksic_code'),
            },
            'unsupported_conditions': unsupported,
            'warning': (
                'This is an onboarding seed based on the closest '
                'precompiled profile. Not a final legal determination. '
                'Results require user approval before SaaS registration.'
            ),
        }

    @staticmethod
    def _find_closest(
        profiles: List[Dict], input_data: Dict, sector: str, emp: int
    ) -> Dict:
        def score(p):
            s = 0
            p_emp = p.get('employee_count') or 0
            # Employee count distance (primary)
            s += abs(p_emp - emp) * 10

            if sector == 'BUILDING':
                p_area = float(p.get('building_area') or 0)
                i_area = float(input_data.get('building_area') or 0)
                s += abs(p_area - i_area) * 0.01

            elif sector == 'CONSTRUCTION':
                p_amt = float(p.get('construction_amount') or 0)
                i_amt = float(input_data.get('construction_amount') or 0)
                s += abs(p_amt - i_amt) * 0.0000001

            elif sector == 'INDUSTRIAL':
                p_ksic = (p.get('ksic_code') or '')[:2]
                i_ksic = (input_data.get('ksic_code') or '')[:2]
                if p_ksic and i_ksic and p_ksic == i_ksic:
                    s -= 500  # bonus for same 2-digit KSIC
                p_haz = p.get('hazardous_material') or False
                i_haz = input_data.get('hazardous_material') or False
                if p_haz == i_haz:
                    s -= 100  # bonus for matching hazard status

            return s

        return min(profiles, key=score)

    @staticmethod
    def _check_unsupported(input_data: Dict, matched: Dict) -> List[str]:
        gaps = []
        m_emp = matched.get('employee_count') or 0
        i_emp = input_data.get('employee_count') or 0
        if i_emp and m_emp:
            ratio = abs(i_emp - m_emp) / max(i_emp, 1)
            if ratio > 0.5:
                gaps.append(
                    f'EMPLOYEE_COUNT_GAP: input={i_emp} matched={m_emp} '
                    f'(>{int(ratio*100)}% difference)'
                )
        i_ksic = input_data.get('ksic_code', '')
        m_ksic = matched.get('ksic_code', '')
        if i_ksic and m_ksic and i_ksic[:2] != (m_ksic or '')[:2]:
            gaps.append(
                f'KSIC_MISMATCH: input={i_ksic} matched={m_ksic}'
            )
        return gaps
