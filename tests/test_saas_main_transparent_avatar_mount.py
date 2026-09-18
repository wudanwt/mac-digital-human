from __future__ import annotations

import inspect

import app.saas_main as saas_main
from app.saas.avatar_cards_ui import CSS as avatar_cards_css


def test_transparent_avatar_assets_are_mounted_in_app_shell() -> None:
    source = inspect.getsource(saas_main._enhanced_dashboard)
    assert "/avatar-matting.css" in source
    assert "/avatar-matting.js" in source
    assert "/course-avatar-mode.css" in source
    assert "/course-avatar-mode.js" in source


def test_transparent_avatar_routes_exist() -> None:
    paths = {path for route in saas_main.app.routes if (path := getattr(route, "path", None))}
    assert "/avatar-matting.css" in paths
    assert "/avatar-matting.js" in paths
    assert "/course-avatar-mode.css" in paths
    assert "/course-avatar-mode.js" in paths


def test_avatar_card_styles_are_mounted_and_scoped() -> None:
    source = inspect.getsource(saas_main._enhanced_dashboard)
    assert "/avatar-cards.css" in source
    assert ".card:has([data-dh-image-id]) h3" in avatar_cards_css
    assert "letter-spacing: -." not in avatar_cards_css
