"""TAI 법령엔진 v3.0 — 형태소 분석 엔진 (Kiwi 래핑).

본 모듈은 Kiwi 형태소 분석기를 TAI v3.0 룰 엔진에 맞게 래핑한다.
Day 1 검증에서 도출한 핵심 시그니처(tail-3 패턴, EF 종결 여부 등)를
helper 함수로 캐싀화하여 Stage 1/2 룰 매칭이 단순 문자열 비교로
가능하게 한다.

설계 원칙 (MASTER_HANDOFF §2):
  - LLM 사용 X. Kiwi + 명시적 룰만.
  - 법령 보전. 토큰화는 형태소 분해이며 의미해석 X.
  - 빈 입력은 빈 결과 반환 (예외 X).

다단어 사전 처리 (Track C 권고 반영, 2026-05-09):
  - 공백 포함 어휘 (예: \"고압가스 안전관리법\") → add_re_word 정규식 기반 등록 (안정)
  - 공백 없는 어휘 → add_user_word 일반 등록
  - 목적: dict_legal_terms의 다단어 법령명·기관명 안정 토큰화

다단어 score 가중치 (Track C v1.1 패치, 2026-05-09):
  - 부분문자열 충돌 케이스 관찰: '하수도법 시행규칙' 등 3건이 '하_IC + 수도법 시행규칙_NNP' 식으로 잘림
  - 원인: 다단어 정규식 어휘와 짧은 분해가 score 동률(0.0)일 때 Kiwi가 짧은 분해 선호
  - 해결: MULTIWORD_SCORE_BOOST=10.0을 다단어 add_re_word에 적용 (짧은 분해보다 무조건 우선)

자동 사전 로드:
  - __init__ 시 supabase 주입 + auto_load_verified_dict=True (기본)
  - 인스턴스 생성 시점에 dict_legal_terms.verified=true 자동 로드
  - 실패 시 warning 후 계속 진행 (degraded)

페이지네이션 (P0 패치, 2026-05-12):
  - load_verified_dict_from_db: PostgREST max-rows=1000 기본 정책 회피
  - .limit(N) → .range(start, end) 페이지네이션 (page_size=1000, max_pages=50)
  - 기존 1,725건 중 1,000건만 로드되던 문제 해결 (마스터 §3 P0)
  - 호환: 기존 limit 인자는 deprecated (warning + 무시)

계층: Service (FastAPI import 금지).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

from kiwipiepy import Kiwi, Token

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)


# ----- POS tag 카테고리 -----
EF_TAGS = frozenset({"EF"})
PUNCT_TAGS = frozenset({
    "SF", "SP", "SE", "SS", "SO", "SW", "SSO", "SSC", "SC",
})

# ----- 다단어 우선순위 가중치 -----
# Kiwi 0.22에서 add_re_word(pattern, tag, score) 의 score가 0.0일 때,
# 다단어 어휘의 부분문자열이 이미 등록된 경우(예: '수도법'이 dict에 있고
# '하수도법 시행규칙'도 dict에 있을 때) 짧은 분해가 선택될 수 있다.
# 따라서 다단어에 강한 score 가중치를 부여해 무조건 우선되게 한다.
MULTIWORD_SCORE_BOOST: float = 10.0

# ----- 페이지네이션 기본값 (P0 패치, 2026-05-12) -----
# PostgREST 서버 측 max-rows 기본값과 일치 (1000) → 한 페이지 1라운드트립.
DEFAULT_PAGE_SIZE: int = 1000
# 안전 상한: 50,000건 (현재 dict_legal_terms 14,943건 → 충분 여유).
DEFAULT_MAX_PAGES: int = 50


@dataclass
class TokenizationMeta:
    """토큰화 결과에 부가하는 메타.

    Day 1 발견을 직접 코드화한 것. Stage 2 sub_type 룰 매칭 시
    이 메타를 보고 빠르게 분기 가능.
    """
    tail_3: str
    head_1: str
    has_ef: bool
    last_tag: str
    last_form: str
    token_count: int


class MorphemeEngine:
    """Kiwi 래핑 엔진.

    Usage:
        engine = MorphemeEngine()                    # DB 없이
        engine = MorphemeEngine(supabase=sb)         # 자동 사전 로드
        tokens, meta = engine.analyze("벌금에 처한다.")
    """

    def __init__(
        self,
        load_default_dict: bool = True,
        supabase: SupabaseClient | None = None,
        auto_load_verified_dict: bool = True,
    ) -> None:
        logger.info("Kiwi 인스턴스 초기화 (load_default_dict=%s)", load_default_dict)
        self.kiwi = Kiwi(load_default_dict=load_default_dict)
        self._user_dict_count = 0
        self.supabase = supabase

        # Track C 권고: 자동 사전 로드 (dict_legal_terms verified=true)
        if supabase is not None and auto_load_verified_dict:
            try:
                loaded = self.load_verified_dict_from_db(supabase)
                logger.info("MorphemeEngine 자동 사전 로드: %d개", loaded)
            except Exception as e:  # noqa: BLE001
                logger.warning("자동 사전 로드 실패 (degraded 계속): %s", e)

    # ----- 토큰화 -----

    def tokenize(self, text: str) -> list[Token]:
        """단일 텍스트 토큰화. 빈 입력은 빈 리스트."""
        if not text or not text.strip():
            return []
        return self.kiwi.tokenize(text)

    def tokenize_batch(self, texts: list[str]) -> list[list[Token]]:
        """일괄 토큰화."""
        if not texts:
            return []
        return list(self.kiwi.tokenize(texts))

    def analyze(self, text: str) -> tuple[list[Token], TokenizationMeta]:
        """토큰화 + 메타 동시 산출."""
        tokens = self.tokenize(text)
        meta = self._build_meta(tokens)
        return tokens, meta

    # ----- 시그니처 헬퍼 (Day 1 발견 직결) -----

    @staticmethod
    def get_tail_signature(tokens: list[Token], n: int = 3) -> str:
        if not tokens:
            return ""
        tail = tokens[-n:] if len(tokens) >= n else tokens
        return " + ".join(f"{t.form}/{t.tag}" for t in tail)

    @staticmethod
    def get_head_signature(tokens: list[Token], n: int = 1) -> str:
        if not tokens:
            return ""
        head = tokens[:n]
        return " + ".join(f"{t.form}/{t.tag}" for t in head)

    @staticmethod
    def get_last_meaningful_token(tokens: list[Token]) -> Token | None:
        for tok in reversed(tokens):
            if tok.tag in PUNCT_TAGS:
                continue
            return tok
        return None

    @classmethod
    def has_ef_terminator(cls, tokens: list[Token]) -> bool:
        """Day 1 발견: HEADER 7종은 모두 True, ITEM (할 것/한 자)은 False."""
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
        """단일 어휘를 Kiwi 사전에 추가.

        다단어 (공백 포함) → add_re_word 정규식 등록 (안정) +
            score 가중치 적용 (max(score, MULTIWORD_SCORE_BOOST))
        단일어 → add_user_word 일반 등록 (일반 score)

        Track C v1.1 패치 (2026-05-09):
            부분문자열 충돌(예: '수도법' 단일어 + '하수도법 시행규칙' 다단어)
            시 다단어가 짧은 분해에 밀리는 케이스 해결.
        """
        if not term:
            return False
        try:
            if " " in term:
                # 다단어: 정규식 메타문자 escape + score 가중치
                pattern = re.escape(term)
                effective_score = max(score, MULTIWORD_SCORE_BOOST)
                self.kiwi.add_re_word(pattern, pos_tag, effective_score)
            else:
                self.kiwi.add_user_word(term, pos_tag, score)
            self._user_dict_count += 1
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("사전 추가 실패: term=%r reason=%s", term, e)
            return False

    def load_dict_terms(self, terms: Iterable[dict[str, Any]]) -> int:
        """dict_legal_terms 행 리스트를 Kiwi 사전에 일괄 등록."""
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
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        limit: int | None = None,
    ) -> int:
        """dict_legal_terms.verified=true 어휘를 DB에서 페이지네이션으로 로드.

        P0 패치 (2026-05-12): PostgREST 서버 측 max-rows=1000 기본 정책으로
        인해 .limit(N>1000)이 실제로는 1000만 반환하던 버그 해결.
        .range(start, end)는 inclusive — Range 헤더로 명시적 페이지 요청.

        Args:
            supabase: Supabase Client.
            term_type: 'LAW_NAME' 등 필터링. None이면 전체.
            page_size: 페이지 크기. 기본 1000 (서버 정책 일치).
            max_pages: 안전 상한. 기본 50 → 50,000건.
            limit: **deprecated** — 페이지네이션으로 자동 처리. 무시됨 (warning).

        Returns:
            load_dict_terms의 added 카운트.
        """
        if limit is not None:
            logger.warning(
                "load_verified_dict_from_db: 'limit' 인자는 deprecated. "
                "페이지네이션으로 자동 처리 (PostgREST max-rows 회피). 무시됨."
            )

        accumulated: list[dict[str, Any]] = []
        pages_read = 0
        for page in range(max_pages):
            q = (
                supabase.table("dict_legal_terms")
                .select("term, pos_tag, score, term_type")
                .eq("verified", True)
            )
            if term_type:
                q = q.eq("term_type", term_type)
            start = page * page_size
            end = start + page_size - 1
            res = q.range(start, end).execute()
            rows = res.data or []
            pages_read += 1
            if not rows:
                break
            accumulated.extend(rows)
            if len(rows) < page_size:
                break
        else:
            # for-else: break 없이 max_pages 도달 + 마지막 페이지가 풀이면 추가 가능성
            if accumulated and len(accumulated) % page_size == 0:
                logger.warning(
                    "load_verified_dict_from_db: max_pages=%d 도달 — "
                    "추가 데이터 가능성. max_pages 인자 상향 검토 필요.",
                    max_pages,
                )

        logger.info(
            "verified=true 페이지네이션 로드: %d건 (%d 페이지, page_size=%d)",
            len(accumulated),
            pages_read,
            page_size,
        )
        return self.load_dict_terms(accumulated)

    @property
    def user_dict_size(self) -> int:
        return self._user_dict_count
