import time
import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class CustomerModuleTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_customer_create_list_update_and_analytics_work(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        unique_suffix = f"{uuid.uuid4().hex[:8]}-{int(time.time() * 1000)}"
        customer_payload = {
            "name": f"Ava {unique_suffix}",
            "email": f"ava-{unique_suffix}@example.com",
            "phone": f"+1-555-{int(unique_suffix[:4], 16) % 10000:04d}",
            "dateOfBirth": "1990-01-15",
            "gender": "female",
            "address": "123 Market Street",
            "city": "Seattle",
            "state": "WA",
            "country": "USA",
            "customerType": "retail",
            "preferredSalesChannel": "online",
            "status": "active",
        }

        create_response = self.client.post("/customers", json=customer_payload, headers=headers)
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertEqual(created["name"], customer_payload["name"])
        self.assertEqual(created["email"], customer_payload["email"])
        self.assertEqual(created["status"], "active")

        list_response = self.client.get("/customers", headers=headers)
        self.assertEqual(list_response.status_code, 200)
        customers = list_response.json()
        self.assertTrue(any(item["id"] == created["id"] for item in customers))

        update_response = self.client.put(
            f"/customers/{created['id']}",
            json={**customer_payload, "city": "Austin"},
            headers=headers,
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["city"], "Austin")

        status_response = self.client.patch(
            f"/customers/{created['id']}/status",
            json={"status": "inactive"},
            headers=headers,
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "inactive")

        analytics_response = self.client.get("/customers/analytics", headers=headers)
        self.assertEqual(analytics_response.status_code, 200)
        analytics = analytics_response.json()
        self.assertIn("totalCustomers", analytics)
        self.assertIn("activeCustomers", analytics)
        self.assertIn("inactiveCustomers", analytics)
        self.assertIn("newCustomersThisMonth", analytics)
        self.assertIn("returningCustomers", analytics)
        self.assertIn("averageCustomerSpend", analytics)
        self.assertIn("totalRevenueGenerated", analytics)
        self.assertIn("averagePurchaseFrequency", analytics)
        self.assertIn("customerGrowthTrend", analytics)
        self.assertIn("segmentationSummary", analytics)
        self.assertIn("monthlyCustomerAcquisition", analytics)

        profile_response = self.client.get(f"/customers/{created['id']}", headers=headers)
        self.assertEqual(profile_response.status_code, 200)
        profile = profile_response.json()
        self.assertIn("lifetimeRevenue", profile)
        self.assertIn("totalOrders", profile)
        self.assertIn("averageOrderValue", profile)
        self.assertIn("lastPurchase", profile)
        self.assertIn("favoriteCategory", profile)
        self.assertIn("favoriteProduct", profile)
        self.assertIn("purchaseFrequency", profile)
        self.assertIn("recentOrders", profile)
        self.assertIn("recentPurchases", profile)
        self.assertIn("recentPayments", profile)
        self.assertIn("timeline", profile)

        history_response = self.client.get(f"/customers/{created['id']}/purchase-history", headers=headers)
        self.assertEqual(history_response.status_code, 200)
        history = history_response.json()
        self.assertIn("totalOrders", history)
        self.assertIn("totalRevenueGenerated", history)
        self.assertIn("totalQuantityPurchased", history)
        self.assertIn("averageOrderValue", history)
        self.assertIn("recentTransactions", history)

    def test_duplicate_email_and_phone_are_rejected_within_company(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        unique_suffix = f"{uuid.uuid4().hex[:8]}-{int(time.time() * 1000)}"
        base_payload = {
            "name": f"Grace {unique_suffix}",
            "email": f"grace-{unique_suffix}@example.com",
            "phone": f"+1-555-{int(unique_suffix[:4], 16) % 10000:04d}",
            "status": "active",
        }

        first_response = self.client.post("/customers", json=base_payload, headers=headers)
        self.assertEqual(first_response.status_code, 200)

        duplicate_email_response = self.client.post(
            "/customers",
            json={**base_payload, "name": f"Grace Duplicate {unique_suffix}", "email": base_payload["email"]},
            headers=headers,
        )
        self.assertEqual(duplicate_email_response.status_code, 400)

        duplicate_phone_response = self.client.post(
            "/customers",
            json={**base_payload, "name": f"Grace Phone {unique_suffix}", "email": f"grace-phone-{unique_suffix}@example.com", "phone": base_payload["phone"]},
            headers=headers,
        )
        self.assertEqual(duplicate_phone_response.status_code, 400)

    def test_customer_lifecycle_notifications_are_visible_to_admins(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        unique_suffix = f"{uuid.uuid4().hex[:8]}-{int(time.time() * 1000)}"
        create_response = self.client.post(
            "/customers",
            json={
                "name": f"Nina {unique_suffix}",
                "email": f"nina-{unique_suffix}@example.com",
                "phone": f"+1-555-{int(unique_suffix[:4], 16) % 10000:04d}",
                "status": "active",
            },
            headers=headers,
        )
        self.assertEqual(create_response.status_code, 200)

        self.client.patch(
            f"/customers/{create_response.json()['id']}/status",
            json={"status": "inactive"},
            headers=headers,
        )

        notifications_response = self.client.get("/notifications", headers=headers)
        self.assertEqual(notifications_response.status_code, 200)
        notifications = notifications_response.json()
        self.assertTrue(any(item["type"] == "customer_registered" for item in notifications))
        self.assertTrue(any(item["type"] == "customer_inactive" for item in notifications))

    def test_blank_customer_payloads_are_tolerated_without_validation_errors(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        create_response = self.client.post(
            "/customers",
            json={"name": "", "email": "", "phone": ""},
            headers=headers,
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertEqual(created["name"], "Unknown Customer")

    def test_customer_timeline_endpoint_returns_events(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        unique_suffix = uuid.uuid4().hex[:8]
        unique_email = f"timeline-{unique_suffix}@example.com"
        unique_phone = f"+1-555-{int(unique_suffix[:4], 16) % 10000:04d}"
        create_response = self.client.post(
            "/customers",
            json={
                "name": "Timeline Customer",
                "email": unique_email,
                "phone": unique_phone,
                "status": "active",
            },
            headers=headers,
        )
        self.assertEqual(create_response.status_code, 200)
        customer_id = create_response.json()["id"]

        timeline_response = self.client.get(f"/customers/{customer_id}/timeline", headers=headers)
        self.assertEqual(timeline_response.status_code, 200)
        timeline = timeline_response.json()
        self.assertIsInstance(timeline, list)
        self.assertTrue(any(item.get("type") == "registration" for item in timeline))

    def test_customer_export_endpoints_return_report_files(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        list_export_response = self.client.get("/customers/export?report=list&format=csv", headers=headers)
        self.assertEqual(list_export_response.status_code, 200)
        self.assertTrue(list_export_response.headers["content-type"].startswith("text/csv"))

        analytics_export_response = self.client.get("/customers/export?report=analytics&format=pdf", headers=headers)
        self.assertEqual(analytics_export_response.status_code, 200)
        self.assertTrue(analytics_export_response.headers["content-type"].startswith("application/pdf"))


if __name__ == "__main__":
    unittest.main()
