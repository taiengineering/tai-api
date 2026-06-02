# verification/test_condition_normalizer.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.condition_normalizer import build_condition_context

# 완료 기준: 입력 4개 → 원하는 콘텍스트 4개
result = build_condition_context(
    processes=['용접', '도장'],
    equipments=['크레인'],
    work_types=['철골공사'],
)
print('result:', result)

expected = {
    'has_welding': True,
    'has_painting': True,
    'has_crane': True,
    'construction_steel': True,
}
assert result == expected, f'FAIL: {result}'
print('PASS')

# 중복 테스트
result2 = build_condition_context(
    processes=['용접', '아크용접'],  # 돠 다 has_welding
    equipments=[],
    work_types=[],
)
print('\ndedup result:', result2)
assert result2 == {'has_welding': True}, f'FAIL dedup: {result2}'
print('PASS dedup')
