import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, text

from backend.auth_utils import get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, create_audit_log
from backend.models import (
    ApiRequestMetric,
    ApiRequestMetricAggregate,
    ImportBatch,
    ImportRecord,
    ReconciliationExecution,
    ReportHistory,
    SystemError,
    SystemHealthThreshold,
    SystemIncidentEvent,
    SystemJob,
    User,
)
from backend.system_monitoring import (
    cleanup_monitoring_data,
    default_system_health_thresholds,
    get_or_create_system_health_threshold,
    notify_system_incident,
    recover_system_incident,
    record_system_error,
    record_health_check_results,
    transition_system_incident,
)

ADMIN_ROLES = {"admin", "company_admin", "super_admin"}
WINDOW_HOURS = 24
RECENT_ERROR_LIMIT = 20


def _classify_health_status(
    database_available: bool,
    api_availability_percent: float,
    average_response_time_ms: float,
    failed_jobs: int,
    failed_reconciliations: int,
) -> str:
    if not database_available or api_availability_percent < 95:
        return "unavailable"
    if (
        api_availability_percent < 99
        or average_response_time_ms > 1000
        or failed_jobs > 0
        or failed_reconciliations > 0
    ):
        return "degraded"
    return "healthy"


def get_system_health(db: DbDependency, authorization: str | None) -> dict:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_admin(user)

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=WINDOW_HOURS)
    metrics_query = db.query(ApiRequestMetric).filter(
        ApiRequestMetric.companyId == user.companyId,
        ApiRequestMetric.createdAt >= window_start,
    )
    aggregate_query = db.query(
        func.sum(ApiRequestMetricAggregate.requestCount),
        func.sum(ApiRequestMetricAggregate.clientErrorCount),
        func.sum(ApiRequestMetricAggregate.serverErrorCount),
        func.sum(ApiRequestMetricAggregate.responseTimeTotalMs),
    ).filter(
        ApiRequestMetricAggregate.companyId == user.companyId,
        ApiRequestMetricAggregate.bucketStart >= window_start.replace(second=0, microsecond=0),
    )
    aggregate_totals = aggregate_query.one()
    trend_rows = db.query(
        ApiRequestMetricAggregate.bucketStart,
        func.sum(ApiRequestMetricAggregate.requestCount),
        func.sum(ApiRequestMetricAggregate.serverErrorCount),
        func.sum(ApiRequestMetricAggregate.responseTimeTotalMs),
    ).filter(
        ApiRequestMetricAggregate.companyId == user.companyId,
        ApiRequestMetricAggregate.bucketStart >= window_start.replace(second=0, microsecond=0),
    ).group_by(
        ApiRequestMetricAggregate.bucketStart
    ).order_by(ApiRequestMetricAggregate.bucketStart.asc()).all()
    legacy_total_requests = metrics_query.count()
    legacy_failed_requests = metrics_query.filter(ApiRequestMetric.statusCode >= 400).count()
    legacy_server_errors = metrics_query.filter(ApiRequestMetric.statusCode >= 500).count()
    if aggregate_totals[0] is not None:
        total_requests = max(int(aggregate_totals[0] or 0), legacy_total_requests)
        failed_api_requests = max(
            int(aggregate_totals[1] or 0) + int(aggregate_totals[2] or 0),
            legacy_failed_requests,
        )
        server_errors = max(int(aggregate_totals[2] or 0), legacy_server_errors)
        average_response_time = (
            float(aggregate_totals[3] or 0) / int(aggregate_totals[0])
            if aggregate_totals[0] else 0
        )
    else:
        total_requests = legacy_total_requests
        failed_api_requests = legacy_failed_requests
        server_errors = legacy_server_errors
        average_response_time = metrics_query.with_entities(
            func.avg(ApiRequestMetric.responseTimeMs)
        ).scalar() or 0
    availability = (
        (total_requests - server_errors) / total_requests * 100
        if total_requests
        else 100.0
    )

    jobs = db.query(ImportBatch).filter(
        ImportBatch.companyId == user.companyId,
        ImportBatch.createdAt >= window_start,
    )
    reconciliations = db.query(ReconciliationExecution).filter(
        ReconciliationExecution.companyId == user.companyId,
        ReconciliationExecution.startedAt >= window_start,
    )
    monitored_jobs = db.query(SystemJob).filter(
        SystemJob.companyId == user.companyId,
        SystemJob.createdAt >= window_start,
    ).all()
    tracked_sources = {
        (job.relatedEntityType, str(job.relatedEntityId))
        for job in monitored_jobs
    }
    job_status_counts = {
        "completed": sum(job.status == "completed" for job in monitored_jobs),
        "failed": sum(job.status == "failed" for job in monitored_jobs),
        "running": sum(job.status == "running" for job in monitored_jobs),
        "pending": sum(job.status == "pending" for job in monitored_jobs),
    }
    legacy_imports = jobs.all()
    for batch in legacy_imports:
        if ("ImportBatch", str(batch.id)) in tracked_sources:
            continue
        legacy_status = {
            "completed": "completed",
            "completed_with_errors": "completed",
            "failed": "failed",
            "processing": "running",
            "queued": "pending",
        }.get(batch.status)
        if legacy_status:
            job_status_counts[legacy_status] += 1
    legacy_reconciliations = reconciliations.all()
    for execution in legacy_reconciliations:
        if ("ReconciliationExecution", str(execution.id)) in tracked_sources:
            continue
        legacy_status = {
            "completed": "completed",
            "completed_with_issues": "completed",
            "failed": "failed",
            "running": "running",
        }.get(execution.status)
        if legacy_status:
            job_status_counts[legacy_status] += 1
    completed_jobs = job_status_counts["completed"]
    failed_jobs = job_status_counts["failed"]
    active_jobs = job_status_counts["running"]
    pending_jobs = job_status_counts["pending"]
    failed_reconciliations = reconciliations.filter(
        ReconciliationExecution.status == "failed"
    ).count()

    database_available = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_available = False
        db.rollback()

    status = _classify_health_status(
        database_available,
        availability,
        float(average_response_time),
        failed_jobs,
        failed_reconciliations,
    )

    api_errors = metrics_query.filter(ApiRequestMetric.statusCode >= 500).order_by(
        ApiRequestMetric.createdAt.desc(),
        ApiRequestMetric.id.desc(),
    ).limit(RECENT_ERROR_LIMIT).all()
    job_errors = jobs.filter(
        ImportBatch.status.in_(("failed", "completed_with_errors"))
    ).order_by(ImportBatch.createdAt.desc(), ImportBatch.id.desc()).limit(
        RECENT_ERROR_LIMIT
    ).all()
    reconciliation_errors = reconciliations.filter(
        ReconciliationExecution.status == "failed"
    ).order_by(
        ReconciliationExecution.startedAt.desc(),
        ReconciliationExecution.id.desc(),
    ).limit(RECENT_ERROR_LIMIT).all()
    recent_errors = [
        {
            "source": "api",
            "message": f"{metric.method} {metric.path} returned HTTP {metric.statusCode}",
            "occurredAt": metric.createdAt,
        }
        for metric in api_errors
    ]
    recent_errors.extend(
        {
            "source": "background_job",
            "message": batch.failureMessage or (
                f"Import batch {batch.id} completed with {batch.failedCount or 0} failed rows."
                if batch.status == "completed_with_errors"
                else f"Import batch {batch.id} failed."
            ),
            "occurredAt": batch.completedAt or batch.createdAt,
        }
        for batch in job_errors
    )
    recent_errors.extend(
        {
            "source": "data_quality",
            "message": execution.errorMessage or f"Reconciliation {execution.id} failed.",
            "occurredAt": execution.completedAt or execution.startedAt,
        }
        for execution in reconciliation_errors
    )
    recent_errors.sort(key=lambda error: error["occurredAt"] or now, reverse=True)

    return {
        "status": status,
        "apiAvailable": database_available and availability >= 95,
        "apiAvailabilityPercent": round(availability, 2),
        "averageResponseTimeMs": round(float(average_response_time), 2),
        "failedApiRequests": failed_api_requests,
        "totalApiRequests": total_requests,
        "backgroundJobsCompleted": completed_jobs,
        "backgroundJobsFailed": failed_jobs,
        "activeJobs": active_jobs,
        "pendingJobs": pending_jobs,
        "failedReconciliations": failed_reconciliations,
        "recentErrors": recent_errors[:RECENT_ERROR_LIMIT],
        "lastHealthCheckAt": now,
        "metricsWindowHours": WINDOW_HOURS,
        "apiTrend": [
            {
                "timestamp": bucket_start,
                "requestCount": int(request_count or 0),
                "serverErrorCount": int(server_errors or 0),
                "averageResponseTimeMs": round(
                    float(response_time_total or 0) / int(request_count), 2
                ) if request_count else 0.0,
            }
            for bucket_start, request_count, server_errors, response_time_total in trend_rows
        ],
    }


def get_api_health(db: DbDependency) -> dict:
    checked_at = datetime.now(timezone.utc)
    components = {
        "application_api": {
            "status": "healthy",
            "message": "Health endpoint is responding.",
            "checkedAt": checked_at,
        },
        "database": {
            "status": "healthy",
            "message": "Database connectivity check succeeded.",
            "checkedAt": checked_at,
        },
        "background_processing": {
            "status": "healthy",
            "message": "Background job queue is accessible.",
            "checkedAt": checked_at,
        },
        "external_integrations": {
            "status": "not_configured",
            "message": "No external service integrations are configured.",
            "checkedAt": checked_at,
        },
    }
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db.rollback()
        components["database"].update(
            status="unavailable",
            message="Database connectivity check failed.",
        )
        try:
            company_ids = {
                company_id
                for (company_id,) in db.query(User.companyId).filter(
                    User.companyId.isnot(None)
                ).distinct().all()
            }
            for company_id in company_ids:
                issue = record_system_error(
                    db,
                    company_id=company_id,
                    fingerprint="database:unavailable",
                    category="Database health-check failure",
                    component="Database",
                    endpoint_or_job="Database connectivity",
                    severity="critical",
                    occurred_at=checked_at,
                )
                notify_system_incident(db, issue)
            db.commit()
        except Exception:
            db.rollback()
            logging.exception("Unable to persist database health incident")
        components["background_processing"].update(
            status="unavailable",
            message="Background processing health could not be checked.",
        )
        return {
            "status": "unavailable",
            "checkedAt": checked_at,
            "components": components,
        }

    try:
        database_incidents = db.query(SystemError).filter(
            SystemError.fingerprint == "database:unavailable",
            SystemError.status != "resolved",
        ).all()
        for issue in database_incidents:
            recover_system_incident(
                db,
                issue,
                message="Database connectivity health check recovered.",
            )
        if database_incidents:
            db.commit()
    except Exception:
        db.rollback()
        logging.exception("Unable to close recovered database health incidents")

    try:
        stale_pending = db.query(ImportBatch.id).filter(
            ImportBatch.status == "queued",
            ImportBatch.createdAt < checked_at - timedelta(minutes=15),
        ).first()
        stale_running = db.query(ImportBatch.id).filter(
            ImportBatch.status == "processing",
            ImportBatch.startedAt.isnot(None),
            ImportBatch.startedAt < checked_at - timedelta(minutes=30),
        ).first()
        if stale_pending or stale_running:
            components["background_processing"].update(
                status="degraded",
                message="One or more background jobs exceeded the expected processing window.",
            )
    except Exception:
        db.rollback()
        components["background_processing"].update(
            status="unavailable",
            message="Background processing health could not be checked.",
        )

    background_status = components["background_processing"]["status"]
    overall_status = (
        "unavailable"
        if background_status == "unavailable"
        else "degraded"
        if background_status == "degraded"
        else "healthy"
    )
    result = {
        "status": overall_status,
        "checkedAt": checked_at,
        "components": components,
    }
    try:
        record_health_check_results(db, components)
        cleanup_monitoring_data(db)
    except Exception:
        db.rollback()
        logging.exception("Unable to persist health-check results")
    return result


def list_api_request_metrics(
    db: DbDependency,
    authorization: str | None,
    endpoint: str | None,
    status_code: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    outcome: str | None,
    search: str | None,
    sort_by: str,
    sort_order: str,
    page: int,
    page_size: int,
) -> dict:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_admin(user)
    if outcome not in {None, "success", "failure"}:
        raise HTTPException(status_code=422, detail="Outcome must be success or failure")
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=422, detail="Start time must be before end time")

    query = db.query(ApiRequestMetric).filter(
        ApiRequestMetric.companyId == user.companyId,
    )
    if endpoint:
        query = query.filter(ApiRequestMetric.path.ilike(f"%{endpoint.strip()}%"))
    if search:
        wildcard = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ApiRequestMetric.path.ilike(wildcard),
                ApiRequestMetric.method.ilike(wildcard),
                ApiRequestMetric.errorDetails.ilike(wildcard),
            )
        )
    if status_code is not None:
        query = query.filter(ApiRequestMetric.statusCode == status_code)
    if start_time:
        query = query.filter(ApiRequestMetric.createdAt >= start_time)
    if end_time:
        query = query.filter(ApiRequestMetric.createdAt <= end_time)
    if outcome == "success":
        query = query.filter(ApiRequestMetric.statusCode < 400)
    elif outcome == "failure":
        query = query.filter(ApiRequestMetric.statusCode >= 400)

    sort_columns = {
        "timestamp": ApiRequestMetric.createdAt,
        "endpoint": ApiRequestMetric.path,
        "statusCode": ApiRequestMetric.statusCode,
        "responseTimeMs": ApiRequestMetric.responseTimeMs,
    }
    sort_column = sort_columns.get(sort_by, ApiRequestMetric.createdAt)
    ordering = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    total = query.count()
    records = query.order_by(ordering, ApiRequestMetric.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return {
        "items": [
            {
                "id": metric.id,
                "endpoint": metric.path,
                "method": metric.method,
                "statusCode": metric.statusCode,
                "responseTimeMs": metric.responseTimeMs,
                "timestamp": metric.createdAt,
                "isSuccess": metric.statusCode < 400,
                "errorDetails": metric.errorDetails,
            }
            for metric in records
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def _system_health_admin(db: DbDependency, authorization: str | None):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_admin(user)
    return user


def _can_retry_system_job(db, job: SystemJob, company_id: int) -> bool:
    if (
        job.status != "failed"
        or job.relatedEntityType != "ImportBatch"
        or not job.relatedEntityId
    ):
        return False
    try:
        batch_id = int(job.relatedEntityId)
    except (TypeError, ValueError):
        return False
    batch = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.companyId == company_id,
        ImportBatch.status == "failed",
        ImportBatch.insertedCount == 0,
        ImportBatch.updatedCount == 0,
        ImportBatch.failedCount > 0,
    ).first()
    if not batch:
        return False
    return db.query(ImportRecord.id).filter(
        ImportRecord.batchId == batch.id,
        ImportRecord.companyId == company_id,
        ImportRecord.status == "failed",
    ).first() is not None


def _system_job_response(job: SystemJob, *, can_retry: bool = False) -> dict:
    return {
        "id": job.id,
        "jobType": job.jobType or "Background job",
        "triggeredBy": job.triggeredBy or "System",
        "relatedRecord": f"{job.relatedEntityType or 'Job'} #{job.relatedEntityId or job.id}",
        "startedAt": job.startedAt,
        "completedAt": job.completedAt,
        "durationMs": job.durationMs,
        "status": job.status,
        "retryCount": int(job.retryCount or 0),
        "failureReason": job.failureReason,
        "canCancel": job.status in {"pending", "running"} and job.relatedEntityType == "ImportBatch",
        "canRetry": can_retry,
        "details": json.loads(job.details or "{}"),
    }


def list_system_jobs(
    db: DbDependency,
    authorization: str | None,
    job_type: str | None,
    status: str | None,
    search: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    page: int,
    page_size: int,
) -> dict:
    user = _system_health_admin(db, authorization)
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=422, detail="Start time must be before end time")
    if status and status not in {"pending", "running", "completed", "failed", "cancelled"}:
        raise HTTPException(status_code=422, detail="Unsupported job status")

    query = db.query(SystemJob).filter(SystemJob.companyId == user.companyId)
    if job_type:
        query = query.filter(SystemJob.jobType.ilike(f"%{job_type.strip()}%"))
    if status:
        query = query.filter(SystemJob.status == status)
    if start_time:
        query = query.filter(SystemJob.createdAt >= start_time)
    if end_time:
        query = query.filter(SystemJob.createdAt <= end_time)
    if search:
        wildcard = f"%{search.strip()}%"
        query = query.filter(or_(
            SystemJob.jobType.ilike(wildcard),
            SystemJob.triggeredBy.ilike(wildcard),
            SystemJob.relatedEntityType.ilike(wildcard),
            SystemJob.relatedEntityId.ilike(wildcard),
            SystemJob.failureReason.ilike(wildcard),
        ))
    total = query.count()
    jobs = query.order_by(SystemJob.createdAt.desc(), SystemJob.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return {
        "items": [
            _system_job_response(
                job,
                can_retry=_can_retry_system_job(db, job, user.companyId),
            )
            for job in jobs
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def get_system_job(db: DbDependency, job_id: int, authorization: str | None) -> dict:
    user = _system_health_admin(db, authorization)
    job = db.query(SystemJob).filter(
        SystemJob.id == job_id,
        SystemJob.companyId == user.companyId,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Background job not found")
    response = _system_job_response(
        job,
        can_retry=_can_retry_system_job(db, job, user.companyId),
    )
    if job.relatedEntityType == "ImportBatch":
        batch = db.query(ImportBatch).filter(
            ImportBatch.id == int(job.relatedEntityId),
            ImportBatch.companyId == user.companyId,
        ).first()
        if batch:
            row_status_counts = dict(
                db.query(ImportRecord.status, func.count(ImportRecord.id))
                .filter(
                    ImportRecord.batchId == batch.id,
                    ImportRecord.companyId == user.companyId,
                )
                .group_by(ImportRecord.status)
                .all()
            )
            response["details"].update({
                "batchStatus": batch.status,
                "processedCount": int(batch.processedCount or 0),
                "insertedCount": int(batch.insertedCount or 0),
                "updatedCount": int(batch.updatedCount or 0),
                "failedCount": int(batch.failedCount or 0),
                "rowStatusCounts": row_status_counts,
            })
    elif job.relatedEntityType == "ReconciliationExecution":
        execution = db.query(ReconciliationExecution).filter(
            ReconciliationExecution.id == int(job.relatedEntityId),
            ReconciliationExecution.companyId == user.companyId,
        ).first()
        if execution:
            response["details"].update({
                "recordsChecked": int(execution.recordsChecked or 0),
                "issuesDetected": int(execution.issuesDetected or 0),
                "issuesResolved": int(execution.issuesResolved or 0),
                "failedChecks": int(execution.failedChecks or 0),
            })
    elif job.relatedEntityType == "ReportHistory":
        report = db.query(ReportHistory).filter(
            ReportHistory.id == int(job.relatedEntityId),
            ReportHistory.companyId == user.companyId,
        ).first()
        if report:
            response["details"].update({
                "reportType": report.reportType,
                "exportFormat": report.exportFormat,
                "rowCount": int(report.rowCount or 0),
                "reportStatus": report.status,
            })
    return response


def cancel_system_job(db: DbDependency, job_id: int, authorization: str | None) -> dict:
    user = _system_health_admin(db, authorization)
    job = db.query(SystemJob).filter(
        SystemJob.id == job_id,
        SystemJob.companyId == user.companyId,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Background job not found")
    if job.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Only pending or running jobs can be cancelled")
    if job.relatedEntityType != "ImportBatch":
        raise HTTPException(status_code=409, detail="Cancellation is not supported for this job type")

    from backend.controllers.imports_controller import cancel_import_batch

    result = cancel_import_batch(int(job.relatedEntityId), db, authorization)
    db.refresh(job)
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Background Job Cancellation Requested",
        entity_name=job.jobType,
        resource_type="SystemJob",
        resource_id=job.id,
        description=f"Cancellation requested for {job.jobType} ({job.relatedEntityType} #{job.relatedEntityId}).",
        company_id=user.companyId,
        user_id=user.id,
    )
    return {**_system_job_response(job), "message": result["message"]}


def retry_system_job(
    db: DbDependency,
    job_id: int,
    authorization: str | None,
    enqueue_import,
) -> dict:
    user = _system_health_admin(db, authorization)
    job = db.query(SystemJob).filter(
        SystemJob.id == job_id,
        SystemJob.companyId == user.companyId,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Background job not found")
    if not _can_retry_system_job(db, job, user.companyId):
        raise HTTPException(
            status_code=409,
            detail="This job cannot be safely retried. Only failed imports with no applied rows are eligible.",
        )

    batch_id = int(job.relatedEntityId)
    batch_update = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.companyId == user.companyId,
        ImportBatch.status == "failed",
        ImportBatch.insertedCount == 0,
        ImportBatch.updatedCount == 0,
        ImportBatch.failedCount > 0,
    ).update(
        {
            ImportBatch.status: "queued",
            ImportBatch.startedAt: None,
            ImportBatch.completedAt: None,
            ImportBatch.durationSeconds: 0,
            ImportBatch.processedCount: ImportBatch.invalidCount + ImportBatch.duplicateCount,
            ImportBatch.failedCount: 0,
            ImportBatch.failureMessage: None,
            ImportBatch.cancelRequested: 0,
        },
        synchronize_session=False,
    )
    if batch_update != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="The import is no longer eligible for retry")

    db.query(ImportRecord).filter(
        ImportRecord.batchId == batch_id,
        ImportRecord.companyId == user.companyId,
        ImportRecord.status == "failed",
    ).update(
        {ImportRecord.status: "valid", ImportRecord.message: None},
        synchronize_session=False,
    )
    previous_retry_count = db.query(func.max(SystemJob.retryCount)).filter(
        SystemJob.companyId == user.companyId,
        SystemJob.relatedEntityType == "ImportBatch",
        SystemJob.relatedEntityId == str(batch_id),
    ).scalar() or 0
    retry = SystemJob(
        companyId=user.companyId,
        jobType=job.jobType,
        triggeredByUserId=user.id,
        triggeredBy=user.name or user.email,
        relatedEntityType="ImportBatch",
        relatedEntityId=str(batch_id),
        status="pending",
        retryCount=int(previous_retry_count) + 1,
        details=job.details,
    )
    db.add(retry)
    db.flush()
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Background Job Retry Requested",
        entity_name=job.jobType,
        resource_type="SystemJob",
        resource_id=retry.id,
        description=(
            f"Safe retry requested for failed import batch {batch_id}; "
            "the prior attempt applied no rows."
        ),
        company_id=user.companyId,
        user_id=user.id,
    )
    db.commit()
    db.refresh(retry)
    enqueue_import(batch_id, user.id)
    return _system_job_response(retry)


def list_system_errors(
    db: DbDependency,
    authorization: str | None,
    severity: str | None,
    component: str | None,
    status: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    search: str | None,
    page: int,
    page_size: int,
) -> dict:
    user = _system_health_admin(db, authorization)
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=422, detail="Start time must be before end time")
    if severity and severity not in {"critical", "high", "medium", "low"}:
        raise HTTPException(status_code=422, detail="Unsupported error severity")
    if status and status not in {"open", "investigating", "resolved"}:
        raise HTTPException(status_code=422, detail="Unsupported error status")

    query = db.query(SystemError).filter(SystemError.companyId == user.companyId)
    if severity:
        query = query.filter(SystemError.severity == severity)
    if component:
        query = query.filter(SystemError.component.ilike(f"%{component.strip()}%"))
    if status:
        query = query.filter(SystemError.status == status)
    if start_time:
        query = query.filter(SystemError.lastOccurredAt >= start_time)
    if end_time:
        query = query.filter(SystemError.lastOccurredAt <= end_time)
    if search:
        wildcard = f"%{search.strip()}%"
        query = query.filter(or_(
            SystemError.category.ilike(wildcard),
            SystemError.component.ilike(wildcard),
            SystemError.endpointOrJob.ilike(wildcard),
        ))
    total = query.count()
    errors = query.order_by(
        SystemError.lastOccurredAt.desc(),
        SystemError.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": error.id,
                "category": error.category,
                "component": error.component,
                "endpointOrJob": error.endpointOrJob,
                "timestamp": error.lastOccurredAt,
                "severity": error.severity,
                "occurrenceCount": int(error.occurrenceCount or 1),
                "status": error.status,
                "resolutionNotes": error.resolutionNotes,
            }
            for error in errors
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def get_system_error(db: DbDependency, error_id: int, authorization: str | None) -> dict:
    user = _system_health_admin(db, authorization)
    error = db.query(SystemError).filter(
        SystemError.id == error_id,
        SystemError.companyId == user.companyId,
    ).first()
    if not error:
        raise HTTPException(status_code=404, detail="System error not found")
    return {
        "id": error.id,
        "category": error.category,
        "component": error.component,
        "endpointOrJob": error.endpointOrJob,
        "timestamp": error.lastOccurredAt,
        "severity": error.severity,
        "occurrenceCount": int(error.occurrenceCount or 1),
        "status": error.status,
        "resolutionNotes": error.resolutionNotes,
        "firstOccurredAt": error.firstOccurredAt,
        "lastOccurredAt": error.lastOccurredAt,
    }


def update_system_error(
    db: DbDependency,
    error_id: int,
    payload,
    authorization: str | None,
) -> dict:
    user = _system_health_admin(db, authorization)
    error = db.query(SystemError).filter(
        SystemError.id == error_id,
        SystemError.companyId == user.companyId,
    ).first()
    if not error:
        raise HTTPException(status_code=404, detail="System error not found")
    notes = payload.resolutionNotes if payload.status == "resolved" else payload.investigationNotes
    action = {
        "open": "System Incident Reopened",
        "investigating": "System Incident Investigation Started",
        "resolved": "System Incident Resolved",
    }[payload.status]
    transition_system_incident(
        db,
        error,
        status=payload.status,
        actor_user_id=user.id,
        actor_name=user.name or user.email,
        notes=notes or "Incident status updated.",
        action=action.lower().replace(" ", "_"),
    )
    if payload.status == "open":
        notify_system_incident(db, error)
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action=action,
        entity_name=error.component,
        resource_type="SystemError",
        resource_id=error.id,
        description=f"Incident status changed to {payload.status}. {notes or ''}".strip(),
        company_id=user.companyId,
        user_id=user.id,
    )
    db.commit()
    db.refresh(error)
    return {
        "id": error.id,
        "category": error.category,
        "component": error.component,
        "endpointOrJob": error.endpointOrJob,
        "timestamp": error.lastOccurredAt,
        "severity": error.severity,
        "occurrenceCount": int(error.occurrenceCount or 1),
        "status": error.status,
        "resolutionNotes": error.resolutionNotes,
    }


def list_system_incident_timeline(
    db: DbDependency,
    error_id: int,
    authorization: str | None,
) -> list[dict]:
    user = _system_health_admin(db, authorization)
    error = db.query(SystemError).filter(
        SystemError.id == error_id,
        SystemError.companyId == user.companyId,
    ).first()
    if not error:
        raise HTTPException(status_code=404, detail="System error not found")
    events = db.query(SystemIncidentEvent).filter(
        SystemIncidentEvent.companyId == user.companyId,
        SystemIncidentEvent.systemErrorId == error.id,
    ).order_by(SystemIncidentEvent.createdAt.asc(), SystemIncidentEvent.id.asc()).all()
    return [
        {
            "id": event.id,
            "action": event.action,
            "previousStatus": event.previousStatus,
            "newStatus": event.newStatus,
            "notes": event.notes,
            "actorUserId": event.actorUserId,
            "actorName": event.actorName or "System",
            "createdAt": event.createdAt,
        }
        for event in events
    ]


def get_system_health_thresholds(db: DbDependency, authorization: str | None) -> dict:
    user = _system_health_admin(db, authorization)
    threshold = db.query(SystemHealthThreshold).filter(
        SystemHealthThreshold.companyId == user.companyId
    ).first()
    values = default_system_health_thresholds()
    if threshold:
        values.update({
            "apiErrorRatePercent": threshold.apiErrorRatePercent,
            "averageResponseTimeMs": threshold.averageResponseTimeMs,
            "sampleWindowMinutes": threshold.sampleWindowMinutes,
            "minimumRequestCount": threshold.minimumRequestCount,
            "repeatedFailureCount": threshold.repeatedFailureCount,
            "updatedAt": threshold.updatedAt,
            "updatedByUserId": threshold.updatedByUserId,
        })
    else:
        values.update({"updatedAt": None, "updatedByUserId": None})
    return values


def update_system_health_thresholds(
    db: DbDependency,
    payload,
    authorization: str | None,
) -> dict:
    user = _system_health_admin(db, authorization)
    threshold = get_or_create_system_health_threshold(db, user.companyId)
    previous = {
        "apiErrorRatePercent": threshold.apiErrorRatePercent,
        "averageResponseTimeMs": threshold.averageResponseTimeMs,
        "sampleWindowMinutes": threshold.sampleWindowMinutes,
        "minimumRequestCount": threshold.minimumRequestCount,
        "repeatedFailureCount": threshold.repeatedFailureCount,
    }
    for key, value in payload.model_dump().items():
        setattr(threshold, key, value)
    threshold.updatedByUserId = user.id
    threshold.updatedAt = datetime.now(timezone.utc)
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="System Monitoring Thresholds Changed",
        entity_name="System Health",
        resource_type="SystemHealthThreshold",
        resource_id=threshold.id,
        description=f"Monitoring thresholds changed from {previous} to {payload.model_dump()}.",
        company_id=user.companyId,
        user_id=user.id,
    )
    db.commit()
    db.refresh(threshold)
    from backend.system_monitoring import evaluate_api_thresholds

    evaluate_api_thresholds(db, user.companyId)
    return {
        "apiErrorRatePercent": threshold.apiErrorRatePercent,
        "averageResponseTimeMs": threshold.averageResponseTimeMs,
        "sampleWindowMinutes": threshold.sampleWindowMinutes,
        "minimumRequestCount": threshold.minimumRequestCount,
        "repeatedFailureCount": threshold.repeatedFailureCount,
        "updatedAt": threshold.updatedAt,
        "updatedByUserId": threshold.updatedByUserId,
    }
