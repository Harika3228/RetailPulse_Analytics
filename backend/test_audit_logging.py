import time
import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app
from backend.models import AuditLog
from backend.database import SessionLocal


class AuditLoggingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.db.query(AuditLog).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_registration_login_logout_and_password_change_create_audit_entries(self):
        suffix = uuid.uuid4().hex[:8]
        register_response = self.client.post(
            "/auth/register",
            json={
                "companyName": f"Audit Co Unique {suffix}",
                "industry": "Retail",
                "companyEmail": f"audit-unique-{suffix}@example.com",
                "companyAddress": "1 Audit Street",
                "companyPhone": "555-0000",
                "ownerName": "Audit Owner",
                "ownerEmail": f"owner-unique-{suffix}@example.com",
                "password": "password123",
                "confirmPassword": "password123",
            },
        )
        self.assertEqual(register_response.status_code, 200)

        login_response = self.client.post(
            "/auth/login",
            json={"email": f"owner-unique-{suffix}@example.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        token = login_response.json()["access_token"]

        logout_response = self.client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(logout_response.status_code, 200)

        change_password_response = self.client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "currentPassword": "password123",
                "newPassword": "newpassword123",
                "confirmPassword": "newpassword123",
            },
        )
        self.assertEqual(change_password_response.status_code, 200)

        actions = {
            log.action for log in self.db.query(AuditLog).all()
        }
        self.assertIn("Company Registered", actions)
        self.assertIn("User Login", actions)
        self.assertIn("User Logout", actions)
        self.assertIn("Password Changed", actions)

    def test_customer_changes_create_expected_audit_entries(self):
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
                "name": f"Audit Customer {unique_suffix}",
                "email": f"audit-customer-{unique_suffix}@example.com",
                "phone": f"+1-555-{int(unique_suffix[:4], 16) % 10000:04d}",
                "status": "active",
            },
            headers=headers,
        )
        self.assertEqual(create_response.status_code, 200)
        customer_id = create_response.json()["id"]

        update_response = self.client.put(
            f"/customers/{customer_id}",
            json={
                "name": f"Audit Customer {unique_suffix}",
                "email": f"audit-customer-{unique_suffix}@example.com",
                "phone": f"+1-555-{int(unique_suffix[:4], 16) % 10000:04d}",
                "city": "Austin",
                "status": "active",
            },
            headers=headers,
        )
        self.assertEqual(update_response.status_code, 200)

        status_response = self.client.patch(
            f"/customers/{customer_id}/status",
            json={"status": "inactive"},
            headers=headers,
        )
        self.assertEqual(status_response.status_code, 200)

        export_response = self.client.get("/customers/export?report=list&format=csv", headers=headers)
        self.assertEqual(export_response.status_code, 200)

        delete_response = self.client.delete(f"/customers/{customer_id}", headers=headers)
        self.assertEqual(delete_response.status_code, 200)

        actions = {log.action for log in self.db.query(AuditLog).all()}
        self.assertIn("Customer Created", actions)
        self.assertIn("Customer Updated", actions)
        self.assertIn("Customer Deactivated", actions)
        self.assertIn("Customer Status Changed", actions)
        self.assertIn("Customer Exported", actions)
        self.assertIn("Customer Deleted", actions)


if __name__ == "__main__":
    unittest.main()
