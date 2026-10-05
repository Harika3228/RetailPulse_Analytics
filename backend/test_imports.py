import time
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.controllers.imports_controller import _record_import_event, enqueue_import
from backend.database import SessionLocal
from backend.main import app
from backend.models import (
    AuditLog,
    ImportBatch,
    Notification,
    QualityIssue,
    ReconciliationExecution,
    StockMovement,
    User,
)


def _unique_suffix() -> str:
    return f"{uuid.uuid4().int % 100000000:08d}{int(time.time() * 1000) % 100000:05d}"


class DataImportModuleTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        login_response = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _create_category(self) -> int:
        payload = {"name": f"ImportCat-{_unique_suffix()}", "description": "Import test category"}
        response = self.client.post("/categories", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def _upload_csv(self, entity_type: str, csv_text: str):
        return self.client.post(
            f"/imports/{entity_type}/preview",
            content=csv_text,
            headers={**self.headers, "Content-Type": "text/csv"},
        )

    def _confirm_import(self, batch_id: int):
        response = self.client.post(f"/imports/{batch_id}/confirm", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "queued")
        detail_response = self.client.get(f"/imports/{batch_id}", headers=self.headers)
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        batch = detail_response.json()
        self.assertEqual(batch["progressPercent"], 100)
        self.assertTrue(batch["startedAt"])
        self.assertTrue(batch["completedAt"])
        self.assertGreaterEqual(batch["durationSeconds"], 0)
        self.assertTrue(batch["importedBy"])
        batch["skippedCount"] = batch["invalidCount"] + batch["duplicateCount"]
        return batch

    def test_inventory_import_updates_stock_and_records_movement(self):
        suffix = _unique_suffix()
        category_id = self._create_category()
        product_response = self.client.post(
            "/products",
            headers=self.headers,
            json={
                "name": f"Inventory Import {suffix}",
                "sku": f"INV-{suffix}",
                "categoryId": category_id,
                "brand": "Import Test",
                "unitPrice": 20,
                "costPrice": 10,
                "stockQuantity": 5,
                "unitOfMeasure": "each",
            },
        )
        self.assertEqual(product_response.status_code, 200, product_response.text)
        product_id = product_response.json()["id"]

        preview_response = self._upload_csv(
            "inventory",
            f"SKU,StockQuantity,Reason\nINV-{suffix},12,Physical count\n",
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["validRows"], 1)

        confirmed = self._confirm_import(preview["batchId"])
        self.assertEqual(confirmed["status"], "completed")

        updated_product = self.client.get(f"/products/{product_id}", headers=self.headers)
        self.assertEqual(updated_product.status_code, 200)
        self.assertEqual(updated_product.json()["stockQuantity"], 12)
        movements = self.client.get(f"/inventory/{product_id}/movements", headers=self.headers)
        self.assertEqual(movements.status_code, 200)
        self.assertTrue(any(item["movementType"] == "Inventory Import" for item in movements.json()))

    def test_inventory_import_runs_reconciliation_and_surfaces_quality_issue(self):
        suffix = _unique_suffix()
        category_id = self._create_category()
        product_response = self.client.post(
            "/products",
            headers=self.headers,
            json={
                "name": f"Reconcile Inventory {suffix}",
                "sku": f"DQ-{suffix}",
                "categoryId": category_id,
                "brand": "Quality Check",
                "unitPrice": 12,
                "costPrice": 6,
                "stockQuantity": 5,
                "unitOfMeasure": "each",
            },
        )
        self.assertEqual(product_response.status_code, 200, product_response.text)
        product_id = product_response.json()["id"]

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == "admin@retailpulse.com").first()
            before_count = db.query(ReconciliationExecution).filter(
                ReconciliationExecution.companyId == user.companyId
            ).count()
            movement = StockMovement(
                companyId=user.companyId,
                productId=product_id,
                productName=f"Reconcile Inventory {suffix}",
                sku=f"DQ-{suffix}",
                movementType="Test Inconsistency",
                previousQuantity=5,
                quantityChanged=1,
                updatedQuantity=99,
                reference="quality integration test",
                actor=user.email,
                actorUserId=user.id,
            )
            db.add(movement)
            db.commit()
            movement_id = movement.id
            company_id = user.companyId
        finally:
            db.close()

        preview = self._upload_csv("inventory", f"SKU,StockQuantity\nDQ-{suffix},8\n")
        self.assertEqual(preview.status_code, 200, preview.text)
        completed = self._confirm_import(preview.json()["batchId"])
        self.assertEqual(completed["status"], "completed")

        db = SessionLocal()
        try:
            issue = db.query(QualityIssue).filter(
                QualityIssue.companyId == company_id,
                QualityIssue.issueKey == f"movement-{movement_id}-quantity",
            ).first()
            self.assertIsNotNone(issue)
            self.assertEqual(issue.status, "open")
            latest = db.query(ReconciliationExecution).filter(
                ReconciliationExecution.companyId == company_id
            ).order_by(ReconciliationExecution.id.desc()).first()
            self.assertGreater(db.query(ReconciliationExecution).filter(
                ReconciliationExecution.companyId == company_id
            ).count(), before_count)
            self.assertIn(latest.status, {"completed", "completed_with_issues"})
        finally:
            db.close()

        report = self.client.get("/data-quality", headers=self.headers)
        self.assertEqual(report.status_code, 200, report.text)
        self.assertTrue(any(item["id"] == f"movement-{movement_id}-quantity" for item in report.json()["issues"]))

    def test_import_upload_api_enforces_authorization_and_csv_type(self):
        unauthenticated = self.client.post(
            "/imports/products/preview",
            content="SKU,Name\nSKU-1,Product\n",
            headers={"Content-Type": "text/csv"},
        )
        self.assertEqual(unauthenticated.status_code, 401)

        unsupported_mime = self.client.post(
            "/imports/products/preview",
            content='{"SKU":"SKU-1"}',
            headers={**self.headers, "Content-Type": "application/json"},
        )
        self.assertEqual(unsupported_mime.status_code, 415)

        unsupported_extension = self.client.post(
            "/imports/products/preview?fileName=products.xlsx",
            content="SKU,Name\nSKU-1,Product\n",
            headers={**self.headers, "Content-Type": "text/csv"},
        )
        self.assertEqual(unsupported_extension.status_code, 415)

    def test_import_audit_events_and_notifications_are_linked_and_deduplicated(self):
        suffix = _unique_suffix()
        preview_response = self._upload_csv(
            "customers",
            f"Name,Email,Phone\nEvent Customer,event-{suffix}@example.com,+1-555-{suffix}\n",
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        batch_id = preview_response.json()["batchId"]
        completed = self._confirm_import(batch_id)
        self.assertEqual(completed["status"], "completed")

        db = SessionLocal()
        try:
            batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
            actor = db.query(User).filter(User.email == batch.importedBy).first()
            audit_entries = (
                db.query(AuditLog)
                .filter(AuditLog.companyId == batch.companyId, AuditLog.resourceId == str(batch_id))
                .all()
            )
            actions = [entry.action for entry in audit_entries]
            for action in ("File Uploaded", "Import Started", "Import Completed"):
                matching = [entry for entry in audit_entries if entry.action == action]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0].resourceType, "Import")
                self.assertEqual(matching[0].userId, actor.id)
                self.assertIsNotNone(matching[0].createdAt)
                self.assertEqual(matching[0].companyId, batch.companyId)
            self.assertEqual(len(actions), len(set(actions)))

            notification_keys = [f"import:{batch_id}:started", f"import:{batch_id}:completed"]
            notifications = db.query(Notification).filter(Notification.alertKey.in_(notification_keys)).all()
            self.assertEqual(len(notifications), 2)
            self.assertTrue(all(item.resourceType == "Import" and item.resourceId == str(batch_id) for item in notifications))

            _record_import_event(
                db,
                batch,
                "Import Completed",
                actor=actor,
                notification=(
                    "completed",
                    "import_completed",
                    "Import Completed",
                    f"Import {batch.fileName} (batch {batch.id}) completed successfully with {batch.insertedCount} records processed.",
                ),
            )
            self.assertEqual(
                db.query(Notification).filter(Notification.alertKey == f"import:{batch_id}:completed").count(),
                1,
            )
            self.assertEqual(
                db.query(AuditLog).filter(AuditLog.resourceId == str(batch_id), AuditLog.action == "Import Completed").count(),
                1,
            )
        finally:
            db.close()

    def test_inventory_import_rejects_fractional_stock_quantity(self):
        suffix = _unique_suffix()
        category_id = self._create_category()
        product_response = self.client.post(
            "/products",
            headers=self.headers,
            json={
                "name": f"Fractional Inventory {suffix}",
                "sku": f"FRAC-{suffix}",
                "categoryId": category_id,
                "brand": "Import Test",
                "unitPrice": 20,
                "costPrice": 10,
                "stockQuantity": 5,
                "unitOfMeasure": "each",
            },
        )
        self.assertEqual(product_response.status_code, 200, product_response.text)

        response = self._upload_csv("inventory", f"SKU,StockQuantity\nFRAC-{suffix},1.5\n")
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual(preview["validRows"], 0)
        self.assertEqual(preview["invalidRows"], 1)
        self.assertIn("must be an integer", preview["rows"][0]["messages"][0])

    def test_background_import_persists_progress_across_chunks(self):
        suffix = _unique_suffix()
        category_id = self._create_category()
        rows = ["SKU,Name,CategoryName,Brand,UnitPrice,CostPrice,StockQuantity"]
        rows.extend(
            f"BULK-{suffix}-{index},Bulk Product {index},{category_id},BulkBrand,10,5,1"
            for index in range(205)
        )
        preview_response = self._upload_csv("products", "\n".join(rows) + "\n")
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["validRows"], 205)

        completed = self._confirm_import(preview["batchId"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["insertedCount"], 205)
        self.assertEqual(completed["processedCount"], 205)
        self.assertEqual(completed["progressPercent"], 100)

    def test_queued_import_can_be_cancelled_with_record_reasons(self):
        suffix = _unique_suffix()
        preview_response = self._upload_csv(
            "customers",
            f"Name,Email,Phone\nQueued Customer,queued-{suffix}@example.com,+1-555-999{suffix[:4]}\n",
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        batch_id = preview_response.json()["batchId"]

        db = SessionLocal()
        try:
            queued, _user_id = enqueue_import(batch_id, db, f"Bearer {self.token}")
        finally:
            db.close()
        self.assertEqual(queued.status, "queued")

        cancel_response = self.client.post(f"/imports/{batch_id}/cancel", headers=self.headers)
        self.assertEqual(cancel_response.status_code, 200, cancel_response.text)
        detail_response = self.client.get(f"/imports/{batch_id}", headers=self.headers)
        detail = detail_response.json()
        self.assertEqual(detail["status"], "cancelled")
        self.assertEqual(detail["processedCount"], detail["totalRows"])
        self.assertEqual(detail["rows"][0]["status"], "cancelled")
        self.assertIn("cancelled", detail["rows"][0]["message"].lower())
        db = SessionLocal()
        try:
            cancelled_event = db.query(AuditLog).filter(
                AuditLog.resourceId == str(batch_id),
                AuditLog.action == "Import Cancelled",
            ).one()
            self.assertEqual(cancelled_event.resourceType, "Import")
        finally:
            db.close()

    def test_preview_rejects_invalid_headers_and_ragged_rows(self):
        duplicate_header = self._upload_csv(
            "inventory",
            "SKU,StockQuantity,qty\nSKU-1,10,10\n",
        )
        self.assertEqual(duplicate_header.status_code, 400)
        self.assertIn("same field", duplicate_header.json()["detail"])

        unknown_header = self._upload_csv(
            "inventory",
            "SKU,StockQuantity,WarehouseCode\nSKU-1,10,WH-1\n",
        )
        self.assertEqual(unknown_header.status_code, 400)
        self.assertIn("Unrecognized column", unknown_header.json()["detail"])

        ragged_row = self._upload_csv(
            "inventory",
            "SKU,StockQuantity\nSKU-1,10,unexpected\n",
        )
        self.assertEqual(ragged_row.status_code, 200, ragged_row.text)
        self.assertEqual(ragged_row.json()["invalidRows"], 1)
        self.assertTrue(
            any("more values than columns" in message for message in ragged_row.json()["rows"][0]["messages"])
        )

    def test_preview_rejects_files_over_row_limit_instead_of_truncating(self):
        rows = "SKU,StockQuantity\n" + "SKU-1,1\n" * 10001
        response = self._upload_csv("inventory", rows)
        self.assertEqual(response.status_code, 413, response.text)
        self.assertIn("more than 10000 data rows", response.json()["detail"])

    def test_products_import_accepts_common_currency_and_whitespace_formats(self):
        category_name = f"Electronics-{_unique_suffix()}"
        category = self.client.post(
            "/categories",
            json={"name": category_name, "description": "Real-world import category"},
            headers=self.headers,
        )
        self.assertEqual(category.status_code, 200, category.text)
        category_id = category.json()["id"]

        csv_text = (
            "SKU,Product Name,Category,Unit Price,Stock Quantity\n"
            f'SKU001,Laptop,{category_name},"₹55,000",20\n'
            f'SKU002,Wireless Mouse, {category_name},"1,200",100\n'
        )

        response = self._upload_csv("products", csv_text)
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual(preview["validRows"], 2)
        self.assertEqual(preview["invalidRows"], 0)
        self.assertEqual(preview["duplicateRows"], 0)
        self.assertEqual(preview["rows"][0]["data"]["categoryId"], category_id)

    def test_products_import_accepts_case_and_spacing_variations_for_category_names(self):
        category_name = f"Electronics-{_unique_suffix()} "
        category = self.client.post(
            "/categories",
            json={"name": category_name.strip(), "description": "Category name normalization test"},
            headers=self.headers,
        )
        self.assertEqual(category.status_code, 200, category.text)

        csv_text = (
            "SKU,Product Name,Category,Unit Price,Stock Quantity\n"
            f"SKU555,Monitor, {category_name.lower()} , 2999, 12\n"
            f"SKU556,Keyboard,{category_name.upper().strip()}, 699, 20\n"
        )

        response = self._upload_csv("products", csv_text)
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual(preview["validRows"], 2)
        self.assertEqual(preview["invalidRows"], 0)
        self.assertEqual(preview["duplicateRows"], 0)

    def test_products_import_full_pipeline(self):
        category_id = self._create_category()
        existing_sku = f"IMP-EX-{_unique_suffix()}"
        create_product = self.client.post(
            "/products",
            json={
                "name": f"Existing {existing_sku}",
                "sku": existing_sku,
                "categoryId": category_id,
                "brand": "ImportBrand",
                "unitPrice": 50,
                "costPrice": 20,
                "stockQuantity": 10,
                "unitOfMeasure": "piece",
            },
            headers=self.headers,
        )
        self.assertEqual(create_product.status_code, 200)

        new_sku = f"IMP-NW-{_unique_suffix()}"
        csv_text = (
            "sku,name,categoryName,brand,unitPrice,costPrice,stockQuantity,unitOfMeasure,status\n"
            f"{new_sku},Imported Product,{category_id},ImportBrand,120,80,25,piece,active\n"
            f",{category_id},Bad Row,badprice,xx,5,piece,active\n"
            f"{new_sku},Dup Within File,{category_id},ImportBrand,120,80,25,piece,active\n"
            f"{existing_sku},Dup In System,{category_id},ImportBrand,50,20,10,piece,active\n"
        )
        preview_response = self._upload_csv("products", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["entityType"], "products")
        self.assertEqual(preview["totalRows"], 4)
        self.assertEqual(preview["validRows"], 1)
        self.assertEqual(preview["invalidRows"], 1)
        self.assertEqual(preview["duplicateRows"], 2)

        confirmed = self._confirm_import(preview["batchId"])
        self.assertEqual(confirmed["insertedCount"], 1)

        list_response = self.client.get(f"/products?q={new_sku}", headers=self.headers)
        self.assertEqual(list_response.status_code, 200)
        products = list_response.json()
        self.assertTrue(any(item["sku"].upper() == new_sku.upper() and item["stockQuantity"] == 25 for item in products))

        reconfirm = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(reconfirm.status_code, 400)

        history_response = self.client.get("/imports", headers=self.headers)
        self.assertEqual(history_response.status_code, 200)
        history = history_response.json()
        batch_entry = next((item for item in history if item["id"] == preview["batchId"]), None)
        self.assertIsNotNone(batch_entry)
        self.assertEqual(batch_entry["status"], "completed")
        self.assertEqual(batch_entry["insertedCount"], 1)

        detail_response = self.client.get(f"/imports/{preview['batchId']}", headers=self.headers)
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        statuses = {row["status"] for row in detail["rows"]}
        self.assertIn("imported", statuses)
        self.assertIn("invalid", statuses)
        self.assertIn("duplicate", statuses)
        self.assertNotIn("failed", statuses)

        delete_response = self.client.delete(f"/imports/{preview['batchId']}", headers=self.headers)
        self.assertEqual(delete_response.status_code, 200)

    def test_customers_import_full_pipeline(self):
        existing_email = f"imp-ex-{_unique_suffix()}@example.com"
        create_existing = self.client.post(
            "/customers",
            json={
                "name": "Existing Import Customer",
                "email": existing_email,
                "phone": f"+1-555-{_unique_suffix()[:6]}",
            },
            headers=self.headers,
        )
        self.assertEqual(create_existing.status_code, 200, create_existing.text)

        new_email = f"imp-new-{_unique_suffix()}@example.com"
        phone_a = f"+1-555-100{_unique_suffix()[:4]}"
        csv_text = (
            "name,email,phone,city,country,customerType,status\n"
            f"Imported Customer,{new_email},{phone_a},Seattle,USA,retail,active\n"
            f"Bad Phone,bad-{_unique_suffix()}@example.com,12345,X,Y,retail,active\n"
            f"Duplicate Email,{existing_email},+1-555-9990000,X,Y,retail,active\n"
        )
        preview_response = self._upload_csv("customers", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["totalRows"], 3)
        self.assertEqual(preview["validRows"], 1)
        self.assertEqual(preview["invalidRows"], 1)
        self.assertEqual(preview["duplicateRows"], 1)

        confirmed = self._confirm_import(preview["batchId"])
        self.assertEqual(confirmed["insertedCount"], 1)

        list_response = self.client.get(f"/customers?q={new_email}", headers=self.headers)
        self.assertEqual(list_response.status_code, 200)
        customers = list_response.json()
        imported = [item for item in customers if item["email"] == new_email]
        self.assertEqual(len(imported), 1)
        self.assertTrue(imported[0].get("customerId", "").startswith("CUST-"))

    def test_sales_import_creates_transactions_and_updates_stock(self):
        category_id = self._create_category()
        sku = f"IMP-SL-{_unique_suffix()}"
        product = self.client.post(
            "/products",
            json={
                "name": f"Sellable {sku}",
                "sku": sku,
                "categoryId": category_id,
                "brand": "SalesBrand",
                "unitPrice": 10,
                "costPrice": 5,
                "stockQuantity": 100,
                "unitOfMeasure": "piece",
            },
            headers=self.headers,
        )
        self.assertEqual(product.status_code, 200, product.text)

        invoice = f"IMP-INV-{_unique_suffix()}"
        customer = self.client.post(
            "/customers",
            json={
                "name": "Sales Import Customer",
                "email": f"sales-imp-{_unique_suffix()}@example.com",
                "phone": f"+1-555-200{_unique_suffix()[:4]}",
            },
            headers=self.headers,
        )
        self.assertEqual(customer.status_code, 200)
        customer_email = customer.json()["email"]

        csv_text = (
            "invoiceNumber,customerEmail,sku,quantity,unitPrice,saleDate,paymentMethod,paymentStatus\n"
            f"{invoice},{customer_email},{sku},10,10,2026-01-15,Cash,Paid\n"
            f"{invoice},{customer_email},{sku},5,12,2026-01-15,Cash,Paid\n"
            f",walkin-{_unique_suffix()}@example.com,OVERSTOCK-SKU-MISSING,5000,9,2026-01-15,Cash,Paid\n"
        )
        # third row references an unknown SKU -> invalid (product not found / insufficient stock path)
        preview_response = self._upload_csv("sales", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["entityType"], "sales")
        self.assertEqual(preview["validRows"], 2)
        self.assertEqual(preview["invalidRows"], 1)

        confirmed = self._confirm_import(preview["batchId"])
        self.assertEqual(confirmed["insertedCount"], 2)
        self.assertEqual(confirmed["failedCount"], 0)

        sales_list = self.client.get("/sales", headers=self.headers)
        self.assertEqual(sales_list.status_code, 200)
        transactions = [
            item
            for item in sales_list.json()
            if isinstance(item, dict) and item.get("invoiceNumber") == invoice
        ]
        self.assertEqual(len(transactions), 1)
        transaction = transactions[0]
        self.assertEqual(len(transaction.get("lines", [])), 2)
        expected_total = 10 * 10 + 5 * 12
        self.assertAlmostEqual(float(transaction["totalAmount"]), float(expected_total), places=2)

        product_detail = None
        products_response = self.client.get(f"/products?q={sku}", headers=self.headers)
        for item in products_response.json():
            if item["sku"] == sku:
                product_detail = item
        self.assertIsNotNone(product_detail)
        self.assertEqual(product_detail["stockQuantity"], 85)

    def test_sales_row_validation_customer_existence_and_stock(self):
        category_id = self._create_category()
        sku = f"IMP-RV-{_unique_suffix()}"
        product = self.client.post(
            "/products",
            json={
                "name": f"RowCheck {sku}",
                "sku": sku,
                "categoryId": category_id,
                "brand": "RowBrand",
                "unitPrice": 10,
                "costPrice": 5,
                "stockQuantity": 100,
                "unitOfMeasure": "piece",
            },
            headers=self.headers,
        )
        self.assertEqual(product.status_code, 200, product.text)

        known_email = f"rowcheck-{_unique_suffix()}@example.com"
        known_name = f"Row Customer {_unique_suffix()}"
        customer = self.client.post(
            "/customers",
            json={
                "name": known_name,
                "email": known_email,
                "phone": f"+1-555-300{_unique_suffix()[:4]}",
            },
            headers=self.headers,
        )
        self.assertEqual(customer.status_code, 200)

        inv_email = f"IMP-E-{_unique_suffix()}"
        inv_ghost = f"IMP-G-{_unique_suffix()}"
        inv_stock = f"IMP-S-{_unique_suffix()}"
        inv_name = f"IMP-N-{_unique_suffix()}"
        csv_text = (
            "invoiceNumber,customerName,customerEmail,sku,quantity,unitPrice,saleDate,paymentMethod,paymentStatus\n"
            f"{inv_email},,{known_email},{sku},10,10,2026-01-15,Cash,Paid\n"
            f"{inv_ghost},,ghost-{_unique_suffix()}@example.com,{sku},5,10,2026-01-15,Cash,Paid\n"
            f"{inv_stock},{known_name},,{sku},150,10,2026-01-15,Cash,Paid\n"
            f"{inv_name},{known_name},,{sku},5,10,2026-01-15,Cash,Paid\n"
        )
        preview_response = self._upload_csv("sales", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["totalRows"], 4)
        self.assertEqual(preview["validRows"], 2)
        self.assertEqual(preview["invalidRows"], 2)

        detail_response = self.client.get(f"/imports/{preview['batchId']}", headers=self.headers)
        self.assertEqual(detail_response.status_code, 200)
        invalid_messages = "; ".join(
            " ".join(row.get("messages") or [])
            if isinstance(row.get("messages"), list)
            else str(row.get("message") or "")
            for row in detail_response.json()["rows"]
            if row.get("status") == "invalid"
        ).lower()
        self.assertIn("no customer found with email", invalid_messages)
        self.assertIn("insufficient stock", invalid_messages)

        confirmed = self._confirm_import(preview["batchId"])
        self.assertEqual(confirmed["insertedCount"], 2)
        self.assertEqual(confirmed["failedCount"], 0)

        sales_list = self.client.get("/sales", headers=self.headers)
        self.assertEqual(sales_list.status_code, 200)
        transactions = sales_list.json()
        imported_invoices = {
            item.get("invoiceNumber")
            for item in transactions
            if isinstance(item, dict)
        }
        self.assertIn(inv_email, imported_invoices)
        self.assertIn(inv_name, imported_invoices)
        self.assertNotIn(inv_ghost, imported_invoices)
        self.assertNotIn(inv_stock, imported_invoices)

    def test_failed_records_export(self):
        category_id = self._create_category()
        existing_sku = f"EXP-EX-{_unique_suffix()}"
        create_product = self.client.post(
            "/products",
            json={
                "name": f"Export Existing {existing_sku}",
                "sku": existing_sku,
                "categoryId": category_id,
                "brand": "ExportBrand",
                "unitPrice": 50,
                "costPrice": 20,
                "stockQuantity": 10,
                "unitOfMeasure": "piece",
            },
            headers=self.headers,
        )
        self.assertEqual(create_product.status_code, 200)

        new_sku = f"EXP-NW-{_unique_suffix()}"
        csv_text = (
            "sku,name,categoryName,unitPrice,stockQuantity\n"
            f"{new_sku},Good Product,{category_id},25,5\n"
            f",Bad Product,{category_id},25,5\n"
            f"{existing_sku},Dup Product,{category_id},50,10\n"
        )
        preview_response = self._upload_csv("products", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["validRows"], 1)
        self.assertEqual(preview["invalidRows"], 1)
        self.assertEqual(preview["duplicateRows"], 1)

        confirm_response = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)

        export_response = self.client.get(f"/imports/{preview['batchId']}/failed-records", headers=self.headers)
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("text/csv", export_response.headers.get("content-type", ""))
        self.assertIn("attachment", export_response.headers.get("content-disposition", ""))
        body = export_response.text.lstrip("\ufeff")
        lines = [line for line in body.strip().splitlines() if line]
        self.assertTrue(lines[0].startswith("RowNumber,Status,ErrorType,Errors,"))
        self.assertEqual(len(lines), 3)  # header + 2 problem rows
        self.assertIn("SKU is required", body)
        self.assertIn("Duplicate SKU already exists in system", body)
        self.assertNotIn("Good Product", body)

        missing_export = self.client.get("/imports/99999999/failed-records", headers=self.headers)
        self.assertEqual(missing_export.status_code, 404)

    def test_import_errors_endpoint(self):
        category_id = self._create_category()
        new_sku = f"ERR-NW-{_unique_suffix()}"
        csv_text = (
            "sku,name,categoryName,unitPrice,stockQuantity\n"
            f"{new_sku},Good Product,{category_id},25,5\n"
            f",Bad Product,{category_id},0,5\n"
        )
        preview_response = self._upload_csv("products", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["invalidRows"], 1)

        errors_response = self.client.get(f"/imports/{preview['batchId']}/errors", headers=self.headers)
        self.assertEqual(errors_response.status_code, 200, errors_response.text)
        payload = errors_response.json()
        self.assertEqual(payload["batchId"], preview["batchId"])
        self.assertEqual(payload["totalErrors"], 2)
        messages = [error["message"] for error in payload["errors"]]
        self.assertIn("SKU is required", messages)
        self.assertIn("Unit price must be greater than zero", messages)
        fields = {error["field"] for error in payload["errors"]}
        self.assertIn("SKU", fields)
        self.assertIn("Unit Price", fields)
        self.assertTrue(all(error["errorType"] == "Validation" for error in payload["errors"]))
        self.assertTrue(all("name" in error["recordData"] for error in payload["errors"]))
        rows = [error["rowNumber"] for error in payload["errors"]]
        self.assertTrue(all(row > 1 for row in rows))

        missing_errors = self.client.get("/imports/99999999/errors", headers=self.headers)
        self.assertEqual(missing_errors.status_code, 404)

        analyst_login = self.client.post(
            "/auth/login",
            json={"email": "analyst@retailpulse.com", "password": "password123"},
        )
        analyst_headers = {"Authorization": f"Bearer {analyst_login.json()['access_token']}"}
        forbidden = self.client.get(f"/imports/{preview['batchId']}/errors", headers=analyst_headers)
        self.assertEqual(forbidden.status_code, 403)

    def test_unexpected_processing_errors_are_sanitized(self):
        category_id = self._create_category()
        suffix = _unique_suffix()
        preview_response = self._upload_csv(
            "products",
            f"SKU,Name,CategoryName,UnitPrice,StockQuantity\nSAFE-{suffix},Safe Product,{category_id},10,2\n",
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        batch_id = preview_response.json()["batchId"]
        secret_detail = "sqlite:///private/path; password=top-secret"

        with patch(
            "backend.controllers.imports_controller._process_product_records",
            side_effect=RuntimeError(secret_detail),
        ):
            batch = self._confirm_import(batch_id)

        self.assertEqual(batch["status"], "failed")
        self.assertNotIn("top-secret", batch["failureMessage"])
        self.assertNotIn("private/path", batch["failureMessage"])

        errors_response = self.client.get(f"/imports/{batch_id}/errors", headers=self.headers)
        errors = errors_response.json()["errors"]
        self.assertEqual(errors[0]["errorType"], "Processing")
        self.assertEqual(errors[0]["recordData"]["name"], "Safe Product")
        self.assertNotIn("top-secret", errors[0]["message"])
        db = SessionLocal()
        try:
            self.assertEqual(
                db.query(Notification).filter(Notification.alertKey == f"import:{batch_id}:failed").count(),
                1,
            )
            self.assertEqual(
                db.query(AuditLog).filter(
                    AuditLog.resourceId == str(batch_id),
                    AuditLog.action == "Import Failed",
                ).count(),
                1,
            )
        finally:
            db.close()

    def test_import_history_completed_with_errors_status(self):
        category_id = self._create_category()
        sku = f"IMP-CE-{_unique_suffix()}"
        product = self.client.post(
            "/products",
            json={
                "name": f"StatusCheck {sku}",
                "sku": sku,
                "categoryId": category_id,
                "brand": "StatusBrand",
                "unitPrice": 10,
                "costPrice": 5,
                "stockQuantity": 50,
                "unitOfMeasure": "piece",
            },
            headers=self.headers,
        )
        self.assertEqual(product.status_code, 200, product.text)

        email = f"status-{_unique_suffix()}@example.com"
        customer = self.client.post(
            "/customers",
            json={
                "name": f"Status Customer {_unique_suffix()}",
                "email": email,
                "phone": f"+1-555-700{_unique_suffix()[:4]}",
            },
            headers=self.headers,
        )
        self.assertEqual(customer.status_code, 200)

        invoice = f"IMP-CE-{_unique_suffix()}"
        csv_text = (
            "invoiceNumber,customerEmail,sku,quantity,unitPrice,saleDate,discountAmount,paymentMethod,paymentStatus\n"
            f"{invoice},{email},{sku},1,10,2026-01-15,99,Cash,Paid\n"
        )
        preview_response = self._upload_csv("sales", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["validRows"], 1)

        confirmed = self._confirm_import(preview["batchId"])
        self.assertEqual(confirmed["status"], "completed_with_errors")
        self.assertEqual(confirmed["insertedCount"], 0)
        self.assertEqual(confirmed["failedCount"], 1)

        detail_response = self.client.get(f"/imports/{preview['batchId']}", headers=self.headers)
        self.assertEqual(detail_response.status_code, 200)
        row_statuses = {row["status"] for row in detail_response.json()["rows"]}
        self.assertIn("failed", row_statuses)

        history_response = self.client.get("/imports", headers=self.headers)
        self.assertEqual(history_response.status_code, 200)
        batch_entry = next((item for item in history_response.json() if item["id"] == preview["batchId"]), None)
        self.assertIsNotNone(batch_entry)
        self.assertEqual(batch_entry["status"], "completed_with_errors")
        db = SessionLocal()
        try:
            self.assertEqual(
                db.query(Notification).filter(
                    Notification.alertKey == f"import:{preview['batchId']}:completed-with-errors"
                ).count(),
                1,
            )
        finally:
            db.close()

    def test_confirm_with_no_valid_rows_completes_cleanly(self):
        existing_email = f"novale-{_unique_suffix()}@example.com"
        create_existing = self.client.post(
            "/customers",
            json={
                "name": "No Valid Original",
                "email": existing_email,
                "phone": f"+1-555-600{_unique_suffix()[:4]}",
            },
            headers=self.headers,
        )
        self.assertEqual(create_existing.status_code, 200, create_existing.text)

        csv_text = (
            "name,email,phone\n"
            f"Clone One,{existing_email},+1-555-9990000\n"
            "Bad Row,not-an-email,+1-555-9990001\n"
            ",missing@example.com,+1-555-9990002\n"
        )
        preview_response = self._upload_csv("customers", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["validRows"], 0)

        confirmed = self._confirm_import(preview["batchId"])
        self.assertEqual(confirmed["status"], "completed")
        self.assertEqual(confirmed["insertedCount"], 0)
        self.assertEqual(confirmed["failedCount"], 0)
        self.assertEqual(confirmed["skippedCount"], confirmed["totalRows"])

        reconfirm = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(reconfirm.status_code, 400)

    def test_duplicate_detection_products_customers_and_sales(self):
        # Products: within-file SKU duplicates are flagged even when a later
        # occurrence carries its own validation errors.
        category_id = self._create_category()
        dup_sku = f"IMP-DP-{_unique_suffix()}"
        products_csv = (
            "sku,name,categoryName,unitPrice,stockQuantity\n"
            f"{dup_sku},First Product,{category_id},10,5\n"
            f"{dup_sku},Second Product,{category_id},oops,5\n"
            f"{dup_sku},Third Product,{category_id},12,7\n"
        )
        products_response = self._upload_csv("products", products_csv)
        self.assertEqual(products_response.status_code, 200, products_response.text)
        products_payload = products_response.json()
        self.assertEqual(products_payload["totalRows"], 3)
        self.assertEqual(products_payload["validRows"], 1)
        self.assertEqual(products_payload["duplicateRows"], 2)
        products_detail = self.client.get(f"/imports/{products_payload['batchId']}", headers=self.headers)
        self.assertEqual(products_detail.status_code, 200)
        duplicate_messages = [
            str(row.get("message") or "")
            for row in products_detail.json()["rows"]
            if row.get("status") == "duplicate"
        ]
        joined_messages = "; ".join(duplicate_messages).lower()
        self.assertIn("duplicate sku within file", joined_messages)

        # Customers: an existing phone number is a duplicate even with a new email.
        phone = f"+1-555-400{_unique_suffix()[:4]}"
        create_customer = self.client.post(
            "/customers",
            json={
                "name": "Phone Dup Original",
                "email": f"orig-{_unique_suffix()}@example.com",
                "phone": phone,
            },
            headers=self.headers,
        )
        self.assertEqual(create_customer.status_code, 200, create_customer.text)
        customers_csv = (
            "name,email,phone\n"
            f"Phone Dup Clone,clone-{_unique_suffix()}@example.com,{phone}\n"
        )
        customers_response = self._upload_csv("customers", customers_csv)
        self.assertEqual(customers_response.status_code, 200, customers_response.text)
        customers_payload = customers_response.json()
        self.assertEqual(customers_payload["totalRows"], 1)
        self.assertEqual(customers_payload["validRows"], 0)
        self.assertEqual(customers_payload["duplicateRows"], 1)

        # Sales: an invoice number already imported is flagged on the next upload.
        sku = f"IMP-DS-{_unique_suffix()}"
        product = self.client.post(
            "/products",
            json={
                "name": f"Dup Sale {sku}",
                "sku": sku,
                "categoryId": category_id,
                "brand": "DupBrand",
                "unitPrice": 10,
                "costPrice": 5,
                "stockQuantity": 100,
                "unitOfMeasure": "piece",
            },
            headers=self.headers,
        )
        self.assertEqual(product.status_code, 200, product.text)
        sales_email = f"dupsale-{_unique_suffix()}@example.com"
        sales_customer = self.client.post(
            "/customers",
            json={
                "name": f"Dup Sale Customer {_unique_suffix()}",
                "email": sales_email,
                "phone": f"+1-555-500{_unique_suffix()[:4]}",
            },
            headers=self.headers,
        )
        self.assertEqual(sales_customer.status_code, 200)

        invoice = f"IMP-INVDP-{_unique_suffix()}"
        sales_header = (
            "invoiceNumber,customerEmail,sku,quantity,unitPrice,saleDate,paymentMethod,paymentStatus\n"
        )
        first_upload = self._upload_csv(
            "sales", sales_header + f"{invoice},{sales_email},{sku},10,10,2026-01-15,Cash,Paid\n"
        )
        self.assertEqual(first_upload.status_code, 200, first_upload.text)
        first_payload = first_upload.json()
        self.assertEqual(first_payload["validRows"], 1)
        self.assertEqual(first_payload["duplicateRows"], 0)
        confirmed = self._confirm_import(first_payload["batchId"])
        self.assertEqual(confirmed["insertedCount"], 1)

        second_upload = self._upload_csv(
            "sales", sales_header + f"{invoice},{sales_email},{sku},4,10,2026-01-16,Cash,Paid\n"
        )
        self.assertEqual(second_upload.status_code, 200, second_upload.text)
        second_payload = second_upload.json()
        self.assertEqual(second_payload["totalRows"], 1)
        self.assertEqual(second_payload["validRows"], 0)
        self.assertEqual(second_payload["duplicateRows"], 1)
        second_detail = self.client.get(f"/imports/{second_payload['batchId']}", headers=self.headers)
        self.assertEqual(second_detail.status_code, 200)
        sale_duplicate_rows = [
            str(row.get("message") or "")
            for row in second_detail.json()["rows"]
            if row.get("status") == "duplicate"
        ]
        self.assertTrue(any("duplicate invoice number already exists" in message.lower() for message in sale_duplicate_rows))

    def test_missing_required_columns_rejected(self):
        cases = {
            "products": ("name,categoryName\nWidget,1\n", ["SKU"]),
            "customers": ("name,email\nJohn Doe,john@example.com\n", ["Phone"]),
            "sales": ("sku,quantity\nSKU-1,1\n", ["Customer Name", "Customer Email", "Unit Price", "Sale Date"]),
        }
        for entity_type, (csv_text, expected_labels) in cases.items():
            response = self._upload_csv(entity_type, csv_text)
            self.assertEqual(response.status_code, 400, f"{entity_type}: {response.text}")
            detail = response.json()["detail"]
            self.assertIn("missing required column", detail.lower())
            for label in expected_labels:
                self.assertIn(label, detail)

    def test_required_columns_accepted_via_aliases(self):
        category_id = self._create_category()
        sku = f"IMP-AL-{_unique_suffix()}"
        csv_text = (
            "Product Name,SKU Code,Category,Price,Qty\n"
            f"Alias Product,{sku},{category_id},15.5,7\n"
        )
        preview_response = self._upload_csv("products", csv_text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["validRows"], 1)

    def test_analyst_cannot_access_imports(self):
        login_response = self.client.post(
            "/auth/login",
            json={"email": "analyst@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login_response.status_code, 200)
        analyst_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        history_response = self.client.get("/imports", headers=analyst_headers)
        self.assertEqual(history_response.status_code, 403)

        upload_response = self._upload_csv_with(analyst_headers, "products", "sku,name\nA,B\n")
        self.assertEqual(upload_response.status_code, 403)

        export_response = self.client.get("/imports/1/failed-records", headers=analyst_headers)
        self.assertEqual(export_response.status_code, 403)

    def _upload_csv_with(self, headers, entity_type: str, csv_text: str):
        return self.client.post(
            f"/imports/{entity_type}/preview",
            content=csv_text,
            headers={**headers, "Content-Type": "text/csv"},
        )


if __name__ == "__main__":
    unittest.main()

