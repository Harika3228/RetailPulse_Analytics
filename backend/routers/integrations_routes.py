from fastapi import APIRouter, BackgroundTasks, Header, Query, Request

from backend.controllers.integrations_controller import (
    create_integration,
    delete_integration,
    export_integration_sync_errors,
    get_integration_dashboard,
    get_integration_detail,
    get_integration_sync_run,
    get_integration_sync_errors,
    list_integration_sync_runs,
    list_integrations,
    retry_failed_sync_records,
    set_integration_enabled,
    start_csv_sync,
    test_integration_connection,
    update_integration,
    update_integration_field_mapping,
    update_integration_schedule,
)
from backend.database import DbDependency
from backend.schemas import (
    IntegrationConnectorCreate,
    IntegrationConnectorResponse,
    IntegrationConnectorUpdate,
    IntegrationConnectionTestRequest,
    IntegrationConnectionTestResponse,
    IntegrationDashboardResponse,
    IntegrationDashboardItem,
    IntegrationFieldMappingResponse,
    IntegrationFieldMappingUpdate,
    IntegrationScheduleUpdate,
    IntegrationSyncResponse,
    IntegrationSyncHistoryResponse,
    IntegrationSyncRunItem,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get(
    "",
    response_model=list[IntegrationDashboardItem],
    summary="List integrations visible to the authenticated company",
)
def integration_list_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_integrations(db, authorization)


@router.get(
    "/dashboard",
    response_model=IntegrationDashboardResponse,
    summary="Get company integration dashboard",
)
def integration_dashboard_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_integration_dashboard(db, authorization)


@router.post(
    "",
    response_model=IntegrationConnectorResponse,
    status_code=201,
    summary="Create an integration configuration",
)
def create_integration_route(
    payload: IntegrationConnectorCreate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return create_integration(payload, db, authorization)


@router.post(
    "/test-connection",
    response_model=IntegrationConnectionTestResponse,
    summary="Test a source connection without changing business data",
)
def test_integration_connection_route(
    payload: IntegrationConnectionTestRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return test_integration_connection(payload, db, authorization)


@router.get(
    "/sync-runs",
    response_model=IntegrationSyncHistoryResponse,
    summary="List company synchronization history",
)
def integration_sync_history_route(
    db: DbDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    integrationId: int | None = Query(default=None, gt=0),
    status: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_integration_sync_runs(db, authorization, offset=offset, limit=limit, connector_id=integrationId, status=status)


@router.get(
    "/{connector_id}/sync-runs",
    response_model=IntegrationSyncHistoryResponse,
    summary="List synchronization history for one integration",
)
def integration_connector_sync_history_route(
    connector_id: int,
    db: DbDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_integration_sync_runs(
        db,
        authorization,
        offset=offset,
        limit=limit,
        connector_id=connector_id,
        status=status,
    )


@router.get(
    "/sync-runs/{sync_run_id}",
    response_model=IntegrationSyncRunItem,
    summary="Get synchronization details",
)
def integration_sync_detail_route(
    sync_run_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_integration_sync_run(sync_run_id, db, authorization)


@router.get("/sync-runs/{sync_run_id}/errors", summary="List safe failed-record details")
def integration_sync_errors_route(
    sync_run_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_integration_sync_errors(sync_run_id, db, authorization)


@router.get("/sync-runs/{sync_run_id}/errors/export", summary="Download failed-record CSV")
def integration_sync_errors_export_route(
    sync_run_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_integration_sync_errors(sync_run_id, db, authorization)


@router.post("/sync-runs/{sync_run_id}/retry", status_code=202, summary="Retry failed records only")
def integration_sync_retry_route(
    sync_run_id: int,
    background_tasks: BackgroundTasks,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return retry_failed_sync_records(sync_run_id, db, authorization, background_tasks)


@router.get(
    "/{connector_id}",
    response_model=IntegrationConnectorResponse,
    summary="Get integration details",
)
def integration_detail_route(
    connector_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_integration_detail(db, connector_id, authorization)


@router.patch(
    "/{connector_id}",
    response_model=IntegrationConnectorResponse,
    summary="Update an integration configuration",
)
def update_integration_route(
    connector_id: int,
    payload: IntegrationConnectorUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_integration(connector_id, payload, db, authorization)


@router.put(
    "/{connector_id}/field-mapping",
    response_model=IntegrationFieldMappingResponse,
    summary="Validate and save the connector field mapping",
)
def update_integration_field_mapping_route(
    connector_id: int,
    payload: IntegrationFieldMappingUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_integration_field_mapping(connector_id, payload, db, authorization)


@router.put(
    "/{connector_id}/schedule",
    response_model=IntegrationConnectorResponse,
    summary="Configure or disable a connector synchronization schedule",
)
def update_integration_schedule_route(
    connector_id: int,
    payload: IntegrationScheduleUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_integration_schedule(connector_id, payload, db, authorization)


@router.post(
    "/{connector_id}/enable",
    response_model=IntegrationConnectorResponse,
    summary="Enable an integration connector",
)
def enable_integration_route(
    connector_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return set_integration_enabled(connector_id, True, db, authorization)


@router.post(
    "/{connector_id}/disable",
    response_model=IntegrationConnectorResponse,
    summary="Disable an integration connector",
)
def disable_integration_route(
    connector_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return set_integration_enabled(connector_id, False, db, authorization)


@router.delete(
    "/{connector_id}",
    summary="Delete an integration configuration",
)
def delete_integration_route(
    connector_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return delete_integration(connector_id, db, authorization)


@router.post(
    "/{connector_id}/sync",
    response_model=IntegrationSyncResponse,
    status_code=202,
    summary="Start CSV integration synchronization",
)
async def start_integration_sync_route(
    connector_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbDependency,
    fileName: str | None = None,
    fieldMapping: str | None = Header(default=None, alias="X-Field-Mapping"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return await start_csv_sync(
        connector_id,
        request,
        db,
        authorization,
        fileName,
        background_tasks,
        fieldMapping,
    )
