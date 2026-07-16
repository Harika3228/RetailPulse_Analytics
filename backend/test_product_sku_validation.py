import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class ProductSkuValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _register_admin(self) -> tuple[str, int]:
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "companyName": f"SKU Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"sku-company-{suffix}@example.com",
            "companyAddress": "100 SKU Street",
            "companyPhone": "555-1111",
            "ownerName": f"SKU Owner {suffix}",
            "ownerEmail": f"sku-owner-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        return body["access_token"], body["user"]["companyId"]

    def _create_category(self, token: str, name: str) -> int:
        response = self.client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name, "description": "SKU test category", "status": "active"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def _product_payload(self, sku: str, category_id: int, suffix: str) -> dict:
        return {
            "name": f"Product {suffix}",
            "sku": sku,
            "categoryId": category_id,
            "brand": "RetailPulse",
            "description": "SKU validation product",
            "unitPrice": 25.0,
            "costPrice": 15.0,
            "initialStockQuantity": 50,
            "unitOfMeasure": "pcs",
            "status": "active",
        }

    def test_duplicate_sku_not_allowed_within_same_company(self):
        token, _company_id = self._register_admin()
        category_id = self._create_category(token, f"Category-{uuid.uuid4().hex[:6]}")

        first = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token}"},
            json=self._product_payload("RTL-10001", category_id, "A"),
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token}"},
            json=self._product_payload("rtl-10001", category_id, "B"),
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json()["detail"], "SKU already exists")

    def test_same_sku_allowed_for_different_companies(self):
        token_a, _company_a = self._register_admin()
        token_b, _company_b = self._register_admin()

        category_a = self._create_category(token_a, f"Category-A-{uuid.uuid4().hex[:6]}")
        category_b = self._create_category(token_b, f"Category-B-{uuid.uuid4().hex[:6]}")

        first = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token_a}"},
            json=self._product_payload("RTL-10002", category_a, "A"),
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token_b}"},
            json=self._product_payload("RTL-10002", category_b, "B"),
        )
        self.assertEqual(second.status_code, 200)


if __name__ == "__main__":
    unittest.main()
