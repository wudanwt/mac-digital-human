from __future__ import annotations

from types import SimpleNamespace

from app.saas.render_core import build_page_plans


def test_page_plans_use_frozen_overrides_without_database_state() -> None:
    deck = SimpleNamespace(
        slides=[
            SimpleNamespace(index=1, title="第一页", narration="PPT 备注一", layout="pip"),
            SimpleNamespace(index=2, title="第二页", narration="PPT 备注二", layout="pip"),
        ]
    )
    script = [
        {
            "index": 1,
            "narration": "冻结讲稿一",
            "layout": "full_slide",
            "avatar_mode": "original",
        }
    ]
    settings = {"layout": "split", "subtitle_mode": "burn"}

    plans = build_page_plans(deck, script, settings)

    assert [plan.index for plan in plans] == [1, 2]
    assert plans[0].narration == "冻结讲稿一"
    assert plans[0].layout == "full_slide"
    assert plans[1].narration == "PPT 备注二"
    assert plans[1].layout == "split"
    assert plans[0].override is not script[0]
