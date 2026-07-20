import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class CompanyIsolationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _register_company_admin(self, suffix: str) -> tuple[str, int]:
        register_payload = {
            "companyName": f"Isolation Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"company-{suffix}@example.com",
            "companyAddress": "1 Isolation Way",
            "companyPhone": "555-1000",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        return body["access_token"], body["user"]["companyId"]

    def test_user_cannot_access_other_company_data_via_token(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]

        response = self.client.get(
            "/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["companyName"], "RetailPulse North")

    def test_company_admin_cannot_access_other_company_categories_or_products(self):
        suffix_a = uuid.uuid4().hex[:8]
        suffix_b = uuid.uuid4().hex[:8]

        token_a, company_a = self._register_company_admin(suffix_a)
        token_b, _company_b = self._register_company_admin(suffix_b)

        # Create category and product in company A
        create_category = self.client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"name": f"Cat-{suffix_a}", "description": "A category", "status": "active"},
        )
        self.assertEqual(create_category.status_code, 200)
        category_id = create_category.json()["id"]

        create_product = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "name": f"Product-{suffix_a}",
                "sku": f"SKU-{suffix_a}",
                "categoryId": category_id,
                "brand": "RetailPulse",
                "description": "Isolation product",
                "unitPrice": 10.5,
                "costPrice": 7.25,
                "initialStockQuantity": 100,
                "unitOfMeasure": "pcs",
                "status": "active",
            },
        )
        self.assertEqual(create_product.status_code, 200)
        product_id = create_product.json()["id"]

        # Company B cannot fetch A's category by id
        get_foreign_category = self.client.get(
            f"/categories/{category_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(get_foreign_category.status_code, 404)

        # Company B cannot fetch A's product by id
        get_foreign_product = self.client.get(
            f"/products/{product_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(get_foreign_product.status_code, 404)

        # Company B list endpoints must not include company A records
        list_categories_b = self.client.get(
            "/categories",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(list_categories_b.status_code, 200)
        self.assertFalse(any(item["id"] == category_id for item in list_categories_b.json()))

        list_products_b = self.client.get(
            "/products",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(list_products_b.status_code, 200)
        self.assertFalse(any(item["id"] == product_id for item in list_products_b.json()))

        # Company B cannot mutate company A records
        update_foreign_product = self.client.put(
            f"/products/{product_id}",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "name": "Hacked",
                "sku": f"SKU-{suffix_a}",
                "categoryId": category_id,
                "brand": "Other",
                "description": "No access",
                "unitPrice": 1.0,
                "costPrice": 1.0,
                "initialStockQuantity": 1,
                "unitOfMeasure": "pcs",
                "status": "inactive",
            },
        )
        self.assertEqual(update_foreign_product.status_code, 404)

        delete_foreign_category = self.client.delete(
            f"/categories/{category_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(delete_foreign_category.status_code, 404)

        # Sanity: owner A can still access own resources
        own_category = self.client.get(
            f"/categories/{category_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        self.assertEqual(own_category.status_code, 200)
        own_product = self.client.get(
            f"/products/{product_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        self.assertEqual(own_product.status_code, 200)
        self.assertEqual(own_product.json()["categoryId"], category_id)
        self.assertEqual(own_product.json()["status"], "active")

        # Prevent unused variable lint noise for explicit company id capture.
        self.assertIsInstance(company_a, int)

    def test_company_admin_cannot_access_other_company_sales_transactions(self):
        suffix_a = uuid.uuid4().hex[:8]
        suffix_b = uuid.uuid4().hex[:8]

        token_a, _company_a = self._register_company_admin(suffix_a)
        token_b, _company_b = self._register_company_admin(suffix_b)

        category_response = self.client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"name": f"SalesCat-{suffix_a}", "description": "Sales category", "status": "active"},
        )
        self.assertEqual(category_response.status_code, 200)
        category_id = category_response.json()["id"]

        product_response = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "name": f"SalesProduct-{suffix_a}",
                "sku": f"SLS-{suffix_a}",
                "categoryId": category_id,
                "brand": "RetailPulse",
                "description": "Isolation sales product",
                "unitPrice": 25.0,
                "costPrice": 10.0,
                "initialStockQuantity": 10,
                "unitOfMeasure": "pcs",
                "status": "active",
            },
        )
        self.assertEqual(product_response.status_code, 200)
        product_id = product_response.json()["id"]

        create_sale = self.client.post(
            "/sales/transactions",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "productId": product_id,
                "quantity": 2,
                "unitPrice": 25.0,
                "customerName": "Isolation Buyer",
                "saleDateTime": "2026-07-19T10:00:00",
                "salesChannel": "In-Store",
                "paymentMethod": "Cash",
                "discountAmount": 0,
                "taxAmount": 0,
            },
        )
        self.assertEqual(create_sale.status_code, 200)
        transaction_id = create_sale.json()["transactionId"]

        list_sales_b = self.client.get(
            "/sales/transactions",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(list_sales_b.status_code, 200)
        self.assertFalse(any(item["transactionId"] == transaction_id for item in list_sales_b.json()))

        get_foreign_sale = self.client.get(
            f"/sales/transactions/{transaction_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(get_foreign_sale.status_code, 404)

        update_foreign_sale = self.client.put(
            f"/sales/transactions/{transaction_id}",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "productId": product_id,
                "quantity": 1,
                "unitPrice": 25.0,
                "customerName": "Hack Buyer",
                "saleDateTime": "2026-07-19T10:30:00",
                "salesChannel": "Online",
                "paymentMethod": "Card",
                "discountAmount": 0,
                "taxAmount": 0,
            },
        )
        self.assertEqual(update_foreign_sale.status_code, 404)

        delete_foreign_sale = self.client.delete(
            f"/sales/transactions/{transaction_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(delete_foreign_sale.status_code, 404)


if __name__ == "__main__":
    unittest.main()
