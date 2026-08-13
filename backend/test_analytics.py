import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class SalesAnalyticsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _register_company(self, suffix: str) -> str:
        register_payload = {
            "companyName": f"Analytics Sales Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"analytics-sales-{suffix}@example.com",
            "companyAddress": "1 Analytics Way",
            "companyPhone": "555-3100",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-analytics-sales-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _create_category(self, token: str, suffix: str) -> int:
        category_response = self.client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Analytics Sales Category {suffix}", "description": "Analytics", "status": "active"},
        )
        self.assertEqual(category_response.status_code, 200)
        return category_response.json()["id"]

    def _create_product(self, token: str, suffix: str, stock: int, unit_price: float) -> int:
        category_id = self._create_category(token, suffix)
        product_response = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": f"Analytics Sales Product {suffix}",
                "sku": f"ASL-{suffix}",
                "categoryId": category_id,
                "brand": "Northwind",
                "description": "Analytics product",
                "unitPrice": unit_price,
                "costPrice": unit_price * 0.8,
                "initialStockQuantity": stock,
                "unitOfMeasure": "pcs",
                "status": "active",
            },
        )
        self.assertEqual(product_response.status_code, 200)
        return product_response.json()["id"]

    def _create_sale(self, token: str, product_id: int, quantity: int, unit_price: float, customer_name: str, sale_date_time: str, payment_method: str = "Cash", sales_channel: str = "In-Store", discount: float = 0, tax: float = 0):
        response = self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_id,
                "quantity": quantity,
                "unitPrice": unit_price,
                "customerName": customer_name,
                "salesChannel": sales_channel,
                "paymentMethod": payment_method,
                "discountAmount": discount,
                "taxAmount": tax,
                "saleDateTime": sale_date_time,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_summary_returns_kpis(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=50.0)
        self._create_sale(token, product_id, 2, 50.0, "Jane Doe", "2026-07-22T10:00:00Z", discount=5.0, tax=7.5)

        response = self.client.get("/api/analytics/sales/summary", headers=self._headers(token))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 102.5)
        self.assertEqual(body["totalOrders"], 1)
        self.assertEqual(body["totalProductsSold"], 2)
        self.assertEqual(body["averageOrderValue"], 102.5)
        self.assertEqual(body["totalDiscount"], 5.0)
        self.assertEqual(body["totalTax"], 7.5)

    def test_trend_returns_buckets(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=40.0)
        self._create_sale(token, product_id, 1, 40.0, "Jane Doe", "2026-07-22T10:00:00Z")

        response = self.client.get("/analytics/sales/trend", headers=self._headers(token))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for bucket in ("daily", "weekly", "monthly"):
            self.assertIn(bucket, body["revenueTrend"])
            self.assertIn(bucket, body["salesTrend"])
            self.assertIn(bucket, body["orderTrend"])
        self.assertEqual(body["revenueTrend"]["daily"], [{"label": "2026-07-22", "value": 40.0}])
        self.assertEqual(body["salesTrend"]["daily"], [{"label": "2026-07-22", "value": 1}])
        self.assertEqual(body["orderTrend"]["daily"], [{"label": "2026-07-22", "value": 1}])

    def test_products_returns_top_sellers(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_a = self._create_product(token, f"{suffix}-a", stock=10, unit_price=40.0)
        product_b = self._create_product(token, f"{suffix}-b", stock=10, unit_price=100.0)
        self._create_sale(token, product_a, 4, 40.0, "Alpha Customer", "2026-07-22T10:00:00Z")
        self._create_sale(token, product_b, 1, 100.0, "Beta Customer", "2026-07-22T11:00:00Z")

        response = self.client.get("/api/analytics/sales/products", headers=self._headers(token))
        self.assertEqual(response.status_code, 200)
        products = response.json()
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["name"], f"Analytics Sales Product {suffix}-a")
        self.assertEqual(products[0]["quantity"], 4)
        self.assertEqual(products[0]["revenue"], 160.0)
        self.assertEqual(products[1]["name"], f"Analytics Sales Product {suffix}-b")
        self.assertEqual(products[1]["revenue"], 100.0)

    def test_customers_returns_top_customers(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=50.0)
        self._create_sale(token, product_id, 2, 50.0, "Loyal Customer", "2026-07-22T10:00:00Z")
        self._create_sale(token, product_id, 1, 50.0, "Loyal Customer", "2026-07-22T11:00:00Z")

        response = self.client.get("/api/analytics/sales/customers", headers=self._headers(token))
        self.assertEqual(response.status_code, 200)
        customers = response.json()
        self.assertEqual(len(customers), 1)
        self.assertEqual(customers[0]["name"], "Loyal Customer")
        self.assertEqual(customers[0]["orders"], 2)
        self.assertEqual(customers[0]["totalSpend"], 150.0)
        self.assertEqual(customers[0]["averageOrderValue"], 75.0)

    def test_payment_methods_returns_breakdown(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=50.0)
        self._create_sale(token, product_id, 1, 50.0, "Jane Doe", "2026-07-22T10:00:00Z", payment_method="Card")
        self._create_sale(token, product_id, 2, 50.0, "John Roe", "2026-07-22T11:00:00Z", payment_method="Card")
        self._create_sale(token, product_id, 1, 40.0, "Sam Poe", "2026-07-22T12:00:00Z", payment_method="Cash")

        response = self.client.get("/api/analytics/sales/payment-methods", headers=self._headers(token))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 190.0)
        self.assertEqual(body["totalOrders"], 3)
        by_method = {entry["paymentMethod"]: entry for entry in body["paymentMethods"]}
        self.assertEqual(by_method["Card"]["revenue"], 150.0)
        self.assertEqual(by_method["Card"]["orders"], 2)
        self.assertEqual(by_method["Cash"]["revenue"], 40.0)
        self.assertEqual(by_method["Cash"]["orders"], 1)

    def test_filters_are_applied(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=50.0)
        self._create_sale(token, product_id, 1, 50.0, "Jane Doe", "2026-07-10T10:00:00Z", payment_method="Card")
        self._create_sale(token, product_id, 1, 50.0, "Jane Doe", "2026-07-22T10:00:00Z", payment_method="Cash")

        response = self.client.get(
            "/api/analytics/sales/summary",
            headers=self._headers(token),
            params={"dateFrom": "2026-07-20T00:00:00Z", "dateTo": "2026-07-23T23:59:59Z", "paymentMethod": "Cash"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 50.0)
        self.assertEqual(body["totalOrders"], 1)

    def test_requires_authentication(self):
        response = self.client.get("/api/analytics/sales/summary")
        self.assertEqual(response.status_code, 401)

    def test_company_scoped(self):
        suffix_a = uuid.uuid4().hex[:8]
        suffix_b = uuid.uuid4().hex[:8]
        token_a = self._register_company(suffix_a)
        token_b = self._register_company(suffix_b)

        product_a = self._create_product(token_a, f"{suffix_a}-alpha", stock=5, unit_price=40.0)
        product_b = self._create_product(token_b, f"{suffix_b}-beta", stock=5, unit_price=80.0)
        self._create_sale(token_a, product_a, 1, 40.0, "Alpha Customer", "2026-07-22T10:00:00Z")
        self._create_sale(token_b, product_b, 2, 80.0, "Beta Customer", "2026-07-22T10:00:00Z")

        response = self.client.get("/api/analytics/sales/summary", headers=self._headers(token_a))
        body = response.json()
        self.assertEqual(body["totalRevenue"], 40.0)
        self.assertEqual(body["totalOrders"], 1)

        products_response = self.client.get("/api/analytics/sales/products", headers=self._headers(token_a))
        products = products_response.json()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["name"], f"Analytics Sales Product {suffix_a}-alpha")

    def test_export_csv_respects_filters_and_date_range(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=50.0)
        self._create_sale(token, product_id, 1, 50.0, "Jane Doe", "2026-07-10T10:00:00Z", payment_method="Card")
        self._create_sale(token, product_id, 2, 50.0, "June Roe", "2026-07-22T10:00:00Z", payment_method="Cash")

        response = self.client.get(
            "/analytics/sales/export",
            headers=self._headers(token),
            params={"format": "csv", "dateFrom": "2026-07-20T00:00:00Z", "dateTo": "2026-07-23T23:59:59Z", "paymentMethod": "Cash"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        body = response.text
        self.assertIn("June Roe", body)
        self.assertNotIn("Jane Doe", body)
        self.assertIn("Total Revenue", body)
        self.assertIn("100.00", body)

    def test_export_csv_is_company_scoped(self):
        suffix_a = uuid.uuid4().hex[:8]
        suffix_b = uuid.uuid4().hex[:8]
        token_a = self._register_company(suffix_a)
        token_b = self._register_company(suffix_b)

        product_a = self._create_product(token_a, f"{suffix_a}-alpha", stock=5, unit_price=40.0)
        product_b = self._create_product(token_b, f"{suffix_b}-beta", stock=5, unit_price=80.0)
        self._create_sale(token_a, product_a, 1, 40.0, "Alpha Customer", "2026-07-22T10:00:00Z")
        self._create_sale(token_b, product_b, 2, 80.0, "Beta Customer", "2026-07-22T10:00:00Z")

        response = self.client.get("/analytics/sales/export", headers=self._headers(token_a), params={"format": "csv"})
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Alpha Customer", body)
        self.assertNotIn("Beta Customer", body)

    def test_export_pdf_is_valid(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=50.0)
        self._create_sale(token, product_id, 2, 50.0, "Loyal Customer", "2026-07-22T10:00:00Z")

        response = self.client.get("/analytics/sales/export", headers=self._headers(token), params={"format": "pdf"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/pdf", response.headers["content-type"])
        content = response.content
        self.assertIn(b"%PDF", content)
        self.assertTrue(content.startswith(b"%PDF-1.4"))
        self.assertTrue(content.endswith(b"%%EOF"))
        self.assertIn(b"Loyal Customer", content)
        self.assertIn(b"startxref", content)

    def test_export_requires_authentication(self):
        response = self.client.get("/analytics/sales/export", params={"format": "csv"})
        self.assertEqual(response.status_code, 401)

    def test_export_records_audit_event(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=5, unit_price=25.0)
        self._create_sale(token, product_id, 1, 25.0, "Audit Customer", "2026-07-22T10:00:00Z")

        self.client.get("/analytics/sales/export", headers=self._headers(token), params={"format": "csv"})
        audit_response = self.client.get("/audit-logs", headers=self._headers(token))
        self.assertEqual(audit_response.status_code, 200)
        actions = {entry["action"] for entry in audit_response.json()}
        self.assertTrue(any(action.startswith("Sales Analytics Exported") for action in actions))


if __name__ == "__main__":
    unittest.main()
