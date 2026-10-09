from fastapi import APIRouter, BackgroundTasks, Header

from backend.controllers.workflows_controller import (
    cancel_approval_request,
    decide_approval_request,
    get_approval_request,
    get_approval_history,
    get_pending_approval_counts,
    list_approval_requests,
    submit_draft_approval_request,
    submit_approval_request,
    list_workflow_configurations,
    update_workflow_configuration,
)
from backend.database import DbDependency
from backend.controllers.imports_controller import run_import_job
from backend.schemas import (
    ApprovalAction,
    ApprovalDecision,
    ApprovalHistoryResponse,
    ApprovalRequestCreate,
    ApprovalRequestResponse,
    PendingApprovalCountsResponse,
    WorkflowConfigurationResponse,
    WorkflowConfigurationUpdate,
)
 
router = APIRouter(tags=["workflows"])


@router.get("/workflows", response_model=list[ApprovalRequestResponse])
def list_approval_requests_route(
    db: DbDependency,
    scope: str = "submitted",
    requestType: str | None = None,
    status: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_approval_requests(db, scope, requestType, status, authorization)


@router.get("/workflows/pending-counts", response_model=PendingApprovalCountsResponse)
def pending_approval_counts_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_pending_approval_counts(db, authorization)


@router.get("/workflows/configuration", response_model=list[WorkflowConfigurationResponse])
def list_workflow_configurations_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_workflow_configurations(db, authorization)


@router.put("/workflows/configuration/{request_type}", response_model=WorkflowConfigurationResponse)
def update_workflow_configuration_route(
    request_type: str,
    payload: WorkflowConfigurationUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_workflow_configuration(request_type, payload, db, authorization)


@router.post("/workflows", response_model=ApprovalRequestResponse)
def submit_approval_request_route(
    payload: ApprovalRequestCreate,
    background_tasks: BackgroundTasks,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return submit_approval_request(
        payload,
        db,
        authorization,
        lambda batch_id, user_id: background_tasks.add_task(run_import_job, batch_id, user_id),
    )


@router.get("/workflows/{request_id}", response_model=ApprovalRequestResponse)
def get_approval_request_route(
    request_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_approval_request(request_id, db, authorization)


@router.get("/workflows/{request_id}/history", response_model=list[ApprovalHistoryResponse])
def get_approval_history_route(
    request_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_approval_history(request_id, db, authorization)


@router.post("/workflows/{request_id}/submit", response_model=ApprovalRequestResponse)
def submit_draft_approval_request_route(
    request_id: int,
    background_tasks: BackgroundTasks,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return submit_draft_approval_request(
        request_id,
        db,
        authorization,
        lambda batch_id, user_id: background_tasks.add_task(run_import_job, batch_id, user_id),
    )


@router.post("/workflows/{request_id}/cancel", response_model=ApprovalRequestResponse)
def cancel_approval_request_route(
    request_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return cancel_approval_request(request_id, db, authorization)


@router.post("/workflows/{request_id}/decision", response_model=ApprovalRequestResponse)
def decide_approval_request_route(
    request_id: int,
    payload: ApprovalDecision,
    background_tasks: BackgroundTasks,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return decide_approval_request(
        request_id,
        payload,
        db,
        authorization,
        lambda batch_id, user_id: background_tasks.add_task(run_import_job, batch_id, user_id),
    )


@router.post("/workflows/{request_id}/approve", response_model=ApprovalRequestResponse)
def approve_request_route(
    request_id: int,
    payload: ApprovalAction,
    background_tasks: BackgroundTasks,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return decide_approval_request(
        request_id,
        ApprovalDecision(decision="approved", comment=payload.comment),
        db,
        authorization,
        lambda batch_id, user_id: background_tasks.add_task(run_import_job, batch_id, user_id),
    )


@router.post("/workflows/{request_id}/reject", response_model=ApprovalRequestResponse)
def reject_request_route(
    request_id: int,
    payload: ApprovalAction,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return decide_approval_request(
        request_id,
        ApprovalDecision(decision="rejected", comment=payload.comment),
        db,
        authorization,
    )
