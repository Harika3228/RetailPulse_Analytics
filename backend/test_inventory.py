import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _create_test_product(self, token: str, suffix: str, stock: int = 12):
        category_response = self.client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"Category-{suffix}", "description": "Inventory category", "status": "active"},
        )
        self.assertEqual(category_response.status_code, 200)
        category_id = category_response.json()["id"]

        product_response = self.client.post(
            "/products",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": f"Inventory Product {suffix}",
                "sku": f"INV-{suffix}",
                "categoryId": category_id,
                "brand": "Northwind",
                "description": "Inventory test product",
                "unitPrice": 15.0,
                "costPrice": 10.0,
                "initialStockQuantity": stock,
                "unitOfMeasure": "pcs",
                "status": "active",
            },
        )
        self.assertEqual(product_response.status_code, 200)
        return product_response.json()["id"]

    def test_inventory_listing_and_movements_are_available(self):
        suffix = uuid.uuid4().hex[:8]
        register_payload = {
            "companyName": f"Inventory Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"inventory-{suffix}@example.com",
            "companyAddress": "1 Inventory Way",
            "companyPhone": "555-2000",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        register_response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(register_response.status_code, 200)
        token = register_response.json()["access_token"]
        product_id = self._create_test_product(token, suffix)

        inventory_response = self.client.get(
            "/inventory",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(inventory_response.status_code, 200)
        inventory_body = inventory_response.json()
        self.assertTrue(any(item["productId"] == product_id for item in inventory_body))
        inventory_item = next(item for item in inventory_body if item["productId"] == product_id)
        self.assertEqual(inventory_item["currentStock"], 12)
        self.assertEqual(inventory_item["reservedStock"], 0)
        self.assertEqual(inventory_item["availableStock"], 12)
        self.assertEqual(inventory_item["stockStatus"], "in_stock")

        movements_response = self.client.get(
            f"/inventory/{product_id}/movements",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(movements_response.status_code, 200)
        self.assertTrue(len(movements_response.json()) >= 1)

    def test_inventory_listing_can_be_sorted_by_current_stock_desc(self):
        suffix = uuid.uuid4().hex[:8]
        register_payload = {
            "companyName": f"Sort Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"sort-{suffix}@example.com",
            "companyAddress": "1 Sort Way",
            "companyPhone": "555-2002",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-sort-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        register_response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(register_response.status_code, 200)
        token = register_response.json()["access_token"]
        self._create_test_product(token, suffix, stock=8)
        self._create_test_product(token, f"{suffix}-b", stock=25)

        inventory_response = self.client.get(
            "/inventory?sort_by=current_stock&sort_direction=desc",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(inventory_response.status_code, 200)
        inventory_body = inventory_response.json()
        self.assertGreaterEqual(len(inventory_body), 2)
        self.assertEqual(inventory_body[0]["currentStock"], 25)
        self.assertEqual(inventory_body[0]["productName"], "Inventory Product " + f"{suffix}-b")

    def test_invalid_adjustments_are_rejected(self):
        suffix = uuid.uuid4().hex[:8]
        register_payload = {
            "companyName": f"Validation Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"validation-{suffix}@example.com",
            "companyAddress": "1 Validation Way",
            "companyPhone": "555-2003",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-validation-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        register_response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(register_response.status_code, 200)
        token = register_response.json()["access_token"]
        product_id = self._create_test_product(token, suffix)

        missing_reason_response = self.client.post(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "adjustmentType": "stock_in",
                "quantity": 1,
                "reason": "   ",
                "remarks": "No reason",
            },
        )
        self.assertEqual(missing_reason_response.status_code, 422)

        stock_out_too_large_response = self.client.post(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "adjustmentType": "stock_out",
                "quantity": 20,
                "reason": "Inventory correction",
                "remarks": "Too large",
            },
        )
        self.assertEqual(stock_out_too_large_response.status_code, 400)

        zero_quantity_response = self.client.post(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "adjustmentType": "stock_in",
                "quantity": 0,
                "reason": "Zero quantity",
                "remarks": "Invalid",
            },
        )
        self.assertEqual(zero_quantity_response.status_code, 422)

    def test_manual_adjustments_create_admin_notifications(self):
        suffix = uuid.uuid4().hex[:8]
        register_payload = {
            "companyName": f"Notifications Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"notifications-{suffix}@example.com",
            "companyAddress": "1 Notification Way",
            "companyPhone": "555-2004",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-notifications-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        register_response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(register_response.status_code, 200)
        token = register_response.json()["access_token"]
        product_id = self._create_test_product(token, suffix, stock=6)

        first_adjustment_response = self.client.post(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "adjustmentType": "stock_out",
                "quantity": 1,
                "reason": "Low stock correction",
                "remarks": "Trigger low stock",
            },
        )
        self.assertEqual(first_adjustment_response.status_code, 200)

        second_adjustment_response = self.client.post(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "adjustmentType": "stock_out",
                "quantity": 5,
                "reason": "Empty stock correction",
                "remarks": "Trigger out of stock",
            },
        )
        self.assertEqual(second_adjustment_response.status_code, 200)

        third_adjustment_response = self.client.post(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "adjustmentType": "manual_adjustment",
                "quantity": 2,
                "reason": "Manual inventory correction",
                "remarks": "Trigger manual adjustment",
            },
        )
        self.assertEqual(third_adjustment_response.status_code, 200)

        notifications_response = self.client.get(
            "/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(notifications_response.status_code, 200)
        notification_types = {item["type"] for item in notifications_response.json()}
        self.assertIn("manual_adjustment", notification_types)
        self.assertIn("low_stock", notification_types)
        self.assertIn("out_of_stock", notification_types)

    def test_inventory_dashboard_summary_endpoint(self):
        suffix = uuid.uuid4().hex[:8]
        register_payload = {
            "companyName": f"Summary Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"summary-{suffix}@example.com",
            "companyAddress": "1 Summary Way",
            "companyPhone": "555-2005",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-summary-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        register_response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(register_response.status_code, 200)
        token = register_response.json()["access_token"]
        self._create_test_product(token, suffix, stock=5)
        self._create_test_product(token, f"{suffix}-b", stock=0)

        response = self.client.get(
            "/dashboard/inventory-summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalProducts"], 2)
        self.assertEqual(body["totalInventoryQuantity"], 5)
        self.assertEqual(body["lowStockProducts"], 1)
        self.assertEqual(body["outOfStockProducts"], 1)

    def test_stock_adjustments_can_be_created_and_listed(self):
        suffix = uuid.uuid4().hex[:8]
        register_payload = {
            "companyName": f"Adjust Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"adjust-{suffix}@example.com",
            "companyAddress": "1 Adjustment Way",
            "companyPhone": "555-2001",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-adjust-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        register_response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(register_response.status_code, 200)
        token = register_response.json()["access_token"]
        product_id = self._create_test_product(token, suffix)

        adjustment_response = self.client.post(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "adjustmentType": "stock_in",
                "quantity": 5,
                "reason": "Restock",
                "remarks": "Added from supplier",
            },
        )
        self.assertEqual(adjustment_response.status_code, 200)
        adjustment_body = adjustment_response.json()
        self.assertEqual(adjustment_body["adjustmentType"], "stock_in")
        self.assertEqual(adjustment_body["quantity"], 5)
        self.assertEqual(adjustment_body["reason"], "Restock")
        self.assertEqual(adjustment_body["remarks"], "Added from supplier")

        inventory_response = self.client.get(
            "/inventory",
            headers={"Authorization": f"Bearer {token}"},
        )
        inventory_item = next(item for item in inventory_response.json() if item["productId"] == product_id)
        self.assertEqual(inventory_item["currentStock"], 17)

        adjustments_response = self.client.get(
            f"/inventory/{product_id}/adjustments",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(adjustments_response.status_code, 200)
        self.assertEqual(len(adjustments_response.json()), 1)

        movements_response = self.client.get(
            f"/inventory/{product_id}/movements",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(movements_response.status_code, 200)
        adjustment_movement = next(
            movement for movement in movements_response.json() if movement["movementType"] == "Stock Addition"
        )
        self.assertEqual(adjustment_movement["previousQuantity"], 12)
        self.assertEqual(adjustment_movement["updatedQuantity"], 17)
        self.assertEqual(adjustment_movement["quantityChanged"], 5)
        self.assertEqual(adjustment_movement["reason"], "Restock")
        self.assertTrue(adjustment_movement["user"].strip())


if __name__ == "__main__":
    unittest.main()
