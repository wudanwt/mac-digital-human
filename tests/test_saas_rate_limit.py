from starlette.requests import Request

from app.saas.middleware import RateLimitMiddleware
from app.saas.worker_ui import JS as WORKER_UI_JS


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"authorization", b"Bearer test-token")],
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
        }
    )


def test_worker_polling_uses_a_separate_rate_limit_bucket() -> None:
    status_key = RateLimitMiddleware._bucket_key(
        _request("GET", "/api/saas/workers/status")
    )
    save_key = RateLimitMiddleware._bucket_key(
        _request("PATCH", "/api/saas/courses/course-id")
    )

    assert status_key.startswith("poll:")
    assert save_key.startswith("interactive:")
    assert status_key.removeprefix("poll:") == save_key.removeprefix("interactive:")


def test_worker_ui_does_not_repoll_for_its_own_dom_updates() -> None:
    assert "if(radio===mountedRadio)return" in WORKER_UI_JS
    assert "},15000);" in WORKER_UI_JS
    assert "!document.hidden" in WORKER_UI_JS
    assert "if(badge.textContent!==badgeText)badge.textContent=badgeText" in WORKER_UI_JS
