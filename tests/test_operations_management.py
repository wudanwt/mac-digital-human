from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.saas.database import SessionLocal
from app.saas.models import User
from app.saas_main import app


PASSWORD = "correct-horse-battery-staple"


def _register(client: TestClient, prefix: str) -> dict:
    email = f"{prefix}-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": prefix,
            "workspace_name": f"{prefix} workspace",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    data["_email"] = email
    return data


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _promote(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.is_superuser = True
        db.commit()


def test_operations_management_closes_manual_subscription_lifecycle() -> None:
    with TestClient(app) as client:
        admin = _register(client, "ops-admin")
        customer = _register(client, "ops-customer")
        _promote(admin["_email"])
        admin_headers = _headers(admin["access_token"])
        customer_headers = _headers(customer["access_token"])
        tenant_id = customer["workspace"]["id"]

        forbidden = client.get("/api/saas/admin/ops/overview", headers=customer_headers)
        assert forbidden.status_code == 403

        plan_code = f"ops-{uuid4().hex[:10]}"
        created_plan = client.post(
            "/api/saas/admin/ops/plans",
            headers=admin_headers,
            json={
                "code": plan_code,
                "name": "运营测试套餐",
                "monthly_minutes": 120,
                "storage_gb": 20,
                "max_avatars": 3,
                "max_members": 5,
                "priority": 15,
                "price_cny": 299,
                "is_active": True,
            },
        )
        assert created_plan.status_code == 201, created_plan.text

        customers = client.get("/api/saas/admin/ops/customers", headers=admin_headers)
        assert customers.status_code == 200, customers.text
        row = next(item for item in customers.json() if item["id"] == tenant_id)
        assert row["plan_code"] == "free"

        activation = client.post(
            f"/api/saas/admin/ops/customers/{tenant_id}/activate",
            headers=admin_headers,
            json={
                "plan_code": plan_code,
                "months": 3,
                "amount_cny": 800,
                "activation_mode": "replace",
                "note": "合同 OPS-001",
            },
        )
        assert activation.status_code == 201, activation.text
        assert activation.json()["status"] == "paid"
        assert activation.json()["remaining_minutes"] == 360.0

        detail = client.get(
            f"/api/saas/admin/ops/customers/{tenant_id}",
            headers=admin_headers,
        )
        assert detail.status_code == 200, detail.text
        payload = detail.json()
        assert payload["subscription"]["plan_code"] == plan_code
        assert payload["subscription"]["remaining_minutes"] == 360.0
        assert payload["periods"][0]["granted_minutes"] == 360.0
        assert payload["periods"][0]["amount_cny"] == 800
        assert payload["periods"][0]["note"] == "合同 OPS-001"
        assert payload["orders"][0]["status"] == "paid"

        renewed = client.post(
            f"/api/saas/admin/ops/customers/{tenant_id}/activate",
            headers=admin_headers,
            json={
                "plan_code": plan_code,
                "months": 2,
                "activation_mode": "renew",
                "note": "续费两个月",
            },
        )
        assert renewed.status_code == 201, renewed.text
        assert renewed.json()["remaining_minutes"] == 600.0

        credit = client.post(
            f"/api/saas/admin/ops/customers/{tenant_id}/credits",
            headers=admin_headers,
            json={"minutes": 15, "reason": "售后补偿"},
        )
        assert credit.status_code == 200, credit.text
        assert credit.json()["remaining_minutes"] == 615.0

        debit = client.post(
            f"/api/saas/admin/ops/customers/{tenant_id}/credits",
            headers=admin_headers,
            json={"minutes": -5, "reason": "冲正"},
        )
        assert debit.status_code == 200, debit.text
        assert debit.json()["remaining_minutes"] == 610.0

        detail = client.get(
            f"/api/saas/admin/ops/customers/{tenant_id}",
            headers=admin_headers,
        ).json()
        assert len(detail["periods"]) >= 2
        assert detail["periods"][0]["activation_mode"] == "renew"
        assert any(item["kind"] == "credit_grant_seconds" for item in detail["usage_ledger"])

        overview = client.get("/api/saas/admin/ops/overview", headers=admin_headers)
        assert overview.status_code == 200, overview.text
        assert overview.json()["paid_customers"] >= 1
        assert overview.json()["paid_revenue_cny"] >= 800

        patched = client.patch(
            f"/api/saas/admin/ops/plans/{plan_code}",
            headers=admin_headers,
            json={"price_cny": 329, "is_active": False},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["price_cny"] == 329
        assert patched.json()["is_active"] is False


def test_operations_ui_is_mounted() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/operations-ui.js")
        assert page.status_code == 200
        assert "/operations-ui.js" in page.text
        assert script.status_code == 200
        assert "SaaS 运营管理中心" in script.text
        assert "订阅周期历史" in script.text
