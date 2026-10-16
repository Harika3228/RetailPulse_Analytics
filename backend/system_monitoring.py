import json
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from backend.helpers import create_notification
from backend.models import (
    ApiRequestMetric,
    ApiRequestMetricAggregate,
    HealthCheckResult,
    Notification,
    SystemError,
    SystemHealthThreshold,
    SystemIncidentEvent,
    SystemJob,
)

API_METRIC_RETENTION_DAYS = 7
API_AGGREGATE_RETENTION_DAYS = 30
TERMINAL_JOB_RETENTION_DAYS = 180
RESOLVED_INCIDENT_RETENTION_DAYS = 365
API_SUCCESS_SAMPLE_RATE = 0.05
_last_retention_cleanup_at: datetime | None = None


def record_api_request(
    db,
    *,
    company_id: int,
    method: str,
    path: str,
    status_code: int,
    response_time_ms: float,
    error_details: str | None,
    occurred_at: datetime | None = None,
) -> None:
    now = occurred_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    bucket_start = now.replace(second=0, microsecond=0)
    db.query(ApiRequestMetricAggregate).filter(
        ApiRequestMetricAggregate.companyId == company_id,
        ApiRequestMetricAggregate.bucketStart == bucket_start,
        ApiRequestMetricAggregate.method == method,
        ApiRequestMetricAggregate.path == path,
    ).update({
        ApiRequestMetricAggregate.requestCount: ApiRequestMetricAggregate.requestCount + 1,
        ApiRequestMetricAggregate.clientErrorCount: ApiRequestMetricAggregate.clientErrorCount + int(400 <= status_code < 500),
        ApiRequestMetricAggregate.serverErrorCount: ApiRequestMetricAggregate.serverErrorCount + int(status_code >= 500),
        ApiRequestMetricAggregate.responseTimeTotalMs: ApiRequestMetricAggregate.responseTimeTotalMs + response_time_ms,
        ApiRequestMetricAggregate.responseTimeMaxMs: case(
            (ApiRequestMetricAggregate.responseTimeMaxMs < response_time_ms, response_time_ms),
            else_=ApiRequestMetricAggregate.responseTimeMaxMs,
        ),
        ApiRequestMetricAggregate.updatedAt: now,
    }, synchronize_session=False)
    if not db.query(ApiRequestMetricAggregate.id).filter(
        ApiRequestMetricAggregate.companyId == company_id,
        ApiRequestMetricAggregate.bucketStart == bucket_start,
        ApiRequestMetricAggregate.method == method,
        ApiRequestMetricAggregate.path == path,
    ).first():
        try:
            with db.begin_nested():
                db.add(ApiRequestMetricAggregate(
                    companyId=company_id,
                    bucketStart=bucket_start,
                    method=method,
                    path=path,
                    requestCount=1,
                    clientErrorCount=int(400 <= status_code < 500),
                    serverErrorCount=int(status_code >= 500),
                    responseTimeTotalMs=response_time_ms,
                    responseTimeMaxMs=response_time_ms,
                    updatedAt=now,
                ))
                db.flush()
        except IntegrityError:
            db.execute(update(ApiRequestMetricAggregate).where(
                ApiRequestMetricAggregate.companyId == company_id,
                ApiRequestMetricAggregate.bucketStart == bucket_start,
                ApiRequestMetricAggregate.method == method,
                ApiRequestMetricAggregate.path == path,
            ).values(
                requestCount=ApiRequestMetricAggregate.requestCount + 1,
                clientErrorCount=ApiRequestMetricAggregate.clientErrorCount + int(400 <= status_code < 500),
                serverErrorCount=ApiRequestMetricAggregate.serverErrorCount + int(status_code >= 500),
                responseTimeTotalMs=ApiRequestMetricAggregate.responseTimeTotalMs + response_time_ms,
                responseTimeMaxMs=case(
                    (ApiRequestMetricAggregate.responseTimeMaxMs < response_time_ms, response_time_ms),
                    else_=ApiRequestMetricAggregate.responseTimeMaxMs,
                ),
                updatedAt=now,
            ))

    if status_code >= 400 or random.random() < API_SUCCESS_SAMPLE_RATE:
        db.add(ApiRequestMetric(
            companyId=company_id,
            method=method,
            path=path,
            statusCode=status_code,
            responseTimeMs=round(response_time_ms, 2),
            errorDetails=error_details,
            createdAt=now,
        ))
    if status_code >= 500:
        issue = record_system_error(
            db,
            company_id=company_id,
            fingerprint=f"api:{method}:{path}:{status_code}",
            category="API server error",
            component="Application API",
            endpoint_or_job=f"{method} {path}",
            severity="high",
            occurred_at=now,
        )
        notify_system_incident(db, issue)


def record_health_check_results(db, components: dict, *, company_id: int = 0) -> None:
    now = datetime.now(timezone.utc)
    for component, result in components.items():
        result_query = db.query(HealthCheckResult).filter(
            HealthCheckResult.companyId == company_id,
            HealthCheckResult.component == component,
        )
        saved = result_query.first()
        if saved is None:
            try:
                with db.begin_nested():
                    saved = HealthCheckResult(companyId=company_id, component=component)
                    db.add(saved)
                    db.flush()
            except IntegrityError:
                saved = result_query.first()
                if saved is None:
                    raise
        saved.status = result["status"]
        saved.message = result["message"]
        saved.checkedAt = result.get("checkedAt", now)
    db.commit()


def cleanup_monitoring_data(db, *, force: bool = False, now: datetime | None = None) -> None:
    global _last_retention_cleanup_at
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if (
        not force
        and _last_retention_cleanup_at is not None
        and (current_time - _last_retention_cleanup_at).total_seconds() < 3600
    ):
        return

    try:
        db.query(ApiRequestMetric).filter(
            ApiRequestMetric.createdAt < current_time - timedelta(days=API_METRIC_RETENTION_DAYS)
        ).delete(synchronize_session=False)
        db.query(ApiRequestMetricAggregate).filter(
            ApiRequestMetricAggregate.bucketStart < current_time - timedelta(days=API_AGGREGATE_RETENTION_DAYS)
        ).delete(synchronize_session=False)
        db.query(SystemJob).filter(
            SystemJob.status.in_(("completed", "failed", "cancelled")),
            or_(
                SystemJob.completedAt < current_time - timedelta(days=TERMINAL_JOB_RETENTION_DAYS),
                (SystemJob.completedAt.is_(None))
                & (SystemJob.updatedAt < current_time - timedelta(days=TERMINAL_JOB_RETENTION_DAYS)),
            ),
        ).delete(synchronize_session=False)

        expired_incidents = select(SystemError.id).where(
            SystemError.status == "resolved",
            SystemError.resolvedAt < current_time - timedelta(days=RESOLVED_INCIDENT_RETENTION_DAYS),
        )
        db.query(SystemIncidentEvent).filter(
            SystemIncidentEvent.systemErrorId.in_(expired_incidents)
        ).delete(synchronize_session=False)
        expired_notifications = select(Notification.id).where(
            Notification.type == "system_incident",
            Notification.resolvedAt.isnot(None),
            Notification.resolvedAt < current_time - timedelta(days=RESOLVED_INCIDENT_RETENTION_DAYS),
        )
        db.query(Notification).filter(Notification.id.in_(expired_notifications)).delete(
            synchronize_session=False
        )
        db.query(SystemError).filter(
            SystemError.status == "resolved",
            SystemError.resolvedAt < current_time - timedelta(days=RESOLVED_INCIDENT_RETENTION_DAYS),
        ).delete(synchronize_session=False)
        db.commit()
        _last_retention_cleanup_at = current_time
    except Exception:
        db.rollback()
        logging.exception("Unable to apply monitoring data retention")

def create_system_job(
    db,
    *,
    company_id: int,
    job_type: str,
    triggered_by_user_id: int | None,
    triggered_by: str,
    related_entity_type: str,
    related_entity_id: int | str,
    details: dict,
    status: str = "pending",
    started_at: datetime | None = None,
) -> SystemJob:
    job = SystemJob(
        companyId=company_id,
        jobType=job_type,
        triggeredByUserId=triggered_by_user_id,
        triggeredBy=triggered_by,
        relatedEntityType=related_entity_type,
        relatedEntityId=str(related_entity_id),
        status=status,
        startedAt=started_at,
        details=json.dumps(details, separators=(",", ":")),
    )
    db.add(job)
    db.flush()
    return job


def finish_system_job(
    job: SystemJob,
    status: str,
    *,
    failure_reason: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    now = completed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    job.status = status
    job.completedAt = now
    job.failureReason = failure_reason
    started_at = job.startedAt
    if started_at and started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    job.durationMs = (
        round(max(0.0, (now - started_at).total_seconds() * 1000), 2)
        if started_at
        else 0.0
    )


def record_system_error(
    db,
    *,
    company_id: int,
    fingerprint: str,
    category: str,
    component: str,
    endpoint_or_job: str,
    severity: str = "high",
    occurred_at: datetime | None = None,
) -> SystemError:
    now = occurred_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    issue = db.query(SystemError).filter(
        SystemError.companyId == company_id,
        SystemError.fingerprint == fingerprint,
    ).first()
    is_new_incident = issue is None or issue.status == "resolved"
    previous_status = issue.status if issue else None
    if issue is None:
        issue = SystemError(
            companyId=company_id,
            fingerprint=fingerprint,
            category=category,
            component=component,
            endpointOrJob=endpoint_or_job,
            severity=severity,
            status="open",
            occurrenceCount=1,
            firstOccurredAt=now,
            lastOccurredAt=now,
        )
        db.add(issue)
    else:
        issue.occurrenceCount = int(issue.occurrenceCount or 0) + 1
        issue.lastOccurredAt = now
        if issue.status == "resolved":
            issue.status = "open"
            issue.resolutionNotes = None
            issue.resolvedAt = None
            issue.resolvedByUserId = None
    if is_new_incident:
        db.flush()
        db.add(SystemIncidentEvent(
            companyId=company_id,
            systemErrorId=issue.id,
            action="incident_opened",
            previousStatus=previous_status,
            newStatus="open",
            notes="Incident automatically opened from a monitored system event.",
            actorUserId=None,
            actorName="System",
            createdAt=now,
        ))
    return issue


def default_system_health_thresholds() -> dict:
    return {
        "apiErrorRatePercent": 5.0,
        "averageResponseTimeMs": 1000.0,
        "sampleWindowMinutes": 5,
        "minimumRequestCount": 10,
        "repeatedFailureCount": 3,
    }


def get_or_create_system_health_threshold(db, company_id: int) -> SystemHealthThreshold:
    threshold = db.query(SystemHealthThreshold).filter(
        SystemHealthThreshold.companyId == company_id
    ).first()
    if threshold is None:
        threshold = SystemHealthThreshold(companyId=company_id)
        db.add(threshold)
        db.flush()
    return threshold


def notify_system_incident(db, issue: SystemError, *, message: str | None = None) -> None:
    create_notification(
        db,
        issue.companyId,
        message=message or f"{issue.component}: {issue.category} requires attention.",
        notification_type="system_incident",
        target_role="admin",
        severity="error" if issue.severity in {"critical", "high"} else "warning",
        title=f"System incident: {issue.component}",
        resource_type="SystemError",
        resource_id=issue.id,
        alert_key=f"system-incident:{issue.id}",
    )


def notify_repeated_import_failure(db, issue: SystemError) -> None:
    threshold = get_or_create_system_health_threshold(db, issue.companyId)
    if int(issue.occurrenceCount or 0) >= int(threshold.repeatedFailureCount or 3):
        notify_system_incident(
            db,
            issue,
            message=(
                f"{issue.occurrenceCount} failures detected for {issue.endpointOrJob}. "
                "Review the related import batches."
            ),
        )


def transition_system_incident(
    db,
    issue: SystemError,
    *,
    status: str,
    actor_user_id: int | None,
    actor_name: str,
    notes: str,
    action: str,
) -> None:
    previous_status = issue.status
    now = datetime.now(timezone.utc)
    issue.status = status
    issue.resolutionNotes = notes if status == "resolved" else issue.resolutionNotes
    issue.resolvedAt = now if status == "resolved" else None
    issue.resolvedByUserId = actor_user_id if status == "resolved" else None
    issue.updatedAt = now
    db.add(SystemIncidentEvent(
        companyId=issue.companyId,
        systemErrorId=issue.id,
        action=action,
        previousStatus=previous_status,
        newStatus=status,
        notes=notes,
        actorUserId=actor_user_id,
        actorName=actor_name,
        createdAt=now,
    ))
    if status == "resolved":
        db.query(Notification).filter(
            Notification.companyId == issue.companyId,
            Notification.alertKey == f"system-incident:{issue.id}",
            Notification.resolvedAt.is_(None),
        ).update({"resolvedAt": now}, synchronize_session=False)


def recover_system_incident(db, issue: SystemError, *, message: str) -> None:
    if issue.status == "resolved":
        return
    transition_system_incident(
        db,
        issue,
        status="resolved",
        actor_user_id=None,
        actor_name="System",
        notes=message,
        action="incident_auto_recovered",
    )


def evaluate_api_thresholds(db, company_id: int) -> None:
    threshold = get_or_create_system_health_threshold(db, company_id)
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=int(threshold.sampleWindowMinutes or 5))
    count, failed, average = db.query(
        func.sum(ApiRequestMetricAggregate.requestCount),
        func.sum(ApiRequestMetricAggregate.serverErrorCount),
        func.sum(ApiRequestMetricAggregate.responseTimeTotalMs)
        / func.nullif(func.sum(ApiRequestMetricAggregate.requestCount), 0),
    ).filter(
        ApiRequestMetricAggregate.companyId == company_id,
        ApiRequestMetricAggregate.bucketStart >= start.replace(second=0, microsecond=0),
    ).one()
    if count is None:
        count, failed, average = db.query(
            func.count(ApiRequestMetric.id),
            func.sum(case((ApiRequestMetric.statusCode >= 500, 1), else_=0)),
            func.avg(ApiRequestMetric.responseTimeMs),
        ).filter(
            ApiRequestMetric.companyId == company_id,
            ApiRequestMetric.createdAt >= start,
        ).one()
    count = int(count or 0)
    failed = int(failed or 0)
    average = float(average or 0)
    error_rate = failed / count * 100 if count else 0.0
    requirements_met = count >= int(threshold.minimumRequestCount or 10)
    alert_states = {
        "api:error-rate": (
            requirements_met and error_rate >= float(threshold.apiErrorRatePercent),
            f"HTTP 5xx rate is {error_rate:.1f}% over the last {threshold.sampleWindowMinutes} minutes.",
            "API error-rate threshold exceeded",
        ),
        "api:response-time": (
            requirements_met and average >= float(threshold.averageResponseTimeMs),
            f"Average API response time is {average:.0f} ms over the last {threshold.sampleWindowMinutes} minutes.",
            "API response-time threshold exceeded",
        ),
    }
    for fingerprint, (is_breached, message, category) in alert_states.items():
        issue = db.query(SystemError).filter(
            SystemError.companyId == company_id,
            SystemError.fingerprint == fingerprint,
        ).first()
        if is_breached:
            issue = record_system_error(
                db,
                company_id=company_id,
                fingerprint=fingerprint,
                category=category,
                component="Application API",
                endpoint_or_job="API performance",
                severity="high",
                occurred_at=now,
            )
            issue.lastOccurredAt = now
            notify_system_incident(db, issue, message=message)
        elif issue and issue.status != "resolved":
            recover_system_incident(
                db,
                issue,
                message="API metrics returned below the configured monitoring threshold.",
            )
    db.commit()


def recover_component_incident(
    db,
    *,
    company_id: int,
    fingerprint: str,
    recovery_message: str,
) -> None:
    issue = db.query(SystemError).filter(
        SystemError.companyId == company_id,
        SystemError.fingerprint == fingerprint,
        SystemError.status != "resolved",
    ).first()
    if issue:
        recover_system_incident(db, issue, message=recovery_message)
        db.commit()
