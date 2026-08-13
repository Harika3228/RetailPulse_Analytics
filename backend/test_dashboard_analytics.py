import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class AnalyticsDashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _register_company(self, suffix: str) -> str:
        register_payload = {
            "companyName": f"Analytics Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"analytics-{suffix}@example.com",
            "companyAddress": "1 Analytics Way",
            "companyPhone": "555-3000",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-analytics-{suffix}@example.com",
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
            json={"name": f"Analytics Category {suffix}", "description": "Analytics", "status": "active"},
        )
        self.assertEqual(category_response.status_code, 200)
        return category_response.json()["id"]

    def _create_product(self, token: str, suffix: str, stock: int, unit_price: float, brand: str = "Northwind") -> int:
        category_id = self._create_category(token, suffix)
        product_response = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": f"Analytics Product {suffix}",
                "sku": f"ANL-{suffix}",
                "categoryId": category_id,
                "brand": brand,
                "description": "Analytics product",
                "unitPrice": unit_price,
                "costPrice": unit_price * 0.8,
                "initialStockQuantity": stock,
                "unitOfMeasure": "pcs",
                "status": "active",
            },
        )
        self.assertEqual(product_response.status_code, 200)
        self._last_created_product = product_response.json()["id"]
        return self._last_created_product

    def test_analytics_dashboard_returns_kpis(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=5, unit_price=40.0)
        self._create_product(token, f"{suffix}-b", stock=0, unit_price=80.0)

        sale_response = self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_id,
                "quantity": 2,
                "unitPrice": 40.0,
                "customerName": "Jane Doe",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )
        self.assertEqual(sale_response.status_code, 200)

        response = self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 80.0)
        self.assertEqual(body["totalOrders"], 1)
        self.assertEqual(body["totalProductsSold"], 2)
        self.assertEqual(body["averageOrderValue"], 80.0)
        self.assertEqual(body["totalInventoryValue"], 120.0)
        self.assertEqual(body["lowStockProducts"], 1)
        self.assertEqual(body["outOfStockProducts"], 1)
        self.assertEqual(body["totalCategories"], 2)
        self.assertIn("revenueTrend", body)
        self.assertIn("salesTrend", body)
        self.assertIn("orderTrend", body)
        self.assertIn("topSellingProducts", body)
        self.assertIn("topPerformingCategories", body)
        self.assertIn("salesByPaymentMethod", body)
        self.assertIn("salesBySalesChannel", body)
        self.assertIn("salesByPaymentStatus", body)
        self.assertIn("ordersBySalesChannel", body)
        self.assertIn("ordersByPaymentMethod", body)
        self.assertIn("inventoryDistributionByCategory", body)
        self.assertIn("stockStatusSummary", body)
        self.assertIn("topLowStockProducts", body)
        self.assertIn("outOfStockProducts", body)
        self.assertIn("inventoryValueByCategory", body)
        self.assertIn("topCustomersByRevenue", body)
        self.assertIn("recentCustomers", body)
        self.assertIn("customerGrowthTrend", body)
        self.assertIn("customerRevenueContribution", body)

    def test_analytics_dashboard_applies_filters(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        matching_product_id = self._create_product(token, f"{suffix}-match", stock=6, unit_price=50.0, brand="Northwind")
        self._create_product(token, f"{suffix}-other", stock=4, unit_price=30.0, brand="Acme")

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": matching_product_id,
                "quantity": 1,
                "unitPrice": 50.0,
                "customerName": "Jane Doe",
                "salesChannel": "Online",
                "paymentMethod": "Card",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )

        response = self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "dateFrom": "2026-07-22T00:00:00Z",
                "dateTo": "2026-07-22T23:59:59Z",
                "product": f"Analytics Product {suffix}-match",
                "category": f"Analytics Category {suffix}-match",
                "brand": "Northwind",
                "salesChannel": "Online",
                "paymentMethod": "Card",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 50.0)
        self.assertEqual(body["totalOrders"], 1)
        self.assertEqual(body["totalProductsSold"], 1)
        self.assertEqual(body["averageOrderValue"], 50.0)

    def test_analytics_dashboard_returns_discount_and_tax(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=5, unit_price=100.0)

        sale_response = self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_id,
                "quantity": 2,
                "unitPrice": 100.0,
                "customerName": "Jane Doe",
                "discountAmount": 20.0,
                "taxAmount": 15.0,
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )
        self.assertEqual(sale_response.status_code, 200)

        response = self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 195.0)
        self.assertEqual(body["totalOrders"], 1)
        self.assertEqual(body["totalProductsSold"], 2)
        self.assertEqual(body["averageOrderValue"], 195.0)
        self.assertEqual(body["totalDiscount"], 20.0)
        self.assertEqual(body["totalTax"], 15.0)

    def test_top_products_and_customers_are_returned(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_a = self._create_product(token, f"{suffix}-alpha", stock=10, unit_price=40.0)
        product_b = self._create_product(token, f"{suffix}-beta", stock=10, unit_price=100.0)

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_a,
                "quantity": 4,
                "unitPrice": 40.0,
                "customerName": "Alpha Customer",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )
        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_b,
                "quantity": 1,
                "unitPrice": 100.0,
                "customerName": "Beta Customer",
                "saleDateTime": "2026-07-22T11:00:00Z",
            },
        )

        products_response = self.client.get(
            "/dashboard/analytics/top-products",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(products_response.status_code, 200)
        products = products_response.json()
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["name"], f"Analytics Product {suffix}-alpha")
        self.assertEqual(products[0]["quantity"], 4)
        self.assertEqual(products[0]["revenue"], 160.0)
        self.assertEqual(products[1]["name"], f"Analytics Product {suffix}-beta")
        self.assertEqual(products[1]["quantity"], 1)
        self.assertEqual(products[1]["revenue"], 100.0)

        customers_response = self.client.get(
            "/dashboard/analytics/top-customers",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(customers_response.status_code, 200)
        customers = customers_response.json()
        self.assertEqual(len(customers), 2)
        self.assertEqual(customers[0]["name"], "Alpha Customer")
        self.assertEqual(customers[0]["orders"], 1)
        self.assertEqual(customers[0]["totalSpend"], 160.0)
        self.assertEqual(customers[0]["averageOrderValue"], 160.0)
        self.assertEqual(customers[1]["name"], "Beta Customer")
        self.assertEqual(customers[1]["averageOrderValue"], 100.0)

    def test_top_products_respect_filters(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        matching = self._create_product(token, f"{suffix}-match", stock=5, unit_price=50.0)
        self._create_product(token, f"{suffix}-other", stock=5, unit_price=30.0)

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": matching,
                "quantity": 2,
                "unitPrice": 50.0,
                "customerName": "Jane Doe",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )

        response = self.client.get(
            "/dashboard/analytics/top-products",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "dateFrom": "2026-07-22T00:00:00Z",
                "dateTo": "2026-07-22T23:59:59Z",
                "product": f"Analytics Product {suffix}-match",
            },
        )
        self.assertEqual(response.status_code, 200)
        products = response.json()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["quantity"], 2)
        self.assertEqual(products[0]["revenue"], 100.0)

    def test_analytics_dashboard_applies_customer_filter(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_a = self._create_product(token, f"{suffix}-a", stock=10, unit_price=50.0)
        product_b = self._create_product(token, f"{suffix}-b", stock=10, unit_price=30.0)

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_a,
                "quantity": 2,
                "unitPrice": 50.0,
                "customerName": "Loyal Customer",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )
        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_b,
                "quantity": 3,
                "unitPrice": 30.0,
                "customerName": "Other Customer",
                "saleDateTime": "2026-07-22T11:00:00Z",
            },
        )

        response = self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
            params={"customer": "Loyal Customer"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 100.0)
        self.assertEqual(body["totalOrders"], 1)
        self.assertEqual(body["totalProductsSold"], 2)
        self.assertEqual(body["averageOrderValue"], 100.0)

    def test_top_products_and_customers_respect_customer_filter(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_a = self._create_product(token, f"{suffix}-a", stock=10, unit_price=50.0)
        product_b = self._create_product(token, f"{suffix}-b", stock=10, unit_price=30.0)

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_a,
                "quantity": 2,
                "unitPrice": 50.0,
                "customerName": "Loyal Customer",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )
        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_b,
                "quantity": 3,
                "unitPrice": 30.0,
                "customerName": "Other Customer",
                "saleDateTime": "2026-07-22T11:00:00Z",
            },
        )

        products_response = self.client.get(
            "/dashboard/analytics/top-products",
            headers={"Authorization": f"Bearer {token}"},
            params={"customer": "Loyal Customer"},
        )
        self.assertEqual(products_response.status_code, 200)
        products = products_response.json()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["name"], f"Analytics Product {suffix}-a")
        self.assertEqual(products[0]["revenue"], 100.0)

        customers_response = self.client.get(
            "/dashboard/analytics/top-customers",
            headers={"Authorization": f"Bearer {token}"},
            params={"customer": "Loyal Customer"},
        )
        self.assertEqual(customers_response.status_code, 200)
        customers = customers_response.json()
        self.assertEqual(len(customers), 1)
        self.assertEqual(customers[0]["name"], "Loyal Customer")
        self.assertEqual(customers[0]["totalSpend"], 100.0)

    def test_analytics_dashboard_date_range_filters_sales(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        product_id = self._create_product(token, suffix, stock=10, unit_price=40.0)

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_id,
                "quantity": 1,
                "unitPrice": 40.0,
                "customerName": "Jane Doe",
                "saleDateTime": "2026-07-10T10:00:00Z",
            },
        )
        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": product_id,
                "quantity": 1,
                "unitPrice": 40.0,
                "customerName": "Jane Doe",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )

        response = self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "dateFrom": "2026-07-20T00:00:00Z",
                "dateTo": "2026-07-23T23:59:59Z",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 40.0)
        self.assertEqual(body["totalOrders"], 1)
        self.assertEqual(body["totalProductsSold"], 1)

    def test_product_filter_scopes_revenue_and_orders(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        matching = self._create_product(token, f"{suffix}-match", stock=10, unit_price=50.0)
        self._create_product(token, f"{suffix}-other", stock=10, unit_price=30.0)

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": matching,
                "quantity": 2,
                "unitPrice": 50.0,
                "customerName": "Jane Doe",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )
        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": self._last_created_product,
                "quantity": 3,
                "unitPrice": 30.0,
                "customerName": "Jane Doe",
                "saleDateTime": "2026-07-22T11:00:00Z",
            },
        )

        response = self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
            params={"product": f"Analytics Product {suffix}-match"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 100.0)
        self.assertEqual(body["totalOrders"], 1)
        self.assertEqual(body["totalProductsSold"], 2)
        self.assertEqual(body["averageOrderValue"], 100.0)

    def test_category_filter_returns_no_rows_when_category_missing(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        self._create_product(token, suffix, stock=5, unit_price=40.0)
        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "productId": self._last_created_product,
                "quantity": 1,
                "unitPrice": 40.0,
                "customerName": "Jane Doe",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )

        response = self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
            params={"category": "Nonexistent Category"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalRevenue"], 0.0)
        self.assertEqual(body["totalOrders"], 0)
        self.assertEqual(body["totalProductsSold"], 0)

    def test_dashboard_export_is_company_scoped(self):
        suffix_a = uuid.uuid4().hex[:8]
        suffix_b = uuid.uuid4().hex[:8]
        token_a = self._register_company(suffix_a)
        token_b = self._register_company(suffix_b)

        product_a = self._create_product(token_a, f"{suffix_a}-alpha", stock=5, unit_price=40.0)
        product_b = self._create_product(token_b, f"{suffix_b}-beta", stock=4, unit_price=80.0)

        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "productId": product_a,
                "quantity": 1,
                "unitPrice": 40.0,
                "customerName": "Alpha Customer",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )
        self.client.post(
            "/sales",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "productId": product_b,
                "quantity": 2,
                "unitPrice": 80.0,
                "customerName": "Beta Customer",
                "saleDateTime": "2026-07-22T10:00:00Z",
            },
        )

        response = self.client.get(
            "/dashboard/export",
            headers={"Authorization": f"Bearer {token_a}"},
            params={"format": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].startswith("text/csv"), True)
        body = response.text
        self.assertIn("Alpha Customer", body)
        self.assertNotIn("Beta Customer", body)

        pdf_response = self.client.get(
            "/dashboard/export",
            headers={"Authorization": f"Bearer {token_a}"},
            params={"format": "pdf"},
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("application/pdf", pdf_response.headers["content-type"])
        self.assertIn(b"%PDF", pdf_response.content)

    def test_dashboard_audit_events_are_recorded(self):
        suffix = uuid.uuid4().hex[:8]
        token = self._register_company(suffix)
        self._create_product(token, f"{suffix}-audit", stock=3, unit_price=25.0)

        self.client.get(
            "/dashboard/analytics",
            headers={"Authorization": f"Bearer {token}"},
            params={"product": f"Analytics Product {suffix}-audit"},
        )
        self.client.get(
            "/dashboard/export",
            headers={"Authorization": f"Bearer {token}"},
            params={"format": "csv"},
        )

        audit_response = self.client.get(
            "/audit-logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(audit_response.status_code, 200)
        audit_events = audit_response.json()
        actions = {entry["action"] for entry in audit_events}
        self.assertIn("Dashboard Viewed", actions)
        self.assertIn("Dashboard Filters Applied", actions)
        self.assertTrue(any(action.startswith("Report Exported") for action in actions))


if __name__ == "__main__":
    unittest.main()
