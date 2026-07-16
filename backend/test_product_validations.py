import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class ProductValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _register_admin(self) -> str:
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "companyName": f"Validation Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"validation-company-{suffix}@example.com",
            "companyAddress": "100 Validation St",
            "companyPhone": "555-1111",
            "ownerName": f"Validation Owner {suffix}",
            "ownerEmail": f"validation-owner-{suffix}@example.com",
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
            json={"name": f"Category {suffix}", "description": "Validation category", "status": "active"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def _product_payload(self, category_id: int, suffix: str) -> dict:
        return {
            "name": f"Product {suffix}",
            "sku": f"VAL-{suffix}",
            "categoryId": category_id,
            "brand": "RetailPulse",
            "description": "Validation product",
            "unitPrice": 20.0,
            "costPrice": 10.0,
            "initialStockQuantity": 10,
            "unitOfMeasure": "pcs",
            "status": "active",
        }

    def test_product_name_is_mandatory(self):
        token = self._register_admin()
        category_id = self._create_category(token, uuid.uuid4().hex[:6])
        payload = self._product_payload(category_id, uuid.uuid4().hex[:6])
        payload["name"] = "   "

        response = self.client.post("/products", headers={"Authorization": f"Bearer {token}"}, json=payload)
        self.assertEqual(response.status_code, 422)

    def test_unit_price_must_be_greater_than_zero(self):
        token = self._register_admin()
        category_id = self._create_category(token, uuid.uuid4().hex[:6])
        payload = self._product_payload(category_id, uuid.uuid4().hex[:6])
        payload["unitPrice"] = 0

        response = self.client.post("/products", headers={"Authorization": f"Bearer {token}"}, json=payload)
        self.assertEqual(response.status_code, 422)

    def test_cost_price_cannot_exceed_unit_price(self):
        token = self._register_admin()
        category_id = self._create_category(token, uuid.uuid4().hex[:6])
        payload = self._product_payload(category_id, uuid.uuid4().hex[:6])
        payload["unitPrice"] = 15
        payload["costPrice"] = 16

        response = self.client.post("/products", headers={"Authorization": f"Bearer {token}"}, json=payload)
        self.assertEqual(response.status_code, 422)

    def test_stock_quantity_cannot_be_negative(self):
        token = self._register_admin()
        category_id = self._create_category(token, uuid.uuid4().hex[:6])
        payload = self._product_payload(category_id, uuid.uuid4().hex[:6])
        payload["initialStockQuantity"] = -1

        response = self.client.post("/products", headers={"Authorization": f"Bearer {token}"}, json=payload)
        self.assertEqual(response.status_code, 422)

    def test_duplicate_product_name_not_allowed_within_same_category(self):
        token = self._register_admin()
        category_id = self._create_category(token, uuid.uuid4().hex[:6])

        first = self._product_payload(category_id, uuid.uuid4().hex[:6])
        first["name"] = "Water Bottle"
        first["sku"] = f"WB-{uuid.uuid4().hex[:6]}"
        first_response = self.client.post("/products", headers={"Authorization": f"Bearer {token}"}, json=first)
        self.assertEqual(first_response.status_code, 200)

        second = self._product_payload(category_id, uuid.uuid4().hex[:6])
        second["name"] = "water bottle"
        second["sku"] = f"WB-{uuid.uuid4().hex[:6]}"
        second_response = self.client.post("/products", headers={"Authorization": f"Bearer {token}"}, json=second)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json()["detail"], "Product name already exists in this category")


if __name__ == "__main__":
    unittest.main()
