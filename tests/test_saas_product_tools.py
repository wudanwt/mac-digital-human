from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from pptx import Presentation

from app.saas_main import app


def _register(client: TestClient, prefix: str) -> tuple[str, str, str]:
    email = f"{prefix}-{uuid4().hex[:8]}@example.com"
    password = "correct-horse-battery-staple"
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": prefix,
            "workspace_name": f"{prefix} workspace",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"], email, password


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _pptx_bytes() -> bytes:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "第一章：市场变化"
    slide.placeholders[1].text = "客户需求从项目交付转向持续经营"
    slide.notes_slide.notes_text_frame.text = "这一页重点解释客户为什么需要持续经营能力。"
    buffer = BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_account_profile_and_password_change() -> None:
    with TestClient(app) as client:
        token, email, password = _register(client, "account-tools")
        headers = _headers(token)

        account = client.get("/api/saas/account", headers=headers)
        assert account.status_code == 200
        assert account.json()["email"] == email

        updated = client.patch(
            "/api/saas/account",
            headers=headers,
            json={"display_name": "新的显示名称"},
        )
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "新的显示名称"

        new_password = "new-correct-horse-battery-staple"
        changed = client.post(
            "/api/saas/account/change-password",
            headers=headers,
            json={"current_password": password, "new_password": new_password},
        )
        assert changed.status_code == 204, changed.text

        old_login = client.post("/api/saas/auth/login", json={"email": email, "password": password})
        assert old_login.status_code == 401
        new_login = client.post("/api/saas/auth/login", json={"email": email, "password": new_password})
        assert new_login.status_code == 200


def test_ppt_outline_parser_for_course_studio() -> None:
    with TestClient(app) as client:
        token, _, _ = _register(client, "course-tools")
        headers = _headers(token)
        upload = client.post(
            "/api/saas/assets",
            headers=headers,
            data={"kind": "ppt"},
            files={
                "file": (
                    "training.pptx",
                    BytesIO(_pptx_bytes()),
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            },
        )
        assert upload.status_code == 201, upload.text
        asset_id = upload.json()["id"]

        outline = client.get(f"/api/saas/course-tools/ppt/{asset_id}/outline", headers=headers)
        assert outline.status_code == 200, outline.text
        data = outline.json()
        assert data["total_slides"] == 1
        assert data["slides"][0]["title"] == "第一章：市场变化"
        assert "持续经营" in data["slides"][0]["narration"]


def test_theme_and_product_ui_assets_are_served() -> None:
    with TestClient(app) as client:
        css = client.get("/saas-theme.css")
        js = client.get("/product-ui.js")
        page = client.get("/")
        assert css.status_code == 200
        assert "tech-hero" in css.text
        assert js.status_code == 200
        assert "COURSE STUDIO" in js.text
        assert page.status_code == 200
        assert "/saas-theme.css" in page.text
        assert "/product-ui.js" in page.text
