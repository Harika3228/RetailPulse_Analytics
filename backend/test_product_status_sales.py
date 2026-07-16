import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class ProductStatusSalesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _register_company_admin(self):
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "companyName": f"Sales Status Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"sales-status-{suffix}@example.com",
            "companyAddress": "1 Sales Street",
            "companyPhone": "555-2000",
            "ownerName": f"Sales Owner {suffix}",
            "ownerEmail": f"sales-owner-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _create_category(self, token: str, suffix: str) -> int:
        response = self.client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Sales Cat {suffix}", "description": "For sales tests", "status": "active"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def _create_product(self, token: str, category_id: int, sku: str, status: str = "active") -> int:
        response = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": f"Product {sku}",
                "sku": sku,
                "categoryId": category_id,
                "brand": "RetailPulse",
                "description": "Product status test",
                "unitPrice": 12.5,
                "costPrice": 8.0,
                "initialStockQuantity": 30,
                "unitOfMeasure": "pcs",
                "status": status,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def test_inactive_products_not_selectable_and_blocked_for_new_sales(self):
        suffix = uuid.uuid4().hex[:6]
        token = self._register_company_admin()
        category_id = self._create_category(token, suffix)

        active_product_id = self._create_product(token, category_id, f"ACT-{suffix}", status="active")
        inactive_product_id = self._create_product(token, category_id, f"INA-{suffix}", status="inactive")

        selectable = self.client.get(
            "/sales/products/selectable",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(selectable.status_code, 200)
        ids = {item["id"] for item in selectable.json()}
        self.assertIn(active_product_id, ids)
        self.assertNotIn(inactive_product_id, ids)

        blocked_sale = self.client.post(
            "/sales/transactions",
            headers={"Authorization": f"Bearer {token}"},
            json={"lines": [{"productId": inactive_product_id, "quantity": 2}]},
        )
        self.assertEqual(blocked_sale.status_code, 400)
        self.assertIn("Inactive product", blocked_sale.json()["detail"])

    def test_inactive_products_remain_in_historical_reports(self):
        suffix = uuid.uuid4().hex[:6]
        token = self._register_company_admin()
        category_id = self._create_category(token, suffix)
        product_id = self._create_product(token, category_id, f"HIS-{suffix}", status="active")

        created = self.client.post(
            "/sales/transactions",
            headers={"Authorization": f"Bearer {token}"},
            json={"lines": [{"productId": product_id, "quantity": 3}]},
        )
        self.assertEqual(created.status_code, 200)
        tx_id = created.json()["transactionId"]

        deactivated = self.client.patch(
            f"/products/{product_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "inactive"},
        )
        self.assertEqual(deactivated.status_code, 200)

        history = self.client.get(
            "/sales/reports/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(history.status_code, 200)
        report = history.json()

        matching = [tx for tx in report if tx["transactionId"] == tx_id]
        self.assertTrue(matching)
        self.assertGreater(len(matching[0]["lines"]), 0)
        self.assertEqual(matching[0]["lines"][0]["productId"], product_id)


if __name__ == "__main__":
    unittest.main()
