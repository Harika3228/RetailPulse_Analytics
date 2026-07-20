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


if __name__ == "__main__":
    unittest.main()
