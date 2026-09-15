"""Cloud SaaS entrypoint, isolated from the Apple-Silicon desktop studio.

Run locally:
    pip install -e '.[saas,dev]'
    uvicorn app.saas_main:app --host 0.0.0.0 --port 8918
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .saas.api import router as saas_router
from .saas.bootstrap import initialize
from .saas.middleware import RateLimitMiddleware
from .saas.settings import saas_settings
from .saas.web import dashboard_html


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


@app.get("/", include_in_schema=False)
def index():
    return dashboard_html()


@app.get("/app", include_in_schema=False)
def app_shell():
    return dashboard_html()


__all__ = ["app"]
