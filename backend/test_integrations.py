import hashlib
import json
import unittest
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.controllers.integrations_controller import _next_schedule_at, _notify_sync_outcome
from backend.main import app
from backend.integration_secrets import decrypt_credentials
from backend.integration_secrets import decrypt_source_data
from backend.integration_scheduler import process_due_csv_integrations
from backend.models import (
    AuditLog,
    Category,
    Customer,
    ImportBatch,
    ImportRecord,
    IntegrationConnector,
    IntegrationSyncRun,
    Notification,
    Product,
    QualityIssue,
    ReconciliationExecution,
    StockAdjustment,
    StockMovement,
    SystemJob,
    User,
)


class IntegrationDashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.extra_connector_ids = []
        self.sync_run_ids = []
        self.import_batch_ids = []
        self.customer_emails = []
        self.product_skus = []
        self.test_started_at = datetime.now(timezone.utc)
        login = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        self.user = self.db.query(User).filter_by(email="admin@retailpulse.com").first()
        suffix = uuid.uuid4().hex
        self.connectors = [
            IntegrationConnector(
                companyId=self.user.companyId,
                name=f"Dashboard integration {suffix}",
                dataSourceType="csv",
                connectionConfiguration='{"mode":"upload"}',
                authenticationMethod="none",
                targetModule="products",
                syncFrequency="manual",
                status="active",
                createdByUserId=self.user.id,
            ),
            IntegrationConnector(
                companyId=self.user.companyId,
                name=f"Failed integration {suffix}",
                dataSourceType="rest_api",
                connectionConfiguration='{"baseUrl":"https://example.test"}',
                authenticationMethod="none",
                targetModule="products",
                syncFrequency="hourly",
                status="failed",
                createdByUserId=self.user.id,
            ),
            IntegrationConnector(
                companyId=(self.user.companyId or 0) + 100000,
                name=f"Other company integration {suffix}",
                dataSourceType="csv",
                connectionConfiguration='{"mode":"upload"}',
                authenticationMethod="none",
                targetModule="products",
                syncFrequency="manual",
                status="active",
                createdByUserId=self.user.id,
            ),
        ]
        self.db.add_all(self.connectors)
        self.db.flush()
        self.runs = [
            IntegrationSyncRun(
                companyId=self.user.companyId,
                connectorId=self.connectors[0].id,
                status="completed",
                recordsSynced=7,
                recordsFailed=2,
            ),
            IntegrationSyncRun(
                companyId=self.user.companyId,
                connectorId=self.connectors[0].id,
                status="running",
                recordsSynced=0,
                recordsFailed=0,
            ),
            IntegrationSyncRun(
                companyId=self.connectors[2].companyId,
                connectorId=self.connectors[2].id,
                status="completed",
                recordsSynced=900,
                recordsFailed=900,
            ),
        ]
        self.db.add_all(self.runs)
        self.db.commit()

    def tearDown(self):
        connector_ids = [connector.id for connector in self.connectors]
        all_connector_ids = connector_ids + self.extra_connector_ids
        run_ids = [
            str(row[0])
            for row in self.db.query(IntegrationSyncRun.id).filter(
                IntegrationSyncRun.connectorId.in_(all_connector_ids),
            ).all()
        ]
        if run_ids:
            self.db.query(Notification).filter(
                Notification.resourceType == "IntegrationSyncRun",
                Notification.resourceId.in_(run_ids),
            ).delete(synchronize_session=False)
        self.db.query(IntegrationSyncRun).filter(
            IntegrationSyncRun.connectorId.in_(connector_ids),
        ).delete(synchronize_session=False)
        if self.sync_run_ids:
            self.db.query(Notification).filter(
                Notification.resourceType == "IntegrationSyncRun",
                Notification.resourceId.in_([str(run_id) for run_id in self.sync_run_ids]),
            ).delete(synchronize_session=False)
        if self.import_batch_ids:
            batch_values = [str(batch_id) for batch_id in self.import_batch_ids]
            self.db.query(SystemJob).filter(
                SystemJob.relatedEntityType == "ImportBatch",
                SystemJob.relatedEntityId.in_(batch_values),
            ).delete(synchronize_session=False)
            self.db.query(ImportRecord).filter(
                ImportRecord.batchId.in_(self.import_batch_ids),
            ).delete(synchronize_session=False)
            self.db.query(Notification).filter(
                Notification.resourceType == "Import",
                Notification.resourceId.in_(batch_values),
            ).delete(synchronize_session=False)
            self.db.query(AuditLog).filter(
                AuditLog.resourceType == "Import",
                AuditLog.resourceId.in_(batch_values),
            ).delete(synchronize_session=False)
            self.db.query(ImportBatch).filter(
                ImportBatch.id.in_(self.import_batch_ids),
            ).delete(synchronize_session=False)
        if self.customer_emails:
            imported_customers = self.db.query(Customer).filter(
                Customer.companyId == self.user.companyId,
                Customer.email.in_(self.customer_emails),
            ).all()
            customer_ids = [str(customer.id) for customer in imported_customers]
            if customer_ids:
                self.db.query(QualityIssue).filter(
                    QualityIssue.companyId == self.user.companyId,
                    QualityIssue.affectedRecordType == "Customer",
                    QualityIssue.affectedRecordId.in_(customer_ids),
                ).delete(synchronize_session=False)
            self.db.query(Customer).filter(
                Customer.companyId == self.user.companyId,
                Customer.email.in_(self.customer_emails),
            ).delete(synchronize_session=False)
        if self.product_skus:
            products = self.db.query(Product).filter(
                Product.companyId == self.user.companyId,
                Product.sku.in_(self.product_skus),
            ).all()
            product_ids = [product.id for product in products]
            if product_ids:
                self.db.query(StockAdjustment).filter(
                    StockAdjustment.companyId == self.user.companyId,
                    StockAdjustment.productId.in_(product_ids),
                    StockAdjustment.reason == "Integration update",
                ).delete(synchronize_session=False)
                self.db.query(StockMovement).filter(
                    StockMovement.companyId == self.user.companyId,
                    StockMovement.productId.in_(product_ids),
                    StockMovement.movementType == "Integration Update",
                ).delete(synchronize_session=False)
            self.db.query(Product).filter(
                Product.companyId == self.user.companyId,
                Product.sku.in_(self.product_skus),
            ).delete(synchronize_session=False)
        self.db.query(ReconciliationExecution).filter(
            ReconciliationExecution.companyId == self.user.companyId,
            ReconciliationExecution.triggeredByUserId == self.user.id,
            ReconciliationExecution.startedAt >= self.test_started_at,
        ).delete(synchronize_session=False)
        self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Integration",
            AuditLog.resourceId.in_([str(connector_id) for connector_id in all_connector_ids]),
        ).delete(synchronize_session=False)
        self.db.query(IntegrationConnector).filter(
            IntegrationConnector.id.in_(all_connector_ids),
        ).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def clear_running_fixture(self, connector_id: int) -> None:
        self.db.query(IntegrationSyncRun).filter(
            IntegrationSyncRun.connectorId == connector_id,
            IntegrationSyncRun.status == "running",
        ).delete(synchronize_session=False)
        self.db.commit()

    def test_dashboard_returns_company_scoped_connector_and_sync_metrics(self):
        response = self.client.get("/integrations/dashboard", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()

        self.assertEqual(result["totalIntegrations"], 2)
        self.assertEqual(result["activeIntegrations"], 1)
        self.assertEqual(result["failedIntegrations"], 1)
        self.assertEqual(result["pendingSyncJobs"], 1)
        self.assertEqual(result["recordsSynced"], 7)
        self.assertEqual(result["recordsFailed"], 2)
        self.assertEqual(
            {item["name"] for item in result["integrations"]},
            {connector.name for connector in self.connectors[:2]},
        )
        self.assertTrue(result["integrations"][0]["isOperational"])
        self.assertFalse(result["integrations"][1]["isOperational"])

    def test_integration_list_and_connector_history_are_company_scoped(self):
        response = self.client.get("/integrations", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 2)
        self.assertNotIn(self.connectors[2].id, {item["id"] for item in response.json()})

        cross_company = self.client.get(
            f"/integrations/{self.connectors[2].id}/sync-runs",
            headers=self.headers,
        )
        self.assertEqual(cross_company.status_code, 200, cross_company.text)
        self.assertEqual(cross_company.json()["total"], 0)

    def test_field_mapping_and_schedule_management_apis_validate_and_persist(self):
        connector = self.connectors[0]
        self.clear_running_fixture(connector.id)
        mapping = {
            "sku": "sku",
            "title": "name",
            "category": "categoryname",
            "price": "unitprice",
            "stock": "stockquantity",
        }
        response = self.client.put(
            f"/integrations/{connector.id}/field-mapping",
            headers=self.headers,
            json={"fieldMappings": mapping},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["fieldMappings"], mapping)

        invalid = self.client.put(
            f"/integrations/{connector.id}/field-mapping",
            headers=self.headers,
            json={"fieldMappings": {"sku": "sku"}},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)

        schedule = self.client.put(
            f"/integrations/{connector.id}/schedule",
            headers=self.headers,
            json={
                "syncFrequency": "weekly",
                "scheduleEnabled": True,
                "scheduleTime": "08:45",
                "scheduleDay": 4,
            },
        )
        self.assertEqual(schedule.status_code, 200, schedule.text)
        self.assertTrue(schedule.json()["scheduleEnabled"])
        self.assertEqual(schedule.json()["scheduleTime"], "08:45")
        self.assertEqual(schedule.json()["scheduleDay"], 4)

        disabled = self.client.put(
            f"/integrations/{connector.id}/schedule",
            headers=self.headers,
            json={"syncFrequency": "weekly", "scheduleEnabled": False, "scheduleTime": "08:45", "scheduleDay": 4},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertFalse(disabled.json()["scheduleEnabled"])

    def test_schedule_api_rejects_cross_company_connector(self):
        response = self.client.put(
            f"/integrations/{self.connectors[2].id}/schedule",
            headers=self.headers,
            json={"syncFrequency": "daily", "scheduleEnabled": True, "scheduleTime": "08:45"},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_connector_configuration_encrypts_credentials_and_never_returns_them(self):
        secret = f"password-{uuid.uuid4().hex}"
        response = self.client.post(
            "/integrations",
            headers=self.headers,
            json={
                "name": f"PostgreSQL {uuid.uuid4().hex}",
                "dataSourceType": "postgresql",
                "connectionConfiguration": {
                    "host": "db.example.test",
                    "port": 5432,
                    "database": "retail",
                    "table": "products",
                    "username": "integration-user",
                },
                "authenticationMethod": "password",
                "credentials": {"password": secret},
                "targetModule": "products",
                "syncFrequency": "hourly",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        connector_id = response.json()["id"]
        self.extra_connector_ids.append(connector_id)
        self.assertTrue(response.json()["hasCredentials"])
        self.assertNotIn(secret, response.text)
        connector = self.db.query(IntegrationConnector).filter_by(id=connector_id).first()
        self.assertNotIn(secret, connector.encryptedCredentials)
        self.assertEqual(decrypt_credentials(connector.encryptedCredentials), {"password": secret})
        detail = self.client.get(f"/integrations/{connector_id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertNotIn(secret, detail.text)
        self.assertNotIn("encryptedCredentials", detail.text)
        self.assertNotIn("credentialsConfigured", detail.text)

    def test_non_operational_connector_rejects_sync(self):
        connector = self.connectors[1]
        response = self.client.post(
            f"/integrations/{connector.id}/sync",
            headers={**self.headers, "Content-Type": "text/csv"},
            content=b"sku,name\nSKU-1,Test product\n",
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_csv_connection_test_does_not_create_import_or_sync_run(self):
        batches_before = self.db.query(ImportBatch).count()
        runs_before = self.db.query(IntegrationSyncRun).count()
        response = self.client.post(
            "/integrations/test-connection",
            headers=self.headers,
            json={
                "dataSourceType": "csv",
                "connectionConfiguration": {"mode": "upload"},
                "authenticationMethod": "none",
                "targetModule": "products",
                "syncFrequency": "manual",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["success"])
        self.assertEqual(self.db.query(ImportBatch).count(), batches_before)
        self.assertEqual(self.db.query(IntegrationSyncRun).count(), runs_before)

    def test_csv_sync_rejects_missing_required_field_mapping(self):
        self.clear_running_fixture(self.connectors[0].id)
        response = self.client.post(
            f"/integrations/{self.connectors[0].id}/sync",
            headers={
                **self.headers,
                "Content-Type": "text/csv",
                "X-Field-Mapping": json.dumps({"external_sku": "sku"}),
            },
            content=b"external_sku,external_title\nSKU-1,Widget\n",
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("Required RetailPulse fields are not mapped", response.json()["detail"])

    def test_connection_test_rejects_incomplete_postgresql_configuration_without_network_access(self):
        response = self.client.post(
            "/integrations/test-connection",
            headers=self.headers,
            json={
                "dataSourceType": "postgresql",
                "connectionConfiguration": {
                    "host": "127.0.0.1",
                    "database": "retail",
                },
                "authenticationMethod": "none",
                "targetModule": "products",
                "syncFrequency": "manual",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("table is required", response.text)

    def test_repeated_csv_payload_is_rejected_for_idempotency(self):
        connector = self.connectors[0]
        self.clear_running_fixture(connector.id)
        content = b"sku,name\nSKU-2,Another product\n"
        self.db.add(IntegrationSyncRun(
            companyId=self.user.companyId,
            connectorId=connector.id,
            sourceHash=hashlib.sha256(content).hexdigest(),
            status="completed",
        ))
        self.db.commit()
        response = self.client.post(
            f"/integrations/{connector.id}/sync",
            params={"fileName": "records.csv"},
            headers={**self.headers, "Content-Type": "text/csv"},
            content=content,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("already been submitted", response.json()["detail"])

    def test_csv_connector_uses_import_pipeline_end_to_end(self):
        connector = self.connectors[0]
        self.clear_running_fixture(connector.id)
        connector.targetModule = "customers"
        connector.syncFrequency = "hourly"
        connector.scheduleEnabled = True
        self.db.commit()
        suffix = uuid.uuid4().int % 10_000_000_000
        email = f"integration-{suffix}@example.test"
        self.customer_emails.append(email)
        content = (
            "customer_fullname,mail_address,mobile_no,city,country,segment,status\n"
            f"Integration Customer {suffix},{email},{suffix:010d},Seattle,USA,retail,active\n"
        ).encode("utf-8")

        response = self.client.post(
            f"/integrations/{connector.id}/sync",
            params={"fileName": "customers.csv"},
            headers={
                **self.headers,
                "Content-Type": "text/csv",
                "X-Field-Mapping": json.dumps({
                    "customer_fullname": "name",
                    "mail_address": "email",
                    "mobile_no": "phone",
                    "city": "city",
                    "country": "country",
                    "segment": "customertype",
                    "status": "status",
                }),
            },
            content=content,
        )
        self.assertEqual(response.status_code, 202, response.text)
        result = response.json()
        self.import_batch_ids.append(result["importBatchId"])
        self.sync_run_ids.append(result["syncRunId"])
        self.assertEqual(result["validRows"], 1)

        self.db.expire_all()
        sync_run = self.db.query(IntegrationSyncRun).filter_by(id=result["syncRunId"]).first()
        batch = self.db.query(ImportBatch).filter_by(id=result["importBatchId"]).first()
        self.assertEqual(sync_run.status, "completed")
        self.assertEqual(sync_run.recordsSynced, 1)
        self.assertEqual(sync_run.recordsInserted, 1)
        self.assertEqual(sync_run.recordsUpdated, 0)
        self.assertEqual(batch.status, "completed")
        self.assertIsNotNone(self.db.query(Customer).filter_by(email=email).first())
        stored_connector = self.db.query(IntegrationConnector).filter_by(id=connector.id).first()
        self.assertEqual(json.loads(stored_connector.connectionConfiguration)["fieldMappings"]["customer_fullname"], "name")
        self.assertNotIn(email, stored_connector.encryptedSourceData)
        self.assertEqual(decrypt_source_data(stored_connector.encryptedSourceData), content)
        self.assertIsNotNone(stored_connector.nextSyncAt)

        history = self.client.get("/integrations/sync-runs?limit=10", headers=self.headers)
        self.assertEqual(history.status_code, 200, history.text)
        manual_run = next(item for item in history.json()["items"] if item["id"] == result["syncRunId"])
        self.assertEqual(manual_run["recordsProcessed"], 1)
        self.assertEqual(manual_run["recordsInserted"], 1)
        integration_audits = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Integration",
            AuditLog.resourceId == str(connector.id),
        ).all()
        actions = {entry.action for entry in integration_audits}
        self.assertIn("Integration Sync Started", actions)
        self.assertIn("Integration Sync Completed", actions)
        self.assertTrue(all(entry.userId == self.user.id and entry.timestamp is not None for entry in integration_audits))

        stored_connector.nextSyncAt = datetime.now(timezone.utc)
        self.db.commit()
        process_due_csv_integrations()
        self.db.expire_all()
        scheduled_run = self.db.query(IntegrationSyncRun).filter(
            IntegrationSyncRun.connectorId == connector.id,
            IntegrationSyncRun.triggerType == "scheduled",
        ).order_by(IntegrationSyncRun.id.desc()).first()
        self.assertIsNotNone(scheduled_run)
        self.assertEqual(scheduled_run.syncMode, "incremental")
        self.assertEqual(scheduled_run.recordsSkipped, 1)
        scheduled_alert = self.db.query(Notification).filter_by(
            alertKey=f"integration-sync:{scheduled_run.id}:completed",
        ).first()
        self.assertIsNotNone(scheduled_alert)
        if scheduled_run.importBatchId:
            self.import_batch_ids.append(scheduled_run.importBatchId)
        detail = self.client.get(f"/integrations/sync-runs/{scheduled_run.id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["importSummary"]["fileName"], "customers.csv")

    def test_product_duplicate_strategy_updates_only_mapped_fields(self):
        connector = self.connectors[0]
        self.clear_running_fixture(connector.id)
        category = self.db.query(Category).filter_by(companyId=self.user.companyId).first()
        self.assertIsNotNone(category)
        sku = f"SYNC-{uuid.uuid4().hex[:12].upper()}"
        self.product_skus.append(sku)
        product = Product(
            companyId=self.user.companyId,
            categoryId=category.id,
            sku=sku,
            name="Before sync",
            brand="Preserve me",
            unitPrice=10,
            costPrice=2,
            stockQuantity=3,
            initialStockQuantity=3,
            maxStockLevel=20,
            unitOfMeasure="piece",
            status="active",
        )
        self.db.add(product)
        connector.targetModule = "products"
        connector.duplicateStrategy = "update"
        self.db.commit()
        content = f"sku,name,categoryname,unitprice,stockquantity\n{sku},After sync,{category.name},12,5\n".encode()
        response = self.client.post(
            f"/integrations/{connector.id}/sync?fileName=products.csv",
            headers={**self.headers, "Content-Type": "text/csv"},
            content=content,
        )
        self.assertEqual(response.status_code, 202, response.text)
        self.sync_run_ids.append(response.json()["syncRunId"])
        self.import_batch_ids.append(response.json()["importBatchId"])
        product = self.db.query(Product).filter_by(companyId=self.user.companyId, sku=sku).first()
        self.assertEqual(product.name, "After sync")
        self.assertEqual(product.unitPrice, 12)
        self.assertEqual(product.stockQuantity, 5)
        self.assertEqual(product.brand, "Preserve me")
        run = self.db.query(IntegrationSyncRun).filter_by(id=response.json()["syncRunId"]).first()
        self.assertEqual(run.recordsUpdated, 1)
        self.assertEqual(run.recordsInserted, 0)

    def test_dashboard_requires_authenticated_user(self):
        response = self.client.get("/integrations/dashboard")
        self.assertEqual(response.status_code, 401, response.text)

    def test_schedule_time_calculation_uses_utc_and_weekday(self):
        after = datetime(2026, 6, 1, 8, 30, tzinfo=timezone.utc)
        self.assertEqual(
            _next_schedule_at("daily", "09:15", None, after),
            datetime(2026, 6, 1, 9, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(
            _next_schedule_at("weekly", "09:15", 2, after),
            datetime(2026, 6, 3, 9, 15, tzinfo=timezone.utc),
        )

    def test_sync_outcome_notifications_are_deduplicated_per_run(self):
        run = IntegrationSyncRun(
            companyId=self.user.companyId,
            connectorId=self.connectors[0].id,
            status="completed",
        )
        self.db.add(run)
        self.db.flush()
        _notify_sync_outcome(self.db, run, self.connectors[0])
        _notify_sync_outcome(self.db, run, self.connectors[0])
        self.db.flush()
        matching = self.db.query(Notification).filter_by(
            alertKey=f"integration-sync:{run.id}:completed",
        ).all()
        self.assertEqual(len(matching), 1)

    def test_connection_test_and_status_change_are_audited(self):
        connector = self.connectors[0]
        self.clear_running_fixture(connector.id)
        tested = self.client.post(
            "/integrations/test-connection",
            headers=self.headers,
            json={
                "connectorId": connector.id,
                "dataSourceType": "csv",
                "connectionConfiguration": {"mode": "upload"},
                "authenticationMethod": "none",
                "targetModule": "products",
                "syncFrequency": "manual",
            },
        )
        self.assertEqual(tested.status_code, 200, tested.text)
        updated = self.client.patch(
            f"/integrations/{connector.id}",
            headers=self.headers,
            json={"status": "inactive"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        actions = {
            entry.action
            for entry in self.db.query(AuditLog).filter(
                AuditLog.resourceType == "Integration",
                AuditLog.resourceId == str(connector.id),
            ).all()
        }
        self.assertIn("Integration Connection Tested", actions)
        self.assertIn("Integration Disabled", actions)

    def test_failed_record_export_and_retry_include_only_failed_rows(self):
        connector = self.connectors[0]
        self.clear_running_fixture(connector.id)
        category = self.db.query(Category).filter_by(companyId=self.user.companyId).first()
        self.assertIsNotNone(category)
        sku = f"RETRY-{uuid.uuid4().hex[:12].upper()}"
        self.product_skus.append(sku)
        batch = ImportBatch(
            companyId=self.user.companyId,
            entityType="products",
            fileName="integration-errors.csv",
            totalRows=2,
            validCount=0,
            invalidCount=0,
            duplicateCount=0,
            failedCount=1,
            status="completed_with_errors",
            importedBy=self.user.email,
        )
        self.db.add(batch)
        self.db.flush()
        resolved = {
            "sku": sku,
            "name": "Retry Product",
            "categoryname": category.name,
            "unitprice": "5",
            "stockquantity": "2",
        }
        self.db.add_all([
            ImportRecord(
                batchId=batch.id,
                companyId=self.user.companyId,
                rowNumber=2,
                status="failed",
                message="Temporary processing failure",
                rowData=json.dumps({"row": resolved, "resolved": resolved}),
            ),
            ImportRecord(
                batchId=batch.id,
                companyId=self.user.companyId,
                rowNumber=3,
                status="imported",
                rowData=json.dumps({"row": {"sku": "already-imported"}, "resolved": {}}),
            ),
        ])
        run = IntegrationSyncRun(
            companyId=self.user.companyId,
            connectorId=connector.id,
            importBatchId=batch.id,
            triggeredByUserId=self.user.id,
            triggerType="manual",
            syncMode="incremental",
            status="completed_with_errors",
            recordsProcessed=2,
            recordsFailed=1,
        )
        self.db.add(run)
        self.db.commit()
        self.import_batch_ids.append(batch.id)
        self.sync_run_ids.append(run.id)

        errors = self.client.get(f"/integrations/sync-runs/{run.id}/errors", headers=self.headers)
        self.assertEqual(errors.status_code, 200, errors.text)
        self.assertEqual(errors.json()["total"], 1)
        self.assertEqual(errors.json()["items"][0]["sourceRecordIdentifier"], sku)
        self.assertNotIn("rowData", errors.text)
        export = self.client.get(f"/integrations/sync-runs/{run.id}/errors/export", headers=self.headers)
        self.assertEqual(export.status_code, 200, export.text)
        self.assertIn("Temporary processing failure", export.text)

        retry = self.client.post(f"/integrations/sync-runs/{run.id}/retry", headers=self.headers)
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json()["retriedRecords"], 1)
        self.import_batch_ids.append(retry.json()["importBatchId"])
        self.sync_run_ids.append(retry.json()["syncRunId"])
        retried_batch = self.db.query(ImportBatch).filter_by(id=retry.json()["importBatchId"]).first()
        self.assertEqual(retried_batch.totalRows, 1)


if __name__ == "__main__":
    unittest.main()
