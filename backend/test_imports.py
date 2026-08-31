import time
import unittest
import uuid

from fastapi.testclient import TestClient

from backend.main import app


def _unique_suffix() -> str:
    return f"{uuid.uuid4().hex[:8]}{int(time.time() * 1000) % 100000}"


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
            f"SKU001,Laptop,{category_name},₹55,000,20\n"
            f"SKU002,Wireless Mouse, {category_name} , 1,200 ,100\n"
        )

        response = self._upload_csv("products", csv_text)
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual(preview["validRows"], 2)
        self.assertEqual(preview["invalidRows"], 0)
        self.assertEqual(preview["duplicateRows"], 0)
        self.assertEqual(preview["rows"][0]["data"]["categoryId"], category_id)

    def test_products_import_accepts_case_and_spacing_variations_for_category_names(self):
        category_name = "Electronics "
        category = self.client.post(
            "/categories",
            json={"name": category_name.strip(), "description": "Category name normalization test"},
            headers=self.headers,
        )
        self.assertEqual(category.status_code, 200, category.text)

        csv_text = (
            "SKU,Product Name,Category,Unit Price,Stock Quantity\n"
            "SKU555,Monitor, electronics , 2999, 12\n"
            "SKU556,Keyboard,Electronics, 699, 20\n"
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

        confirm_response = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        confirmed = confirm_response.json()
        self.assertEqual(confirmed["status"], "completed")
        self.assertEqual(confirmed["insertedCount"], 1)

        list_response = self.client.get(f"/products?q={new_sku}", headers=self.headers)
        self.assertEqual(list_response.status_code, 200)
        products = list_response.json()
        self.assertTrue(any(item["sku"] == new_sku and item["stockQuantity"] == 25 for item in products))

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

        confirm_response = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        confirmed = confirm_response.json()
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

        confirm_response = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        confirmed = confirm_response.json()
        self.assertEqual(confirmed["insertedCount"], 1)
        self.assertEqual(confirmed["failedCount"], 0)

        sales_list = self.client.get("/sales/list", headers=self.headers)
        self.assertEqual(sales_list.status_code, 200)
        transactions = [
            item
            for item in sales_list.json().get("transactions", sales_list.json())
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

        confirm_response = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        confirmed = confirm_response.json()
        self.assertEqual(confirmed["insertedCount"], 2)
        self.assertEqual(confirmed["failedCount"], 0)

        sales_list = self.client.get("/sales/list", headers=self.headers)
        self.assertEqual(sales_list.status_code, 200)
        transactions = sales_list.json().get("transactions", sales_list.json())
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
        self.assertTrue(lines[0].startswith("RowNumber,Status,Errors,"))
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

        confirm_response = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        confirmed = confirm_response.json()
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

        confirm_response = self.client.post(f"/imports/{preview['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        confirmed = confirm_response.json()
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
        confirm_response = self.client.post(f"/imports/{first_payload['batchId']}/confirm", headers=self.headers)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        self.assertEqual(confirm_response.json()["insertedCount"], 1)

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

