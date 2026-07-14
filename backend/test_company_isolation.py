import unittest

from fastapi.testclient import TestClient

from backend.main import app


class CompanyIsolationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

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


if __name__ == "__main__":
    unittest.main()
