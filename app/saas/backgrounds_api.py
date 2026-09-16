from __future__ import annotations

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .background_themes import list_themes, render_preview_bytes
from .security import Principal, get_principal
from .settings import saas_settings


router = APIRouter(prefix="/course-tools/backgrounds", tags=["course-tools"])


@router.get("")
def backgrounds(
    principal: Annotated[Principal, Depends(get_principal)],
) -> list[dict[str, str]]:
    del principal
    return [
        {
            **item,
            "preview_url": f"{saas_settings.api_prefix}/course-tools/backgrounds/{item['id']}/preview",
        }
        for item in list_themes()
    ]


@router.get("/{theme_id}/preview")
def background_preview(
    theme_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
) -> Response:
    del principal
    try:
        payload = render_preview_bytes(theme_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Background theme not found") from exc
    return Response(payload, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
