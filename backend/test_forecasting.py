import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import Category, Company, Product, SalesTransaction, SalesTransactionLine, User


class ForecastingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _register_company(self, suffix: str) -> tuple[str, int]:
        register_payload = {
            "companyName": f"Forecasting Co {suffix}",
            "industry": "Retail",
            "companyEmail": f"forecast-{suffix}@example.com",
            "companyAddress": "1 Forecast Way",
            "companyPhone": "555-3000",
            "ownerName": f"Owner {suffix}",
            "ownerEmail": f"owner-{suffix}@example.com",
            "password": "Password123",
            "confirmPassword": "Password123",
        }
        response = self.client.post("/auth/register", json=register_payload)
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        with SessionLocal() as db:
            company = db.query(Company).filter(Company.email == register_payload["companyEmail"]).first()
            self.assertIsNotNone(company)
            return token, company.id

    def _create_company_product(self, company_id: int, suffix: str) -> int:
        with SessionLocal() as db:
            category = Category(companyId=company_id, name=f"Category {suffix}", description="Forecast test")
            db.add(category)
            db.commit()
            db.refresh(category)
            product = Product(
                companyId=company_id,
                categoryId=category.id,
                sku=f"SKU-{suffix}",
                name=f"Forecast Product {suffix}",
                brand="Northwind",
                unitPrice=10.0,
                costPrice=8.0,
                stockQuantity=20,
                initialStockQuantity=20,
                unitOfMeasure="pcs",
                status="active",
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            return product.id

    def _create_sales(self, company_id: int, product_id: int, suffix: str, quantity: int, amount: float) -> None:
        with SessionLocal() as db:
            transaction = SalesTransaction(
                companyId=company_id,
                createdBy=1,
                invoiceNumber=f"INV-{suffix}",
                customerName="Forecast Customer",
                saleDateTime=datetime.now(timezone.utc) - timedelta(days=5),
                totalAmount=amount,
            )
            db.add(transaction)
            db.commit()
            db.refresh(transaction)
            db.add(
                SalesTransactionLine(
                    transactionId=transaction.id,
                    productId=product_id,
                    categoryIdSnapshot=1,
                    quantity=quantity,
                    unitPrice=amount / max(1, quantity),
                    lineTotal=amount,
                    productNameSnapshot=f"Forecast Product {suffix}",
                    skuSnapshot=f"SKU-{suffix}",
                    remainingStockSnapshot=0,
                )
            )
            db.commit()

    def test_forecasts_are_persisted_and_exportable_for_the_authenticated_company(self):
        suffix = uuid.uuid4().hex[:8]
        token, company_id = self._register_company(suffix)
        product_id = self._create_company_product(company_id, suffix)
        self._create_sales(company_id, product_id, suffix, quantity=4, amount=40.0)
        self._create_sales(company_id, product_id, f"{suffix}-b", quantity=6, amount=60.0)

        response = self.client.get("/forecasting", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["forecastedDemand"], 0)
        self.assertTrue(body["forecastPoints"])

        with SessionLocal() as db:
            saved_snapshots = db.query(SalesTransaction).filter(SalesTransaction.companyId == company_id).all()
            self.assertTrue(saved_snapshots)

        csv_response = self.client.get("/forecasting/export/demand", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response.headers.get("content-type", ""))

        product_pdf_response = self.client.get("/forecasting/export/products", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(product_pdf_response.status_code, 200)
        self.assertIn("application/pdf", product_pdf_response.headers.get("content-type", ""))

        category_csv_response = self.client.get("/forecasting/export/categories", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(category_csv_response.status_code, 200)
        self.assertIn("text/csv", category_csv_response.headers.get("content-type", ""))

    def test_forecast_and_inventory_events_emit_notifications_and_audit_logs(self):
        suffix = uuid.uuid4().hex[:8]
        token, company_id = self._register_company(suffix)
        product_id = self._create_company_product(company_id, suffix)
        self._create_sales(company_id, product_id, suffix, quantity=9, amount=90.0)
        self._create_sales(company_id, product_id, f"{suffix}-b", quantity=12, amount=120.0)

        forecast_response = self.client.get("/forecasting", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(forecast_response.status_code, 200)

        inventory_response = self.client.get("/inventory", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(inventory_response.status_code, 200)

        export_response = self.client.get("/forecasting/export/demand", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(export_response.status_code, 200)

        notifications_response = self.client.get("/notifications", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(notifications_response.status_code, 200)
        notification_types = {item["type"] for item in notifications_response.json()}
        self.assertTrue(
            {"forecast_demand_exceeds_inventory", "forecast_out_of_stock", "demand_growth_alert"} & notification_types
        )

        audit_response = self.client.get("/audit-logs", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(audit_response.status_code, 200)
        actions = {item["action"] for item in audit_response.json()}
        self.assertIn("Forecast Generated", actions)
        self.assertIn("Forecast Exported", actions)
        self.assertIn("Inventory Recommendation Generated", actions)


if __name__ == "__main__":
    unittest.main()
