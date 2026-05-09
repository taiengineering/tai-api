"""TAI 법령엔진 v3.0 — 형태소 분석 엔진 (Kiwi 래핑).

본 모듈은 Kiwi 형태소 분석기를 TAI v3.0 룰 엔진에 맞게 래핑한다.
Day 1 검증에서 도출한 핵심 시그니처(tail-3 패턴, EF 종결 여부 등)를
helper 함수로 캐싀화하여 Stage 1/2 룰 매칭이 단순 문자열 비교로
가능하게 한다.

설계 원칙 (MASTER_HANDOFF §2):
  - LLM 사용 X. Kiwi + 명시적 룰만.
  - 법령 보전. 토큰화는 형태소 분해이며 의미해석 X.
  - 빈 입력은 빈 결과 반환 (예외 X).

계층: Service (FastAPI import 금지).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

from kiwipiepy import Kiwi, Token

if TYPE_CHECKING:
    # 타입 힌트만 — 런타임 의존성 X
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)


# ----- POS tag 카테고리 -----
# Day 1 검증: EF (어말어미) 존재가 HEADER vs ITEM 의 1차 분별자.
EF_TAGS = frozenset({"EF"})

# 부호류 — has_ef 판정 시 제외 대상 (마침표 등)
PUNCT_TAGS = frozenset({
    "SF", "SP", "SE", "SS", "SO", "SW", "SSO", "SSC", "SC",
})


@dataclass
class TokenizationMeta:
    """토큰화 결과에 부가하는 메타.

    Day 1 발견을 직접 코드화한 것. Stage 2 sub_type 룰 매칭 시
    이 메타를 보고 빠르게 분기 가능.
    """
    tail_3: str       # 마지막 3 토큰의 form/tag 시그니처
    head_1: str       # 첫 토큰의 form/tag
    has_ef: bool      # EF 종결 여부 (HEADER vs ITEM)
    last_tag: str     # 마지막 의미 토큰의 tag (부호 제외)
    last_form: str    # 마지막 의미 토큰의 form
    token_count: int  # 전체 토큰 수


class MorphemeEngine:
    """Kiwi 래핑 엔진.

    Usage:
        engine = MorphemeEngine()
        tokens = engine.tokenize("사업주는 ... 설치하여야 한다.")
        tokens, meta = engine.analyze("벌금에 처한다.")
        # meta.has_ef -> True (HEADER 후보)
        # meta.tail_3 -> "처하/VV + ᆫ다/EF + ./SF"
    """

    def __init__(self, load_default_dict: bool = True) -> None:
        logger.info("Kiwi 인스턴스 초기화 (load_default_dict=%s)", load_default_dict)
        self.kiwi = Kiwi(load_default_dict=load_default_dict)
        self._user_dict_count = 0

    # ----- 토큰화 -----

    def tokenize(self, text: str) -> list[Token]:
        """단일 텍스트 토큰화. 빈 입력은 빈 리스트."""
        if not text or not text.strip():
            return []
        return self.kiwi.tokenize(text)

    def tokenize_batch(self, texts: list[str]) -> list[list[Token]]:
        """일괄 토큰화. Kiwi 멀티스레드 활용."""
        if not texts:
            return []
        return list(self.kiwi.tokenize(texts))

    def analyze(self, text: str) -> tuple[list[Token], TokenizationMeta]:
        """토큰화 + 메타 동시 산출. Stage 2 룰 매칭에 직접 사용."""
        tokens = self.tokenize(text)
        meta = self._build_meta(tokens)
        return tokens, meta

    # ----- 시그니처 헬퍼 (Day 1 발견 직결) -----

    @staticmethod
    def get_tail_signature(tokens: list[Token], n: int = 3) -> str:
        """마지막 n 토큰의 form/tag 시그니처.

        예: tail-3 -> "하/VX + ᆫ다/EF + ./SF"
        """
        if not tokens:
            return ""
        tail = tokens[-n:] if len(tokens) >= n else tokens
        return " + ".join(f"{t.form}/{t.tag}" for t in tail)

    @staticmethod
    def get_head_signature(tokens: list[Token], n: int = 1) -> str:
        """첫 n 토큰의 form/tag. EXCEPTION_CLAUSE 검출용 (다만/MAG)."""
        if not tokens:
            return ""
        head = tokens[:n]
        return " + ".join(f"{t.form}/{t.tag}" for t in head)

    @staticmethod
    def get_last_meaningful_token(tokens: list[Token]) -> Token | None:
        """부호류 제외 마지막 의미 토큰."""
        for tok in reversed(tokens):
            if tok.tag in PUNCT_TAGS:
                continue
            return tok
        return None

    @classmethod
    def has_ef_terminator(cls, tokens: list[Token]) -> bool:
        """마지막 의미 토큰이 EF (어말어미)인지.

        Day 1 발견: HEADER 7종은 모두 True, ITEM (할 것/한 자)은 False.
        """
        last = cls.get_last_meaningful_token(tokens)
        if last is None:
            return False
        return last.tag in EF_TAGS

    def _build_meta(self, tokens: list[Token]) -> TokenizationMeta:
        last = self.get_last_meaningful_token(tokens)
        return TokenizationMeta(
            tail_3=self.get_tail_signature(tokens, 3),
            head_1=self.get_head_signature(tokens, 1),
            has_ef=self.has_ef_terminator(tokens),
            last_tag=last.tag if last else "",
            last_form=last.form if last else "",
            token_count=len(tokens),
        )

    # ----- 사전 관리 -----

    def add_user_word(
        self,
        term: str,
        pos_tag: str = "NNG",
        score: float = 0.0,
    ) -> bool:
        """단일 어휘를 Kiwi 사전에 추가."""
        if not term:
            return False
        try:
            self.kiwi.add_user_word(term, pos_tag, score)
            self._user_dict_count += 1
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("사전 추가 실패: term=%s reason=%s", term, e)
            return False

    def load_dict_terms(self, terms: Iterable[dict[str, Any]]) -> int:
        """dict_legal_terms 행 리스트를 Kiwi 사전에 일괄 등록.

        Args:
            terms: [{"term": str, "pos_tag": str, "score": float}, ...]

        Returns:
            성공 등록 수.
        """
        added = 0
        total = 0
        for row in terms:
            total += 1
            term = row.get("term")
            pos = row.get("pos_tag", "NNG")
            try:
                score = float(row.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            if not term:
                continue
            if self.add_user_word(term, pos, score):
                added += 1
        logger.info("사전 일괄 등록: %d/%d", added, total)
        return added

    def load_verified_dict_from_db(
        self,
        supabase: SupabaseClient,
        term_type: str | None = None,
        limit: int = 1000,
    ) -> int:
        """dict_legal_terms에서 verified=true 어휘를 DB에서 로드.

        Args:
            supabase: Supabase client (db.supabase_client.get_supabase()에서 주입)
            term_type: 'LAW_NAME' / 'AGENCY_NAME' / 'TECH_TERM' / 'GENERIC' 또는 None (전체)
            limit: 최대 로드 수

        Returns:
            등록 성공 수.
        """
        query = (
            supabase.table("dict_legal_terms")
            .select("term, pos_tag, score, term_type")
            .eq("verified", True)
        )
        if term_type:
            query = query.eq("term_type", term_type)
        res = query.limit(limit).execute()
        rows = res.data or []
        return self.load_dict_terms(rows)

    @property
    def user_dict_size(self) -> int:
        return self._user_dict_count
