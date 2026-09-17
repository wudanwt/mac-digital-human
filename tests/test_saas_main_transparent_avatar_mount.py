from __future__ import annotations

import inspect

import app.saas_main as saas_main


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
