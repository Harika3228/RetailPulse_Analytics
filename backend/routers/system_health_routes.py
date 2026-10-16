from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Header, Query, Response

from backend.controllers.system_health_controller import (
    cancel_system_job,
    get_api_health,
    get_system_job,
    get_system_health,
    get_system_error,
    list_system_errors,
    list_system_incident_timeline,
    list_system_jobs,
    list_api_request_metrics,
    get_system_health_thresholds,
    retry_system_job,
    update_system_error,
    update_system_health_thresholds,
)
from backend.database import DbDependency
from backend.controllers.imports_controller import run_import_job
from backend.schemas import (
    ApiHealthResponse,
    ApiRequestMetricsPageResponse,
    SystemHealthResponse,
    SystemErrorResponse,
    SystemErrorUpdate,
    SystemErrorsPageResponse,
    SystemJobResponse,
    SystemJobsPageResponse,
    SystemIncidentEventResponse,
    SystemHealthThresholdResponse,
    SystemHealthThresholdUpdate,
)

router = APIRouter(tags=["system-health"])


@router.get("/api/health", response_model=ApiHealthResponse)
@router.get("/health", response_model=ApiHealthResponse, include_in_schema=False)
def api_health_route(db: DbDependency, response: Response):
    health = get_api_health(db)
    if health["status"] == "unavailable":
        response.status_code = 503
    return health


@router.get("/system-health", response_model=SystemHealthResponse)
def system_health_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_system_health(db, authorization)


@router.get(
    "/system-health/requests",
    response_model=ApiRequestMetricsPageResponse,
)
@router.get(
    "/api/system-health/requests",
    response_model=ApiRequestMetricsPageResponse,
    include_in_schema=False,
)
def api_request_metrics_route(
    db: DbDependency,
    endpoint: str | None = None,
    status_code: int | None = Query(default=None, ge=100, le=599),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    outcome: str | None = None,
    search: str | None = None,
    sort_by: str = Query(default="timestamp", alias="sortBy"),
    sort_order: str = Query(default="desc", alias="sortOrder", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100, alias="pageSize"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_api_request_metrics(
        db,
        authorization,
        endpoint,
        status_code,
        start_time,
        end_time,
        outcome,
        search,
        sort_by,
        sort_order,
        page,
        page_size,
    )


@router.get("/system-health/jobs", response_model=SystemJobsPageResponse)
def system_jobs_route(
    db: DbDependency,
    job_type: str | None = Query(default=None, alias="jobType"),
    status: str | None = None,
    search: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100, alias="pageSize"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_system_jobs(
        db, authorization, job_type, status, search, start_time, end_time, page, page_size
    )


@router.get("/system-health/jobs/{job_id}", response_model=SystemJobResponse)
def system_job_detail_route(
    job_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_system_job(db, job_id, authorization)


@router.post("/system-health/jobs/{job_id}/cancel")
def cancel_system_job_route(
    job_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return cancel_system_job(db, job_id, authorization)


@router.post("/system-health/jobs/{job_id}/retry", response_model=SystemJobResponse)
def retry_system_job_route(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return retry_system_job(
        db,
        job_id,
        authorization,
        lambda batch_id, user_id: background_tasks.add_task(run_import_job, batch_id, user_id),
    )


@router.get("/system-health/errors", response_model=SystemErrorsPageResponse)
def system_errors_route(
    db: DbDependency,
    severity: str | None = None,
    component: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100, alias="pageSize"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_system_errors(
        db,
        authorization,
        severity,
        component,
        status,
        start_time,
        end_time,
        search,
        page,
        page_size,
    )


@router.patch("/system-health/errors/{error_id}", response_model=SystemErrorResponse)
def update_system_error_route(
    error_id: int,
    payload: SystemErrorUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_system_error(db, error_id, payload, authorization)


@router.get("/system-health/errors/{error_id}", response_model=SystemErrorResponse)
def system_error_detail_route(
    error_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_system_error(db, error_id, authorization)


@router.get(
    "/system-health/errors/{error_id}/timeline",
    response_model=list[SystemIncidentEventResponse],
)
def system_incident_timeline_route(
    error_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_system_incident_timeline(db, error_id, authorization)


@router.get(
    "/system-health/thresholds",
    response_model=SystemHealthThresholdResponse,
)
def system_health_thresholds_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_system_health_thresholds(db, authorization)


@router.put(
    "/system-health/thresholds",
    response_model=SystemHealthThresholdResponse,
)
def update_system_health_thresholds_route(
    payload: SystemHealthThresholdUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_system_health_thresholds(db, payload, authorization)
