"""SaaS entrypoint.

Run locally with:
    uvicorn app.saas_main:app --host 0.0.0.0 --port 8918

The existing desktop/web studio remains in ``app.main``. Importing it here lets
cloud-only routes evolve independently without duplicating the current UI.
"""

from .main import app
from .saas.api import router as saas_router

app.title = "Digital Human SaaS Studio"
app.include_router(saas_router)

__all__ = ["app"]
