"""Cloud SaaS entrypoint, isolated from the Apple-Silicon desktop studio.

Run locally:
    pip install -e '.[saas,dev]'
    uvicorn app.saas_main:app --host 0.0.0.0 --port 8918
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .saas.api import router as saas_router
from .saas.avatar_cards_ui import css_response as avatar_cards_css_response
from .saas.avatar_matting_ui import css_response as avatar_matting_css_response
from .saas.avatar_matting_ui import javascript_response as avatar_matting_javascript_response
from .saas.avatar_ui import javascript_response as avatar_javascript_response
from .saas.bootstrap import initialize
from .saas.course_avatar_mode_ui import css_response as course_avatar_mode_css_response
from .saas.course_avatar_mode_ui import javascript_response as course_avatar_mode_javascript_response
from .saas.course_studio_asset_picker_ui import css_response as course_studio_asset_picker_css_response
from .saas.course_studio_asset_picker_ui import javascript_response as course_studio_asset_picker_javascript_response
from .saas.course_studio_ui import css_response as course_studio_css_response
from .saas.course_studio_ui import javascript_response as course_studio_javascript_response
from .saas.course_studio_upgrade import css_response as course_studio_upgrade_css_response
from .saas.course_studio_upgrade import javascript_response as course_studio_upgrade_javascript_response
from .saas.course_voice_ui import css_response as course_voice_css_response
from .saas.course_voice_ui import javascript_response as course_voice_javascript_response
from .saas.interaction_patch import javascript_response as interaction_javascript_response
from .saas.job_detail_ui import css_response as job_detail_css_response
from .saas.job_detail_ui import javascript_response as job_detail_javascript_response
from .saas.middleware import RateLimitMiddleware
from .saas.operations_ui import javascript_response as operations_javascript_response
from .saas.polish_ui import javascript_response as polish_javascript_response
from .saas.product_ui import javascript_response as product_javascript_response
from .saas.settings import saas_settings
from .saas.system_assets_ui import javascript_response as system_assets_javascript_response
from .saas.theme_ui import css_response as theme_css_response
from .saas.voice_clone_guard_ui import javascript_response as voice_clone_guard_javascript_response
from .saas.web import dashboard_html
from .saas.worker_ui import javascript_response as worker_javascript_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    initialize()
    yield


app = FastAPI(
    title=saas_settings.app_name,
    version="0.5.0",
    description="Multi-tenant digital-human micro-course SaaS control plane.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(saas_settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
if saas_settings.trusted_hosts and saas_settings.trusted_hosts != ("*",):
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(saas_settings.trusted_hosts))
app.add_middleware(RateLimitMiddleware)
app.include_router(saas_router)


def _enhanced_dashboard() -> HTMLResponse:
    base = dashboard_html()
    body = base.body.decode("utf-8")
    body = body.replace(
        "</head>",
        '<link rel="stylesheet" href="/saas-theme.css">'
        '<link rel="stylesheet" href="/avatar-cards.css">'
        '<link rel="stylesheet" href="/avatar-matting.css">'
        '<link rel="stylesheet" href="/course-studio.css">'
        '<link rel="stylesheet" href="/course-studio-upgrade.css">'
        '<link rel="stylesheet" href="/course-studio-asset-picker.css">'
        '<link rel="stylesheet" href="/course-avatar-mode.css">'
        '<link rel="stylesheet" href="/course-voice.css">'
        '<link rel="stylesheet" href="/job-detail.css"></head>',
    )
    body = body.replace(
        "</body>",
        '<script src="/avatar-ui.js"></script>'
        '<script src="/voice-clone-guard.js"></script>'
        '<script src="/avatar-matting.js"></script>'
        '<script src="/product-ui.js"></script>'
        '<script src="/operations-ui.js"></script>'
        '<script src="/polish-ui.js"></script>'
        '<script src="/interaction-patch.js"></script>'
        '<script src="/course-studio.js?v=20260920-3"></script>'
        '<script src="/course-studio-upgrade.js?v=20260920-3"></script>'
        '<script src="/system-assets.js"></script>'
        '<script src="/course-studio-asset-picker.js"></script>'
        '<script src="/course-avatar-mode.js?v=20260920-3"></script>'
        '<script src="/course-voice.js"></script>'
        '<script src="/worker-ui.js"></script>'
        '<script src="/job-detail.js"></script></body>',
    )
    return HTMLResponse(body)


@app.get("/saas-theme.css", include_in_schema=False)
def saas_theme():
    return theme_css_response()


@app.get("/avatar-cards.css", include_in_schema=False)
def avatar_cards_css():
    return avatar_cards_css_response()


@app.get("/avatar-matting.css", include_in_schema=False)
def avatar_matting_css():
    return avatar_matting_css_response()


@app.get("/course-studio.css", include_in_schema=False)
def course_studio_css():
    return course_studio_css_response()


@app.get("/course-studio-upgrade.css", include_in_schema=False)
def course_studio_upgrade_css():
    return course_studio_upgrade_css_response()


@app.get("/course-studio-asset-picker.css", include_in_schema=False)
def course_studio_asset_picker_css():
    return course_studio_asset_picker_css_response()


@app.get("/course-avatar-mode.css", include_in_schema=False)
def course_avatar_mode_css():
    return course_avatar_mode_css_response()


@app.get("/course-voice.css", include_in_schema=False)
def course_voice_css():
    return course_voice_css_response()


@app.get("/job-detail.css", include_in_schema=False)
def job_detail_css():
    return job_detail_css_response()


@app.get("/avatar-ui.js", include_in_schema=False)
def avatar_ui_script():
    return avatar_javascript_response()


@app.get("/voice-clone-guard.js", include_in_schema=False)
def voice_clone_guard_script():
    return voice_clone_guard_javascript_response()


@app.get("/avatar-matting.js", include_in_schema=False)
def avatar_matting_script():
    return avatar_matting_javascript_response()


@app.get("/product-ui.js", include_in_schema=False)
def product_ui_script():
    return product_javascript_response()


@app.get("/operations-ui.js", include_in_schema=False)
def operations_ui_script():
    return operations_javascript_response()


@app.get("/polish-ui.js", include_in_schema=False)
def polish_ui_script():
    return polish_javascript_response()


@app.get("/interaction-patch.js", include_in_schema=False)
def interaction_ui_script():
    return interaction_javascript_response()


@app.get("/course-studio.js", include_in_schema=False)
def course_studio_script():
    return course_studio_javascript_response()


@app.get("/course-studio-upgrade.js", include_in_schema=False)
def course_studio_upgrade_script():
    return course_studio_upgrade_javascript_response()


@app.get("/system-assets.js", include_in_schema=False)
def system_assets_script():
    return system_assets_javascript_response()


@app.get("/course-studio-asset-picker.js", include_in_schema=False)
def course_studio_asset_picker_script():
    return course_studio_asset_picker_javascript_response()


@app.get("/course-avatar-mode.js", include_in_schema=False)
def course_avatar_mode_script():
    return course_avatar_mode_javascript_response()


@app.get("/course-voice.js", include_in_schema=False)
def course_voice_script():
    return course_voice_javascript_response()


@app.get("/worker-ui.js", include_in_schema=False)
def worker_ui_script():
    return worker_javascript_response()


@app.get("/job-detail.js", include_in_schema=False)
def job_detail_script():
    return job_detail_javascript_response()


@app.get("/", include_in_schema=False)
def index():
    return _enhanced_dashboard()


@app.get("/app", include_in_schema=False)
def app_shell():
    return _enhanced_dashboard()


__all__ = ["app"]
