"""OBJ-03 (tai-rebuild) — Route-order shadowing lint.

배경: FastAPI는 라우트를 '등록 순서'대로 매칭한다. 같은 부모 경로에서
단일 세그먼트 동적 라우트 `.../{param}` 가 정적 형제 `.../summary`,
`.../overview` 보다 **먼저 등록**되면, 정적 경로 요청이 동적 라우트에
흡수되어 도달 불가가 된다. (이미 `/equipment-assets/overview` 가 이
버그로 500 → 재구현된 선례가 있음: docs/tai-rebuild/03·04.)

이 테스트는 앱의 실제 라우트 테이블을 introspect 하여, 동일 (method, 부모)
아래에서 동적 캐치올이 정적 형제보다 먼저 등록된 경우를 실패로 처리한다.
런타임 동작은 바꾸지 않는다(검사 전용).
"""
from __future__ import annotations

from collections import defaultdict

import pytest


def _split_parent_leaf(path: str) -> tuple[str, str]:
    p = path.rstrip("/")
    if "/" not in p:
        return "", p
    parent, leaf = p.rsplit("/", 1)
    return parent, leaf


def _is_dynamic_leaf(leaf: str) -> bool:
    return leaf.startswith("{") and leaf.endswith("}")


def _load_app():
    try:
        from main import app  # FastAPI 인스턴스
    except Exception as e:  # pragma: no cover - 환경 미비 시 스킵
        pytest.skip(f"main.app import 실패(환경 미비): {e}")
    return app


def test_no_dynamic_route_shadows_static_sibling():
    from fastapi.routing import APIRoute

    app = _load_app()
    routes = [r for r in app.routes if isinstance(r, APIRoute)]

    # (method, parent) -> [(registration_index, leaf, full_path)]
    by_parent: dict[tuple[str, str], list[tuple[int, str, str]]] = defaultdict(list)
    for idx, r in enumerate(routes):
        parent, leaf = _split_parent_leaf(r.path)
        for method in (r.methods or set()):
            if method in ("HEAD", "OPTIONS"):
                continue
            by_parent[(method, parent)].append((idx, leaf, r.path))

    problems: list[str] = []
    for (method, _parent), items in by_parent.items():
        dynamic = [(i, l, p) for (i, l, p) in items if _is_dynamic_leaf(l)]
        static = [(i, l, p) for (i, l, p) in items if not _is_dynamic_leaf(l)]
        for di, _dl, dp in dynamic:
            for si, _sl, sp in static:
                if di < si:  # 동적 캐치올이 정적 형제보다 먼저 등록 → 섀도잉
                    problems.append(
                        f"{method} {sp} 는 먼저 등록된 동적 라우트 {dp} 에 가려집니다"
                        f" (register idx {dp}={di} < {sp}={si})."
                    )

    assert not problems, (
        "라우트 순서 섀도잉 감지 (동적 /{param} 캐치올을 정적 형제 아래로 이동하세요):\n"
        + "\n".join(sorted(set(problems)))
    )
