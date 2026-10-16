import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.controllers.system_health_controller import _classify_health_status
from backend.controllers.imports_controller import run_import_job
from backend.database import Base, SessionLocal
from backend.main import app
from backend.models import (
    ApiRequestMetric,
    ApiRequestMetricAggregate,
    AuditLog,
    HealthCheckResult,
    ImportBatch,
    ImportRecord,
    Notification,
    ReconciliationExecution,
    SystemError,
    SystemHealthThreshold,
    SystemIncidentEvent,
    SystemJob,
    User,
)
from backend.system_monitoring import (
    cleanup_monitoring_data,
    evaluate_api_thresholds,
    notify_system_incident,
    record_api_request,
    record_system_error,
)


class SystemHealthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()
        login = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        self.user = self.db.query(User).filter_by(email="admin@retailpulse.com").first()
        self.metric_ids = []
        self.aggregate_ids = []
        self.batch_ids = []
        self.import_record_ids = []
        self.reconciliation_ids = []
        self.job_ids = []
        self.system_error_ids = []
        self.incident_event_ids = []
        self.threshold_ids = []
        self.notification_ids = []
        self.audit_ids = []

    def tearDown(self):
        if self.metric_ids:
            self.db.query(ApiRequestMetric).filter(
                ApiRequestMetric.id.in_(self.metric_ids)
            ).delete(synchronize_session=False)
        if self.aggregate_ids:
            self.db.query(ApiRequestMetricAggregate).filter(
                ApiRequestMetricAggregate.id.in_(self.aggregate_ids)
            ).delete(synchronize_session=False)
        if self.batch_ids:
            self.db.query(ImportRecord).filter(
                ImportRecord.batchId.in_(self.batch_ids)
            ).delete(synchronize_session=False)
            self.db.query(ImportBatch).filter(
                ImportBatch.id.in_(self.batch_ids)
            ).delete(synchronize_session=False)
        if self.reconciliation_ids:
            self.db.query(ReconciliationExecution).filter(
                ReconciliationExecution.id.in_(self.reconciliation_ids)
            ).delete(synchronize_session=False)
        if self.job_ids:
            self.db.query(SystemJob).filter(
                SystemJob.id.in_(self.job_ids)
            ).delete(synchronize_session=False)
        if self.system_error_ids:
            event_ids = [
                row.id for row in self.db.query(SystemIncidentEvent.id).filter(
                    SystemIncidentEvent.systemErrorId.in_(self.system_error_ids)
                ).all()
            ]
            self.incident_event_ids.extend(event_ids)
            self.db.query(SystemIncidentEvent).filter(
                SystemIncidentEvent.systemErrorId.in_(self.system_error_ids)
            ).delete(synchronize_session=False)
            self.db.query(SystemError).filter(
                SystemError.id.in_(self.system_error_ids)
            ).delete(synchronize_session=False)
        if self.incident_event_ids:
            self.db.query(SystemIncidentEvent).filter(
                SystemIncidentEvent.id.in_(self.incident_event_ids)
            ).delete(synchronize_session=False)
        if self.threshold_ids:
            self.db.query(SystemHealthThreshold).filter(
                SystemHealthThreshold.id.in_(self.threshold_ids)
            ).delete(synchronize_session=False)
        if self.notification_ids:
            self.db.query(Notification).filter(
                Notification.id.in_(self.notification_ids)
            ).delete(synchronize_session=False)
        if self.audit_ids:
            self.db.query(AuditLog).filter(
                AuditLog.id.in_(self.audit_ids)
            ).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_admin_dashboard_includes_api_and_background_job_health(self):
        now = datetime.now(timezone.utc)
        metrics = [
            ApiRequestMetric(
                companyId=self.user.companyId,
                method="GET",
                path=f"/health-test/{uuid.uuid4().hex[:8]}",
                statusCode=503,
                responseTimeMs=1250,
                createdAt=now,
            ),
        ]
        self.db.add_all(metrics)
        self.db.flush()
        self.metric_ids.extend(metric.id for metric in metrics)
        expected_error_path = metrics[0].path

        batches = [
            ImportBatch(
                companyId=self.user.companyId,
                entityType="inventory",
                fileName=f"health-completed-{uuid.uuid4().hex[:8]}.csv",
                status="completed",
                importedBy=self.user.email,
                createdAt=now,
            ),
            ImportBatch(
                companyId=self.user.companyId,
                entityType="inventory",
                fileName=f"health-failed-{uuid.uuid4().hex[:8]}.csv",
                status="failed",
                failureMessage="Simulated import failure.",
                importedBy=self.user.email,
                createdAt=now,
            ),
            ImportBatch(
                companyId=self.user.companyId,
                entityType="inventory",
                fileName=f"health-queued-{uuid.uuid4().hex[:8]}.csv",
                status="queued",
                importedBy=self.user.email,
                createdAt=now,
            ),
            ImportBatch(
                companyId=self.user.companyId,
                entityType="inventory",
                fileName=f"health-processing-{uuid.uuid4().hex[:8]}.csv",
                status="processing",
                importedBy=self.user.email,
                createdAt=now,
            ),
        ]
        self.db.add_all(batches)
        self.db.flush()
        self.batch_ids.extend(batch.id for batch in batches)
        failed_reconciliation = ReconciliationExecution(
            companyId=self.user.companyId,
            startedAt=now,
            completedAt=now,
            triggeredByUserId=self.user.id,
            status="failed",
            errorMessage="Simulated reconciliation failure.",
        )
        self.db.add(failed_reconciliation)
        self.db.flush()
        self.reconciliation_ids.append(failed_reconciliation.id)
        self.db.commit()

        response = self.client.get("/system-health", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        health = response.json()
        self.assertIn(health["status"], {"healthy", "degraded", "unavailable"})
        self.assertGreaterEqual(health["failedApiRequests"], 1)
        self.assertGreaterEqual(health["averageResponseTimeMs"], 0)
        self.assertGreaterEqual(health["backgroundJobsCompleted"], 1)
        self.assertGreaterEqual(health["backgroundJobsFailed"], 1)
        self.assertGreaterEqual(health["activeJobs"], 1)
        self.assertGreaterEqual(health["pendingJobs"], 1)
        self.assertGreaterEqual(health["failedReconciliations"], 1)
        self.assertTrue(any(expected_error_path in error["message"] for error in health["recentErrors"]))
        self.assertTrue(any(error["source"] == "data_quality" for error in health["recentErrors"]))
        self.assertIsNotNone(health["lastHealthCheckAt"])
        self.assertIn("apiTrend", health)

    def test_system_health_requires_admin_authorization(self):
        self.assertEqual(self.client.get("/system-health").status_code, 401)
        analyst_login = self.client.post(
            "/auth/login",
            json={"email": "analyst@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(analyst_login.status_code, 200, analyst_login.text)
        analyst_headers = {"Authorization": f"Bearer {analyst_login.json()['access_token']}"}
        self.assertEqual(self.client.get("/system-health", headers=analyst_headers).status_code, 403)

    def test_public_api_health_reports_components_without_sensitive_details(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200, response.text)
        health = response.json()
        self.assertIn(health["status"], {"healthy", "degraded", "unavailable"})
        self.assertEqual(
            set(health["components"]),
            {
                "application_api",
                "database",
                "background_processing",
                "external_integrations",
            },
        )
        self.assertIn(
            health["components"]["database"]["status"],
            {"healthy", "unavailable"},
        )
        self.assertEqual(health["components"]["external_integrations"]["status"], "not_configured")
        serialized_health = response.text.lower()
        self.assertNotIn("password", serialized_health)
        self.assertNotIn("connectionstring", serialized_health)
        self.assertNotIn("traceback", serialized_health)
        saved_components = self.db.query(HealthCheckResult).filter(
            HealthCheckResult.companyId == 0,
        ).all()
        self.assertTrue(saved_components)
        self.assertTrue(all(component.checkedAt is not None for component in saved_components))

    def test_request_aggregation_counts_all_requests_but_samples_success_details(self):
        company_id = self.user.companyId + 800000
        now = datetime.now(timezone.utc)
        with patch("backend.system_monitoring.random.random", return_value=0.5):
            for _ in range(100):
                record_api_request(
                    self.db,
                    company_id=company_id,
                    method="GET",
                    path="/aggregate-test",
                    status_code=200,
                    response_time_ms=10,
                    error_details=None,
                    occurred_at=now,
                )
            for _ in range(2):
                record_api_request(
                    self.db,
                    company_id=company_id,
                    method="GET",
                    path="/aggregate-test",
                    status_code=400,
                    response_time_ms=20,
                    error_details="Client error",
                    occurred_at=now,
                )
        self.db.commit()

        aggregate = self.db.query(ApiRequestMetricAggregate).filter(
            ApiRequestMetricAggregate.companyId == company_id,
            ApiRequestMetricAggregate.path == "/aggregate-test",
        ).one()
        self.aggregate_ids.append(aggregate.id)
        sampled_records = self.db.query(ApiRequestMetric).filter(
            ApiRequestMetric.companyId == company_id,
            ApiRequestMetric.path == "/aggregate-test",
        ).all()
        self.metric_ids.extend(metric.id for metric in sampled_records)
        self.assertEqual(aggregate.requestCount, 102)
        self.assertEqual(aggregate.clientErrorCount, 2)
        self.assertEqual(aggregate.serverErrorCount, 0)
        self.assertAlmostEqual(aggregate.responseTimeTotalMs / aggregate.requestCount, 10.1960784, places=5)
        self.assertEqual(len(sampled_records), 2)

    def test_api_thresholds_use_aggregated_request_counts(self):
        company_id = self.user.companyId + 805000
        now = datetime.now(timezone.utc)
        threshold = SystemHealthThreshold(
            companyId=company_id,
            apiErrorRatePercent=50,
            averageResponseTimeMs=100000,
            sampleWindowMinutes=5,
            minimumRequestCount=2,
            repeatedFailureCount=3,
            updatedByUserId=self.user.id,
        )
        aggregate = ApiRequestMetricAggregate(
            companyId=company_id,
            bucketStart=now.replace(second=0, microsecond=0),
            method="GET",
            path="/aggregate-threshold-test",
            requestCount=10,
            clientErrorCount=0,
            serverErrorCount=5,
            responseTimeTotalMs=100,
            responseTimeMaxMs=20,
            updatedAt=now,
        )
        self.db.add_all([threshold, aggregate])
        self.db.flush()
        self.threshold_ids.append(threshold.id)
        self.aggregate_ids.append(aggregate.id)
        self.db.commit()

        evaluate_api_thresholds(self.db, company_id)

        issue = self.db.query(SystemError).filter_by(
            companyId=company_id,
            fingerprint="api:error-rate",
        ).one()
        self.system_error_ids.append(issue.id)
        notifications = self.db.query(Notification).filter(
            Notification.companyId == company_id,
            Notification.alertKey == f"system-incident:{issue.id}",
        ).all()
        self.notification_ids.extend(item.id for item in notifications)
        self.assertEqual(issue.category, "API error-rate threshold exceeded")

    def test_monitoring_retention_removes_expired_data_and_preserves_open_work(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=400)
        company_id = self.user.companyId + 810000
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        isolated_db = sessionmaker(bind=engine)()
        old_metric = ApiRequestMetric(
            companyId=company_id, method="GET", path="/expired", statusCode=200,
            responseTimeMs=1, createdAt=old,
        )
        old_aggregate = ApiRequestMetricAggregate(
            companyId=company_id, bucketStart=old, method="GET", path="/expired",
            requestCount=1, responseTimeTotalMs=1, responseTimeMaxMs=1, updatedAt=old,
        )
        expired_job = SystemJob(
            companyId=company_id, jobType="old job", status="completed",
            createdAt=old, completedAt=old, updatedAt=old,
        )
        active_job = SystemJob(
            companyId=company_id, jobType="active job", status="running",
            createdAt=old, startedAt=old, updatedAt=old,
        )
        resolved_incident = SystemError(
            companyId=company_id, fingerprint="retention:resolved",
            category="test", component="test", endpointOrJob="test",
            severity="low", status="resolved", firstOccurredAt=old,
            lastOccurredAt=old, resolvedAt=old,
        )
        open_incident = SystemError(
            companyId=company_id, fingerprint="retention:open",
            category="test", component="test", endpointOrJob="test",
            severity="low", status="open", firstOccurredAt=old, lastOccurredAt=old,
        )
        isolated_db.add_all([
            old_metric, old_aggregate, expired_job, active_job,
            resolved_incident, open_incident,
        ])
        isolated_db.flush()
        old_metric_id = old_metric.id
        old_aggregate_id = old_aggregate.id
        expired_job_id = expired_job.id
        active_job_id = active_job.id
        resolved_incident_id = resolved_incident.id
        open_incident_id = open_incident.id
        isolated_db.commit()

        try:
            cleanup_monitoring_data(isolated_db, force=True, now=now)

            self.assertIsNone(isolated_db.query(ApiRequestMetric).filter_by(id=old_metric_id).first())
            self.assertIsNone(isolated_db.query(ApiRequestMetricAggregate).filter_by(id=old_aggregate_id).first())
            self.assertIsNone(isolated_db.query(SystemJob).filter_by(id=expired_job_id).first())
            self.assertIsNotNone(isolated_db.query(SystemJob).filter_by(id=active_job_id).first())
            self.assertIsNone(isolated_db.query(SystemError).filter_by(id=resolved_incident_id).first())
            self.assertIsNotNone(isolated_db.query(SystemError).filter_by(id=open_incident_id).first())
        finally:
            isolated_db.close()
            engine.dispose()

    def test_safe_failed_import_retry_is_authorized_and_audited(self):
        now = datetime.now(timezone.utc)
        batch = ImportBatch(
            companyId=self.user.companyId,
            entityType="inventory",
            fileName="retry-safe.csv",
            totalRows=1,
            validCount=1,
            failedCount=1,
            processedCount=1,
            insertedCount=0,
            updatedCount=0,
            status="failed",
            importedBy=self.user.email,
            createdAt=now,
            completedAt=now,
        )
        self.db.add(batch)
        self.db.flush()
        record = ImportRecord(
            batchId=batch.id,
            companyId=self.user.companyId,
            rowNumber=1,
            rowData="{}",
            status="failed",
            message="Transient processing error",
        )
        failed_job = SystemJob(
            companyId=self.user.companyId,
            jobType="Data import (inventory)",
            triggeredByUserId=self.user.id,
            triggeredBy=self.user.name,
            relatedEntityType="ImportBatch",
            relatedEntityId=str(batch.id),
            status="failed",
            retryCount=0,
            createdAt=now,
            completedAt=now,
            details="{}",
        )
        self.db.add_all([record, failed_job])
        self.db.flush()
        batch_id = batch.id
        record_id = record.id
        failed_job_id = failed_job.id
        self.batch_ids.append(batch_id)
        self.import_record_ids.append(record_id)
        self.job_ids.append(failed_job_id)
        self.db.commit()

        with patch("backend.routers.system_health_routes.run_import_job") as enqueue:
            response = self.client.post(
                f"/system-health/jobs/{failed_job_id}/retry",
                headers=self.admin_headers,
            )
        self.assertEqual(response.status_code, 200, response.text)
        retry_job = response.json()
        self.assertEqual(retry_job["status"], "pending")
        self.assertEqual(retry_job["retryCount"], 1)
        self.assertFalse(retry_job["canRetry"])
        enqueue.assert_called_once_with(batch_id, self.user.id)
        self.db.refresh(batch)
        self.db.refresh(record)
        self.assertEqual(batch.status, "queued")
        self.assertEqual(record.status, "valid")
        retry_audit = self.db.query(AuditLog).filter(
            AuditLog.companyId == self.user.companyId,
            AuditLog.action == "Background Job Retry Requested",
            AuditLog.resourceId == str(retry_job["id"]),
        ).one()
        self.audit_ids.append(retry_audit.id)

    def test_failed_import_with_applied_rows_cannot_be_retried(self):
        now = datetime.now(timezone.utc)
        batch = ImportBatch(
            companyId=self.user.companyId,
            entityType="inventory",
            fileName="retry-unsafe.csv",
            totalRows=1,
            failedCount=1,
            insertedCount=1,
            updatedCount=0,
            status="failed",
            importedBy=self.user.email,
            createdAt=now,
            completedAt=now,
        )
        self.db.add(batch)
        self.db.flush()
        job = SystemJob(
            companyId=self.user.companyId,
            jobType="Data import (inventory)",
            triggeredByUserId=self.user.id,
            triggeredBy=self.user.name,
            relatedEntityType="ImportBatch",
            relatedEntityId=str(batch.id),
            status="failed",
            createdAt=now,
            completedAt=now,
            details="{}",
        )
        self.db.add(job)
        self.db.flush()
        batch_id, job_id = batch.id, job.id
        self.batch_ids.append(batch_id)
        self.job_ids.append(job_id)
        self.db.commit()

        response = self.client.post(
            f"/system-health/jobs/{job_id}/retry",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.db.refresh(batch)
        self.assertEqual(batch.status, "failed")

    def test_request_metrics_filters_sorting_and_pagination_are_company_scoped(self):
        now = datetime.now(timezone.utc)
        endpoint_path = f"/system-health-test/{uuid.uuid4().hex[:8]}"
        metrics = [
            ApiRequestMetric(
                companyId=self.user.companyId,
                method="GET",
                path=endpoint_path,
                statusCode=200,
                responseTimeMs=38.5,
                createdAt=now - timedelta(minutes=2),
            ),
            ApiRequestMetric(
                companyId=self.user.companyId,
                method="POST",
                path=endpoint_path,
                statusCode=422,
                responseTimeMs=61.25,
                errorDetails="Client error",
                createdAt=now,
            ),
            ApiRequestMetric(
                companyId=self.user.companyId + 100000,
                method="GET",
                path=endpoint_path,
                statusCode=500,
                responseTimeMs=999,
                errorDetails="Server error",
                createdAt=now,
            ),
        ]
        self.db.add_all(metrics)
        self.db.flush()
        self.metric_ids.extend(metric.id for metric in metrics)
        self.db.commit()

        response = self.client.get(
            "/system-health/requests",
            params={
                "endpoint": endpoint_path,
                "outcome": "failure",
                "status_code": 422,
                "start_time": (now - timedelta(minutes=1)).isoformat(),
                "end_time": (now + timedelta(minutes=1)).isoformat(),
                "sortBy": "responseTimeMs",
                "sortOrder": "desc",
                "page": 1,
                "pageSize": 1,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        page = response.json()
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["pageSize"], 1)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["statusCode"], 422)
        self.assertEqual(page["items"][0]["endpoint"], endpoint_path)
        self.assertFalse(page["items"][0]["isSuccess"])
        self.assertEqual(page["items"][0]["errorDetails"], "Client error")

    def test_middleware_records_safe_endpoint_metrics_for_authenticated_requests(self):
        response = self.client.get("/products/2147483647", headers=self.admin_headers)
        self.assertEqual(response.status_code, 404, response.text)
        metric = self.db.query(ApiRequestMetric).filter(
            ApiRequestMetric.companyId == self.user.companyId,
            ApiRequestMetric.path == "/products/{product_id}",
            ApiRequestMetric.method == "GET",
        ).order_by(ApiRequestMetric.id.desc()).first()
        self.assertIsNotNone(metric)
        self.metric_ids.append(metric.id)
        self.assertEqual(metric.statusCode, 404)
        self.assertGreaterEqual(metric.responseTimeMs, 0)
        self.assertEqual(metric.errorDetails, "Client error")

    def test_status_thresholds_are_explicit_and_stable(self):
        self.assertEqual(_classify_health_status(False, 100, 0, 0, 0), "unavailable")
        self.assertEqual(_classify_health_status(True, 94.99, 0, 0, 0), "unavailable")
        self.assertEqual(_classify_health_status(True, 95, 0, 0, 0), "degraded")
        self.assertEqual(_classify_health_status(True, 98.99, 0, 0, 0), "degraded")
        self.assertEqual(_classify_health_status(True, 99, 1000, 0, 0), "healthy")
        self.assertEqual(_classify_health_status(True, 99, 1000.01, 0, 0), "degraded")
        self.assertEqual(_classify_health_status(True, 99, 1000, 1, 0), "degraded")
        self.assertEqual(_classify_health_status(True, 99, 1000, 0, 1), "degraded")

    def test_job_listing_details_and_cancellation_are_company_scoped(self):
        batch = ImportBatch(
            companyId=self.user.companyId,
            entityType="inventory",
            fileName=f"monitor-{uuid.uuid4().hex[:8]}.csv",
            status="queued",
            importedBy=self.user.email,
            createdAt=datetime.now(timezone.utc),
        )
        self.db.add(batch)
        self.db.flush()
        job = SystemJob(
            companyId=self.user.companyId,
            jobType="Data import (inventory)",
            triggeredByUserId=self.user.id,
            triggeredBy=self.user.name,
            relatedEntityType="ImportBatch",
            relatedEntityId=str(batch.id),
            status="pending",
            details='{"totalRows":2}',
        )
        other_company_job = SystemJob(
            companyId=self.user.companyId + 100000,
            jobType="Hidden import",
            triggeredBy="Other company",
            relatedEntityType="ImportBatch",
            relatedEntityId="999999",
            status="pending",
            details="{}",
        )
        self.db.add_all([job, other_company_job])
        self.db.commit()
        self.job_ids.extend([job.id, other_company_job.id])
        self.batch_ids.append(batch.id)

        listed = self.client.get(
            "/system-health/jobs",
            params={"status": "pending", "page": 1, "pageSize": 10},
            headers=self.admin_headers,
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        jobs = listed.json()
        self.assertTrue(any(item["id"] == job.id for item in jobs["items"]))
        self.assertFalse(any(item["id"] == other_company_job.id for item in jobs["items"]))
        self.assertEqual(jobs["items"][0]["retryCount"], 0)
        self.assertFalse(jobs["items"][0]["canRetry"])

        detail = self.client.get(
            f"/system-health/jobs/{job.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["details"]["batchStatus"], "queued")

        denied = self.client.get(
            f"/system-health/jobs/{other_company_job.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(denied.status_code, 404)

        cancelled = self.client.post(
            f"/system-health/jobs/{job.id}/cancel",
            headers=self.admin_headers,
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.db.refresh(batch)
        self.assertEqual(batch.status, "cancelled")
        cancellation_audits = self.db.query(AuditLog.id).filter(
            AuditLog.companyId == self.user.companyId,
            AuditLog.action == "Background Job Cancellation Requested",
            AuditLog.resourceId == str(job.id),
        ).all()
        self.audit_ids.extend(row.id for row in cancellation_audits)
        self.assertTrue(cancellation_audits)

    def test_import_execution_is_recorded_as_a_background_job(self):
        existing_reconciliations = {
            row.id for row in self.db.query(ReconciliationExecution.id).filter(
                ReconciliationExecution.companyId == self.user.companyId
            ).all()
        }
        existing_jobs = {
            row.id for row in self.db.query(SystemJob.id).filter(
                SystemJob.companyId == self.user.companyId
            ).all()
        }
        batch = ImportBatch(
            companyId=self.user.companyId,
            entityType="inventory",
            fileName=f"empty-monitor-{uuid.uuid4().hex[:8]}.csv",
            status="queued",
            importedBy=self.user.email,
            totalRows=0,
            createdAt=datetime.now(timezone.utc),
        )
        self.db.add(batch)
        self.db.commit()
        self.batch_ids.append(batch.id)

        run_import_job(batch.id, self.user.id)

        job = self.db.query(SystemJob).filter(
            SystemJob.companyId == self.user.companyId,
            SystemJob.relatedEntityType == "ImportBatch",
            SystemJob.relatedEntityId == str(batch.id),
        ).order_by(SystemJob.id.desc()).first()
        self.assertIsNotNone(job)
        self.job_ids.append(job.id)
        self.assertEqual(job.status, "completed")
        self.assertIsNotNone(job.startedAt)
        self.assertIsNotNone(job.completedAt)
        self.assertEqual(job.retryCount, 0)
        new_reconciliation_ids = {
            row.id
            for row in self.db.query(ReconciliationExecution.id).filter(
                ReconciliationExecution.companyId == self.user.companyId
            ).all()
            if row.id not in existing_reconciliations
        }
        self.reconciliation_ids.extend(new_reconciliation_ids)
        self.job_ids.extend(
            row.id
            for row in self.db.query(SystemJob.id).filter(
                SystemJob.companyId == self.user.companyId
            ).all()
            if row.id not in existing_jobs and row.id != job.id
        )
        reconciliation_job = self.db.query(SystemJob).filter(
            SystemJob.companyId == self.user.companyId,
            SystemJob.relatedEntityType == "ReconciliationExecution",
            SystemJob.relatedEntityId.in_([str(row_id) for row_id in new_reconciliation_ids]),
        ).order_by(SystemJob.id.desc()).first()
        self.assertIsNotNone(reconciliation_job)
        self.assertEqual(reconciliation_job.status, "completed")

    def test_system_errors_group_occurrences_and_require_resolution_notes(self):
        fingerprint = f"api:GET:/monitor-test/{uuid.uuid4().hex[:8]}:500"
        first = record_system_error(
            self.db,
            company_id=self.user.companyId,
            fingerprint=fingerprint,
            category="API server error",
            component="Application API",
            endpoint_or_job="GET /monitor-test/{id}",
        )
        self.db.flush()
        self.system_error_ids.append(first.id)
        repeated = record_system_error(
            self.db,
            company_id=self.user.companyId,
            fingerprint=fingerprint,
            category="API server error",
            component="Application API",
            endpoint_or_job="GET /monitor-test/{id}",
        )
        self.db.commit()
        self.assertEqual(first.id, repeated.id)
        self.assertEqual(repeated.occurrenceCount, 2)
        foreign_error = record_system_error(
            self.db,
            company_id=self.user.companyId + 100000,
            fingerprint=f"foreign:{uuid.uuid4().hex}",
            category="Hidden error",
            component="Other company",
            endpoint_or_job="Hidden",
        )
        self.db.flush()
        self.system_error_ids.append(foreign_error.id)
        self.db.commit()

        listed = self.client.get(
            "/system-health/errors",
            params={"severity": "high", "component": "Application API", "status": "open"},
            headers=self.admin_headers,
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        item = next(error for error in listed.json()["items"] if error["id"] == first.id)
        self.assertEqual(item["occurrenceCount"], 2)
        self.assertNotIn("fingerprint", item)
        self.assertFalse(any(error["id"] == foreign_error.id for error in listed.json()["items"]))

        missing_notes = self.client.patch(
            f"/system-health/errors/{first.id}",
            json={"status": "resolved"},
            headers=self.admin_headers,
        )
        self.assertEqual(missing_notes.status_code, 422)
        resolved = self.client.patch(
            f"/system-health/errors/{first.id}",
            json={"status": "resolved", "resolutionNotes": "Restarted affected service."},
            headers=self.admin_headers,
        )
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["status"], "resolved")
        self.assertEqual(resolved.json()["resolutionNotes"], "Restarted affected service.")

    def test_incident_investigation_resolution_timeline_and_audit(self):
        issue = record_system_error(
            self.db,
            company_id=self.user.companyId,
            fingerprint=f"incident:{uuid.uuid4().hex}",
            category="Background job failure",
            component="Reconciliation",
            endpoint_or_job="Data reconciliation",
        )
        self.db.flush()
        self.system_error_ids.append(issue.id)
        notify_system_incident(self.db, issue, message="Reconciliation failure alert")
        self.db.commit()
        details = self.client.get(
            f"/system-health/errors/{issue.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(details.status_code, 200, details.text)
        self.assertEqual(details.json()["id"], issue.id)
        self.assertIsNotNone(details.json()["firstOccurredAt"])
        self.notification_ids.extend(
            row.id for row in self.db.query(Notification).filter(
                Notification.companyId == self.user.companyId,
                Notification.alertKey == f"system-incident:{issue.id}",
            ).all()
        )

        investigate = self.client.patch(
            f"/system-health/errors/{issue.id}",
            json={"status": "investigating", "investigationNotes": "Checking the failed source records."},
            headers=self.admin_headers,
        )
        self.assertEqual(investigate.status_code, 200, investigate.text)
        self.assertEqual(investigate.json()["status"], "investigating")

        resolve = self.client.patch(
            f"/system-health/errors/{issue.id}",
            json={"status": "resolved", "resolutionNotes": "Corrected the source data and reran checks."},
            headers=self.admin_headers,
        )
        self.assertEqual(resolve.status_code, 200, resolve.text)
        self.assertEqual(resolve.json()["status"], "resolved")

        timeline = self.client.get(
            f"/system-health/errors/{issue.id}/timeline",
            headers=self.admin_headers,
        )
        self.assertEqual(timeline.status_code, 200, timeline.text)
        events = timeline.json()
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[0]["action"], "incident_opened")
        self.assertEqual(events[-2]["newStatus"], "investigating")
        self.assertEqual(events[-2]["actorUserId"], self.user.id)
        self.assertIn("Checking the failed", events[-2]["notes"])
        self.assertEqual(events[-1]["newStatus"], "resolved")
        self.assertEqual(events[-1]["actorName"], self.user.name or self.user.email)

        self.db.refresh(issue)
        self.assertEqual(issue.resolvedByUserId, self.user.id)
        incident_events = self.db.query(SystemIncidentEvent.id).filter(
            SystemIncidentEvent.systemErrorId == issue.id
        ).all()
        self.incident_event_ids.extend(row.id for row in incident_events)
        audit_entries = self.db.query(AuditLog.id).filter(
            AuditLog.companyId == self.user.companyId,
            AuditLog.resourceType == "SystemError",
            AuditLog.resourceId == str(issue.id),
        ).all()
        self.audit_ids.extend(row.id for row in audit_entries)
        notifications = self.db.query(Notification).filter(
            Notification.companyId == self.user.companyId,
            Notification.alertKey == f"system-incident:{issue.id}",
        ).all()
        self.assertTrue(notifications)
        self.assertTrue(all(item.resolvedAt is not None for item in notifications))

    def test_threshold_configuration_is_company_scoped_and_audited(self):
        default_thresholds = self.client.get(
            "/system-health/thresholds",
            headers=self.admin_headers,
        )
        self.assertEqual(default_thresholds.status_code, 200, default_thresholds.text)
        self.assertEqual(default_thresholds.json()["apiErrorRatePercent"], 5.0)

        payload = {
            "apiErrorRatePercent": 7.5,
            "averageResponseTimeMs": 1800,
            "sampleWindowMinutes": 10,
            "minimumRequestCount": 20,
            "repeatedFailureCount": 4,
        }
        saved = self.client.put(
            "/system-health/thresholds",
            json=payload,
            headers=self.admin_headers,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["apiErrorRatePercent"], 7.5)
        self.assertEqual(saved.json()["updatedByUserId"], self.user.id)
        threshold = self.db.query(SystemHealthThreshold).filter(
            SystemHealthThreshold.companyId == self.user.companyId
        ).one()
        self.threshold_ids.append(threshold.id)
        audits = self.db.query(AuditLog.id).filter(
            AuditLog.companyId == self.user.companyId,
            AuditLog.action == "System Monitoring Thresholds Changed",
            AuditLog.resourceId == str(threshold.id),
        ).all()
        self.audit_ids.extend(row.id for row in audits)

    def test_threshold_alerts_deduplicate_and_recover(self):
        monitor_company_id = self.user.companyId + 900000
        threshold = SystemHealthThreshold(
            companyId=monitor_company_id,
            apiErrorRatePercent=50,
            averageResponseTimeMs=100000,
            sampleWindowMinutes=10,
            minimumRequestCount=2,
            repeatedFailureCount=3,
            updatedByUserId=self.user.id,
        )
        self.db.add(threshold)
        self.db.flush()
        self.threshold_ids.append(threshold.id)
        metrics = [
            ApiRequestMetric(
                companyId=monitor_company_id,
                method="GET",
                path="/threshold-alert-test",
                statusCode=500,
                responseTimeMs=20,
                createdAt=datetime.now(timezone.utc),
            )
            for _ in range(2)
        ]
        self.db.add_all(metrics)
        self.db.commit()
        self.metric_ids.extend(item.id for item in metrics)

        evaluate_api_thresholds(self.db, monitor_company_id)
        issue = self.db.query(SystemError).filter(
            SystemError.companyId == monitor_company_id,
            SystemError.fingerprint == "api:error-rate",
        ).one()
        self.system_error_ids.append(issue.id)
        notifications = self.db.query(Notification).filter(
            Notification.companyId == monitor_company_id,
            Notification.alertKey == f"system-incident:{issue.id}",
        ).all()
        self.assertEqual(len(notifications), 1)
        self.notification_ids.extend(item.id for item in notifications)

        evaluate_api_thresholds(self.db, monitor_company_id)
        self.db.refresh(issue)
        self.assertEqual(issue.occurrenceCount, 2)
        self.assertEqual(
            self.db.query(Notification.id).filter(
                Notification.companyId == monitor_company_id,
                Notification.alertKey == f"system-incident:{issue.id}",
            ).count(),
            1,
        )
        self.db.query(ApiRequestMetric).filter(
            ApiRequestMetric.id.in_([item.id for item in metrics])
        ).delete(synchronize_session=False)
        self.db.commit()
        evaluate_api_thresholds(self.db, monitor_company_id)
        self.db.refresh(issue)
        self.db.refresh(notifications[0])
        self.assertEqual(issue.status, "resolved")
        self.assertIsNotNone(notifications[0].resolvedAt)


if __name__ == "__main__":
    unittest.main()
