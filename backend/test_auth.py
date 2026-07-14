import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["user"]["email"], "admin@retailpulse.com")

    def test_refresh_token_reissues_tokens(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        refresh_token = login_response.json()["refresh_token"]

        response = self.client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)

    def test_register_creates_company_and_admin_user(self):
        unique_suffix = uuid.uuid4().hex[:8]
        payload = {
            "companyName": f"Acme Test {unique_suffix}",
            "industry": "Retail",
            "companyEmail": f"contact+{unique_suffix}@example.com",
            "companyAddress": "123 Main St",
            "companyPhone": "+1-555-0100",
            "ownerName": f"Owner {unique_suffix}",
            "ownerEmail": f"owner+{unique_suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }

        response = self.client.post("/auth/register", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        self.assertEqual(body["user"]["email"], payload["ownerEmail"])
        self.assertEqual(body["user"]["companyName"], payload["companyName"])

    def test_register_resolves_duplicate_company_name_without_failing(self):
        payload = {
            "companyName": "RetailPulse Demo",
            "industry": "Retail",
            "companyEmail": "duplicate-company@example.com",
            "companyAddress": "123 Main St",
            "companyPhone": "+1-555-0100",
            "ownerName": "Duplicate Owner",
            "ownerEmail": f"duplicate-owner-{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }

        response = self.client.post("/auth/register", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        self.assertNotEqual(body["user"]["companyName"], "RetailPulse Demo")


if __name__ == "__main__":
    unittest.main()
