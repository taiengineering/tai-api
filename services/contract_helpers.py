from datetime import datetime, timezone
from services.time import now_kst, serialize_external_utc


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


def _expert_type_label(expert_type: str) -> str:
    return {"EXPERT": "선임대행", "CONSULTING": "컨설팅", "REPAIR": "수선중개"}.get(expert_type, expert_type)


def _entity_type_label(entity_type: str) -> str:
    return {
        "INDIVIDUAL": "개인",
        "SOLE_PROPRIETOR": "개인사업자",
        "SIMPLIFIED_TAX": "간이과세자",
        "CORPORATION": "법인",
    }.get(entity_type, entity_type)


def _default_sections(expert_type: str) -> dict:
    return {
        "article3": "<p>을은 갑의 사업장에서 관계 법령에서 정한 안전관리 업무를 성실히 이행하여야 한다.</p>",
        "article5": "<p>갑은 계약 체결 후 계약금액을 TAI엔지니어링이 지정한 가상계좌로 입금한다.</p>",
        "article6": "<p>을은 계약 내용을 성실히 이행하여야 하며, 관계 법령의 변경 시 상호 협의하여 계약 내용을 조정할 수 있다.</p>",
        "article7": "<p>계약 당사자 일방이 계약을 위반하거나 계약의 목적을 달성할 수 없는 경우 서면 통보 후 계약을 해지할 수 있다.</p>",
    }
