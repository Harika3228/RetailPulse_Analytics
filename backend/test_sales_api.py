import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class SalesApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _login(self, email: str, password: str = "password123") -> str:
        response = self.client.post("/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _create_category(self, token: str, name: str) -> int:
        response = self.client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name, "description": "Sales API test category", "status": "active"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def _create_product(self, token: str, category_id: int, sku: str, stock: int = 20, unit_price: float = 15.0) -> int:
        response = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": f"Product {sku}",
                "sku": sku,
                "categoryId": category_id,
                "brand": "RetailPulse",
                "description": "Sales API test product",
                "unitPrice": unit_price,
                "costPrice": unit_price * 0.6,
                "initialStockQuantity": stock,
                "unitOfMeasure": "pcs",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def _create_customer(self, token: str, suffix: str) -> int:
        response = self.client.post(
            "/customers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": f"API Customer {suffix}",
                "email": f"api-customer-{suffix}@example.com",
                "phone": f"55500012{suffix}",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def test_api_sales_full_crud_totals_and_stock_movements(self):
        admin_token = self._login("admin@retailpulse.com")
        analyst_token = self._login("analyst@retailpulse.com")

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f"API Sales {suffix}")
        product_id = self._create_product(admin_token, category_id, f"API-{suffix}", stock=20, unit_price=15.0)
        customer_id = self._create_customer(admin_token, suffix)

        created = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={
                "customerId": customer_id,
                "lines": [{"productId": product_id, "quantity": 2, "unitPrice": 15.0}],
                "saleDateTime": "2026-07-20T10:00:00",
                "salesChannel": "In-Store",
                "paymentMethod": "Cash",
                "discountAmount": 5,
                "taxAmount": 2,
            },
        )
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertRegex(body["invoiceNumber"], r"^INV-\d{4}-\d{6}$")
        self.assertEqual(body["customerId"], customer_id)
        self.assertEqual(body["customerName"], f"API Customer {suffix}")
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["subtotalAmount"], 30.0)
        self.assertEqual(body["discountAmount"], 5.0)
        self.assertEqual(body["taxAmount"], 2.0)
        self.assertEqual(body["totalAmount"], 27.0)
        self.assertEqual(body["lines"][0]["productId"], product_id)
        self.assertEqual(body["lines"][0]["quantity"], 2)
        self.assertEqual(body["lines"][0]["lineTotal"], 27.0)
        transaction_id = body["transactionId"]

        product_after_create = self.client.get(
            f"/products/{product_id}", headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(product_after_create.json()["stockQuantity"], 18)

        movements = self.client.get(
            f"/api/sales/{transaction_id}/stock-movements",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        self.assertEqual(movements.status_code, 200)
        movement_list = movements.json()
        self.assertEqual(len(movement_list), 1)
        self.assertEqual(movement_list[0]["movementType"], "Sale")
        self.assertEqual(movement_list[0]["quantityChanged"], -2)
        self.assertEqual(movement_list[0]["previousQuantity"], 20)
        self.assertEqual(movement_list[0]["updatedQuantity"], 18)
        self.assertEqual(movement_list[0]["reference"], body["invoiceNumber"])
        self.assertEqual(movement_list[0]["productId"], product_id)

        details = self.client.get(
            f"/api/sales/{transaction_id}", headers={"Authorization": f"Bearer {analyst_token}"}
        )
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.json()["transactionId"], transaction_id)
        self.assertEqual(details.json()["status"], "completed")

        listing = self.client.get("/api/sales", headers={"Authorization": f"Bearer {analyst_token}"})
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(any(item["transactionId"] == transaction_id for item in listing.json()))

        updated = self.client.put(
            f"/api/sales/{transaction_id}",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={
                "customerId": customer_id,
                "lines": [{"productId": product_id, "quantity": 3, "unitPrice": 15.0}],
                "saleDateTime": "2026-07-20T11:00:00",
                "salesChannel": "Online",
                "paymentMethod": "Card",
                "discountAmount": 4,
                "taxAmount": 3,
            },
        )
        self.assertEqual(updated.status_code, 200)
        updated_body = updated.json()
        self.assertEqual(updated_body["lines"][0]["quantity"], 3)
        self.assertEqual(updated_body["totalAmount"], 44.0)

        product_after_update = self.client.get(
            f"/products/{product_id}", headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(product_after_update.json()["stockQuantity"], 17)

        updated_movements = self.client.get(
            f"/api/sales/{transaction_id}/stock-movements",
            headers={"Authorization": f"Bearer {analyst_token}"},
        ).json()
        types = [item["movementType"] for item in updated_movements]
        self.assertEqual(types, ["Sale", "Sale Return", "Sale"])
        self.assertEqual(updated_movements[1]["quantityChanged"], 2)
        self.assertEqual(updated_movements[2]["quantityChanged"], -3)

        deleted = self.client.delete(
            f"/api/sales/{transaction_id}", headers={"Authorization": f"Bearer {analyst_token}"}
        )
        self.assertEqual(deleted.status_code, 200)

        product_after_delete = self.client.get(
            f"/products/{product_id}", headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(product_after_delete.json()["stockQuantity"], 20)

        missing = self.client.get(
            f"/api/sales/{transaction_id}", headers={"Authorization": f"Bearer {analyst_token}"}
        )
        self.assertEqual(missing.status_code, 404)

    def test_customer_must_exist_and_belong_to_company(self):
        admin_token = self._login("admin@retailpulse.com")
        analyst_token = self._login("analyst@retailpulse.com")

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f"Missing Customer {suffix}")
        product_id = self._create_product(admin_token, category_id, f"MC-{suffix}")

        response = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={
                "customerId": 999999,
                "lines": [{"productId": product_id, "quantity": 1}],
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Customer not found: 999999")

    def test_product_must_exist(self):
        analyst_token = self._login("analyst@retailpulse.com")

        response = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={"lines": [{"productId": 999999, "quantity": 1}]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Product not found: 999999")

    def test_insufficient_stock_is_rejected(self):
        admin_token = self._login("admin@retailpulse.com")
        analyst_token = self._login("analyst@retailpulse.com")

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f"Low Stock {suffix}")
        product_id = self._create_product(admin_token, category_id, f"LS-{suffix}", stock=1)

        response = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={"lines": [{"productId": product_id, "quantity": 5}]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Quantity sold cannot exceed available stock", response.json()["detail"])

    def test_positive_pricing_is_enforced(self):
        admin_token = self._login("admin@retailpulse.com")
        analyst_token = self._login("analyst@retailpulse.com")

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f"Pricing {suffix}")
        product_id = self._create_product(admin_token, category_id, f"PR-{suffix}", stock=10)

        zero_price = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={"lines": [{"productId": product_id, "quantity": 1, "unitPrice": 0}]},
        )
        self.assertEqual(zero_price.status_code, 422)

        negative_price = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={"lines": [{"productId": product_id, "quantity": 1, "unitPrice": -5}]},
        )
        self.assertEqual(negative_price.status_code, 422)

    def test_mandatory_line_items_are_enforced(self):
        analyst_token = self._login("analyst@retailpulse.com")

        response = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "At least one line item is required")

    def test_invoice_numbers_are_unique(self):
        admin_token = self._login("admin@retailpulse.com")
        analyst_token = self._login("analyst@retailpulse.com")

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f"Unique Inv {suffix}")
        product_id = self._create_product(admin_token, category_id, f"UI-{suffix}", stock=20)

        first = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={"lines": [{"productId": product_id, "quantity": 1}], "customerName": "First Buyer"},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={"lines": [{"productId": product_id, "quantity": 1}], "customerName": "Second Buyer"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json()["invoiceNumber"], second.json()["invoiceNumber"])
        self.assertRegex(first.json()["invoiceNumber"], r"^INV-\d{4}-\d{6}$")
        self.assertRegex(second.json()["invoiceNumber"], r"^INV-\d{4}-\d{6}$")

    def test_customer_name_is_derived_from_customer_when_omitted(self):
        admin_token = self._login("admin@retailpulse.com")
        analyst_token = self._login("analyst@retailpulse.com")

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f"Derived Name {suffix}")
        product_id = self._create_product(admin_token, category_id, f"DN-{suffix}", stock=5)
        customer_id = self._create_customer(admin_token, suffix)

        created = self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={"customerId": customer_id, "lines": [{"productId": product_id, "quantity": 1}]},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["customerId"], customer_id)
        self.assertEqual(created.json()["customerName"], f"API Customer {suffix}")

    def test_sales_list_filters_by_product_and_customer(self):
        admin_token = self._login("admin@retailpulse.com")
        analyst_token = self._login("analyst@retailpulse.com")

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f"Filter {suffix}")
        product_a = self._create_product(admin_token, category_id, f"FA-{suffix}", stock=20)
        product_b = self._create_product(admin_token, category_id, f"FB-{suffix}", stock=20)

        self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={
                "customerName": f"Filter Buyer A {suffix}",
                "lines": [{"productId": product_a, "quantity": 1}],
                "salesChannel": "In-Store",
                "paymentMethod": "Cash",
            },
        )
        self.client.post(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            json={
                "customerName": f"Filter Buyer B {suffix}",
                "lines": [{"productId": product_b, "quantity": 2}],
                "salesChannel": "Online",
                "paymentMethod": "Card",
            },
        )

        by_product = self.client.get(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            params={"product": f"Product FA-{suffix}"},
        )
        self.assertEqual(by_product.status_code, 200)
        self.assertEqual(len(by_product.json()), 1)
        self.assertEqual(by_product.json()[0]["customerName"], f"Filter Buyer A {suffix}")

        by_customer = self.client.get(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            params={"customer": f"Filter Buyer B {suffix}"},
        )
        self.assertEqual(by_customer.status_code, 200)
        self.assertEqual(len(by_customer.json()), 1)
        self.assertEqual(by_customer.json()[0]["lines"][0]["productName"], f"Product FB-{suffix}")

        combined = self.client.get(
            "/api/sales",
            headers={"Authorization": f"Bearer {analyst_token}"},
            params={"product": f"Product FA-{suffix}", "customer": f"Filter Buyer B {suffix}"},
        )
        self.assertEqual(combined.status_code, 200)
        self.assertEqual(len(combined.json()), 0)


if __name__ == "__main__":
    unittest.main()
