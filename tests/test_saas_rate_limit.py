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


def test_bulk_media_and_worker_calls_do_not_exhaust_interactive_bucket() -> None:
    media_key = RateLimitMiddleware._bucket_key(
        _request("GET", "/api/saas/course-tools/ppt/deck/slides/20/thumbnail")
    )
    asset_key = RateLimitMiddleware._bucket_key(
        _request("GET", "/api/saas/assets/asset-id/content")
    )
    worker_key = RateLimitMiddleware._bucket_key(
        _request("POST", "/api/saas/internal/render/tasks/claim")
    )
    save_key = RateLimitMiddleware._bucket_key(
        _request("PATCH", "/api/saas/courses/course-id")
    )

    assert media_key.startswith("media:")
    assert asset_key.startswith("media:")
    assert worker_key.startswith("worker:")
    assert save_key.startswith("interactive:")
    assert len({media_key, asset_key, worker_key, save_key}) == 3


def test_noninteractive_buckets_have_higher_but_finite_limits() -> None:
    middleware = RateLimitMiddleware(lambda scope, receive, send: None)
    middleware.limit = 120

    assert middleware._limit_for("interactive") == 120
    assert middleware._limit_for("poll") == 360
    assert middleware._limit_for("worker") == 600
    assert middleware._limit_for("media") == 1200


def test_worker_ui_does_not_repoll_for_its_own_dom_updates() -> None:
    assert "if(radio===mountedRadio)return" in WORKER_UI_JS
    assert "},15000);" in WORKER_UI_JS
    assert "!document.hidden" in WORKER_UI_JS
    assert "if(badge.textContent!==badgeText)badge.textContent=badgeText" in WORKER_UI_JS
