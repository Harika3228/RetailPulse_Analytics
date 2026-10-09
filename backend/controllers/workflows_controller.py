import json
import math
import re
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import func, or_

from backend.auth_utils import get_current_user
from backend.cache import invalidate_forecast_cache
from backend.database import DbDependency
from backend.helpers import _ensure_admin, create_audit_log, create_notification
from backend.models import (
    ApprovalHistoryRecord,
    ApprovalRequestRecord,
    Company,
    Customer,
    ImportBatch,
    Product,
    StockAdjustment,
    StockMovement,
    User,
    WorkflowConfiguration,
)
from backend.schemas import ApprovalDecision, ApprovalRequestCreate, WorkflowConfigurationUpdate

ADMIN_ROLES = {"admin", "company_admin", "super_admin"}
REQUEST_STATUSES = {"draft", "submitted", "pending_approval", "approved", "rejected", "cancelled"}
REQUEST_TYPES = {
    "stock_adjustment",
    "product_deactivation",
    "product_price_change",
    "customer_information_change",
    "inventory_import_approval",
}
ALLOWED_TRANSITIONS = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"pending_approval", "approved", "cancelled"},
    "pending_approval": {"approved", "rejected", "cancelled"},
    "processing": {"approved", "rejected"},
    "approved": set(),
    "rejected": set(),
    "cancelled": set(),
}
CUSTOMER_CHANGE_FIELDS = {
    "name", "email", "phone", "dateOfBirth", "gender", "address", "city",
    "state", "country", "postalCode", "customerType", "preferredSalesChannel",
}


def _get_workflow_configuration(
    db: DbDependency,
    company_id: int,
    request_type: str,
    create: bool = True,
) -> WorkflowConfiguration | None:
    configuration = db.query(WorkflowConfiguration).filter(
        WorkflowConfiguration.companyId == company_id,
        WorkflowConfiguration.requestType == request_type,
    ).first()
    if configuration or not create:
        return configuration
    configuration = WorkflowConfiguration(
        companyId=company_id,
        requestType=request_type,
        approverRole="admin",
        approvalRequired=1,
        isActive=1,
        allowSelfApproval=0,
    )
    db.add(configuration)
    db.flush()
    return configuration


def _ensure_workflow_configurations(db: DbDependency, company_id: int) -> list[WorkflowConfiguration]:
    configurations = []
    for request_type in sorted(REQUEST_TYPES):
        configuration = _get_workflow_configuration(db, company_id, request_type)
        if configuration is None:
            raise HTTPException(status_code=500, detail="Unable to initialize workflow configuration")
        configurations.append(configuration)
    return configurations


def list_workflow_configurations(db: DbDependency, authorization: str | None) -> list[dict]:
    user = _get_user(db, authorization)
    _ensure_admin(user)
    configurations = _ensure_workflow_configurations(db, user.companyId)
    db.commit()
    return [_serialize_configuration(configuration) for configuration in configurations]


def _serialize_configuration(configuration: WorkflowConfiguration) -> dict:
    return {
        "requestType": configuration.requestType,
        "approverRole": configuration.approverRole,
        "approvalRequired": bool(configuration.approvalRequired),
        "isActive": bool(configuration.isActive),
        "allowSelfApproval": bool(configuration.allowSelfApproval) if configuration else False,
    }


def update_workflow_configuration(
    request_type: str,
    payload: WorkflowConfigurationUpdate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _get_user(db, authorization)
    _ensure_admin(user)
    if request_type not in REQUEST_TYPES:
        raise HTTPException(status_code=404, detail="Workflow request type not found")
    configuration = _get_workflow_configuration(db, user.companyId, request_type)
    if configuration is None:
        raise HTTPException(status_code=500, detail="Unable to initialize workflow configuration")
    previous = _serialize_configuration(configuration)
    configuration.approverRole = payload.approverRole
    configuration.approvalRequired = int(payload.approvalRequired)
    configuration.isActive = int(payload.isActive)
    configuration.allowSelfApproval = int(payload.allowSelfApproval)
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        user_id=user.id,
        company_id=user.companyId,
        action="Workflow Configuration Updated",
        resource_type="Workflow Configuration",
        resource_id=f"{user.companyId}:{request_type}",
        description=json.dumps({"before": previous, "after": _serialize_configuration(configuration)}),
        commit=False,
    )
    db.commit()
    db.refresh(configuration)
    return _serialize_configuration(configuration)


def _role_matches(user: User, approver_role: str) -> bool:
    if approver_role == "admin":
        return user.role in ADMIN_ROLES
    return user.role == approver_role


def _users_in_approver_role(db: DbDependency, company_id: int, approver_role: str):
    query = db.query(User).filter(User.companyId == company_id, User.status == "active")
    if approver_role == "admin":
        query = query.filter(User.role.in_(ADMIN_ROLES))
    else:
        query = query.filter(User.role == approver_role)
    return query.all()


def _can_review(db: DbDependency, user: User, request: ApprovalRequestRecord) -> bool:
    configuration = _get_workflow_configuration(db, user.companyId, request.requestType, create=False)
    allow_self = bool(configuration.allowSelfApproval) if configuration else False
    if request.requesterId == user.id:
        return allow_self and _role_matches(user, request.assignedApproverRole or "admin")
    return user.role in ADMIN_ROLES or _role_matches(user, request.assignedApproverRole or "admin")


def _related_entity(db: DbDependency, request_type: str, related_record: str, company_id: int):
    if request_type in {"stock_adjustment", "product_deactivation", "product_price_change"}:
        query = db.query(Product).filter(Product.companyId == company_id)
        entity = (
            query.filter(Product.id == int(related_record)).first()
            if related_record.isdigit()
            else query.filter(Product.sku == related_record).first()
        )
        if not entity:
            raise HTTPException(status_code=404, detail="Related product not found")
        return entity
    if request_type == "customer_information_change":
        query = db.query(Customer).filter(
            Customer.companyId == company_id,
            or_(Customer.isDeleted.is_(None), Customer.isDeleted == 0),
        )
        entity = (
            query.filter(Customer.id == int(related_record)).first()
            if related_record.isdigit()
            else query.filter(Customer.customerId == related_record).first()
        )
        if not entity:
            raise HTTPException(status_code=404, detail="Related customer not found")
        return entity
    if request_type == "inventory_import_approval":
        if not related_record.isdigit():
            raise HTTPException(status_code=422, detail="Related record must be an import batch ID")
        entity = db.query(ImportBatch).filter(
            ImportBatch.id == int(related_record),
            ImportBatch.companyId == company_id,
        ).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Related inventory import batch not found")
        return entity
    raise HTTPException(status_code=422, detail="Unsupported approval request type")


def _current_values(entity, request_type: str) -> dict:
    if request_type in {"stock_adjustment", "product_deactivation", "product_price_change"}:
        return {
            "id": entity.id,
            "sku": entity.sku,
            "name": entity.name,
            "stockQuantity": entity.stockQuantity,
            "unitPrice": entity.unitPrice,
            "status": entity.status,
        }
    if request_type == "customer_information_change":
        return {field: getattr(entity, field) for field in sorted(CUSTOMER_CHANGE_FIELDS)}
    return {
        "batchId": entity.id,
        "entityType": entity.entityType,
        "fileName": entity.fileName,
        "totalRows": entity.totalRows,
        "validCount": entity.validCount,
        "status": entity.status,
    }


def _get_user(db: DbDependency, authorization: str | None) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return get_current_user(db, authorization.split(" ", 1)[1])


def _serialize_request(db: DbDependency, request: ApprovalRequestRecord) -> dict:
    requester = db.query(User).filter(User.id == request.requesterId).first()
    reviewer = db.query(User).filter(User.id == request.reviewerId).first() if request.reviewerId else None
    history_rows = (
        db.query(ApprovalHistoryRecord)
        .filter(
            ApprovalHistoryRecord.requestId == request.id,
            ApprovalHistoryRecord.companyId == request.companyId,
        )
        .order_by(ApprovalHistoryRecord.createdAt.asc(), ApprovalHistoryRecord.id.asc())
        .all()
    )
    history = []
    for entry in history_rows:
        actor = db.query(User).filter(User.id == entry.actorId).first()
        history.append({
            "id": entry.id,
            "action": entry.action,
            "actorId": entry.actorId,
            "actorName": (actor.name or actor.email) if actor else "Former user",
            "comment": entry.comment or "",
            "createdAt": entry.createdAt,
        })
    try:
        details = json.loads(request.details or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Approval request details are invalid") from exc
    try:
        requested_changes = json.loads(request.requestedChanges or request.details or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Approval request changes are invalid") from exc
    company = db.query(Company).filter(Company.id == request.companyId).first()
    try:
        entity = _related_entity(db, request.requestType, request.relatedRecord, request.companyId)
        current_values = _current_values(entity, request.requestType)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        current_values = {}
    priority = "high" if request.requestType in {"stock_adjustment", "inventory_import_approval"} else "medium"
    configuration = _get_workflow_configuration(db, request.companyId, request.requestType, create=False)
    return {
        "id": request.id,
        "requestType": request.requestType,
        "title": request.title,
        "description": request.description,
        "reason": request.reason or request.description or "",
        "relatedRecord": request.relatedRecord or "General request",
        "requestedChanges": requested_changes,
        "currentValues": current_values,
        "priority": priority,
        "assignedApproverRole": request.assignedApproverRole or "admin",
        "allowSelfApproval": bool(configuration.allowSelfApproval) if configuration else False,
        "details": details,
        "status": "pending_approval" if request.status == "pending" else request.status,
        "companyId": request.companyId,
        "companyName": company.name if company else "Unknown company",
        "requesterId": request.requesterId,
        "requesterName": (requester.name or requester.email) if requester else "Former user",
        "requesterEmail": requester.email if requester else "",
        "reviewerId": request.reviewerId,
        "reviewerName": (reviewer.name or reviewer.email) if reviewer else None,
        "reviewerComment": request.reviewerComment,
        "createdAt": request.createdAt,
        "updatedAt": request.updatedAt,
        "history": history,
    }


def _record_audit(db: DbDependency, user: User, request: ApprovalRequestRecord, action: str, comment: str = "") -> None:
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        user_id=user.id,
        company_id=user.companyId,
        action=action,
        resource_type="Approval Request",
        resource_id=request.id,
        description=json.dumps({
            "requestType": request.requestType,
            "title": request.title,
            "status": request.status,
            "relatedRecord": request.relatedRecord,
            "requestedChanges": request.requestedChanges,
            "reason": request.reason,
            "comment": comment,
        }),
        commit=False,
    )


def _record_history_event(
    db: DbDependency,
    user: User,
    request: ApprovalRequestRecord,
    action: str,
    comment: str = "",
) -> None:
    db.add(ApprovalHistoryRecord(
        requestId=request.id,
        companyId=request.companyId,
        actorId=user.id,
        action=action,
        comment=comment,
        createdAt=datetime.now(timezone.utc),
    ))
    _record_audit(
        db,
        user,
        request,
        f"Approval Request {action.replace('_', ' ').title()}",
        comment,
    )


def list_approval_requests(
    db: DbDependency,
    scope: str,
    request_type: str | None,
    status: str | None,
    authorization: str | None,
) -> list[dict]:
    user = _get_user(db, authorization)
    if scope not in {"pending", "submitted", "drafts", "all"}:
        raise HTTPException(status_code=400, detail="Invalid workflow scope")
    if status == "pending":
        status = "pending_approval"
    if status and status not in REQUEST_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid approval status")
    if request_type and request_type not in REQUEST_TYPES:
        raise HTTPException(status_code=400, detail="Invalid approval request type")

    query = db.query(ApprovalRequestRecord).filter(
        ApprovalRequestRecord.companyId == user.companyId,
    )
    if scope == "pending":
        query = query.filter(ApprovalRequestRecord.status == "pending_approval")
        if user.role not in ADMIN_ROLES:
            query = query.filter(ApprovalRequestRecord.assignedApproverRole == user.role)
    elif scope == "drafts":
        query = query.filter(
            ApprovalRequestRecord.requesterId == user.id,
            ApprovalRequestRecord.status == "draft",
        )
    elif scope == "submitted":
        query = query.filter(
            ApprovalRequestRecord.requesterId == user.id,
            ApprovalRequestRecord.status != "draft",
        )
    elif scope == "all":
        _ensure_admin(user)
    elif user.role not in ADMIN_ROLES:
        query = query.filter(ApprovalRequestRecord.requesterId == user.id)
    if request_type:
        query = query.filter(ApprovalRequestRecord.requestType == request_type)
    if status:
        query = query.filter(ApprovalRequestRecord.status == status)
    requests = query.order_by(ApprovalRequestRecord.createdAt.desc(), ApprovalRequestRecord.id.desc()).all()
    return [_serialize_request(db, request) for request in requests]


def get_approval_history(
    request_id: int,
    db: DbDependency,
    authorization: str | None,
) -> list[dict]:
    user = _get_user(db, authorization)
    request = _get_accessible_request(db, request_id, user)
    history_rows = db.query(ApprovalHistoryRecord).filter(
        ApprovalHistoryRecord.requestId == request.id,
        ApprovalHistoryRecord.companyId == user.companyId,
    ).order_by(
        ApprovalHistoryRecord.createdAt.asc(),
        ApprovalHistoryRecord.id.asc(),
    ).all()
    history = []
    for entry in history_rows:
        actor = db.query(User).filter(
            User.id == entry.actorId,
            User.companyId == user.companyId,
        ).first()
        history.append({
            "id": entry.id,
            "action": entry.action,
            "actorId": entry.actorId,
            "actorName": (actor.name or actor.email) if actor else "Former user",
            "comment": entry.comment or "",
            "createdAt": entry.createdAt,
        })
    return history


def get_pending_approval_counts(db: DbDependency, authorization: str | None) -> dict:
    user = _get_user(db, authorization)
    query = db.query(
        ApprovalRequestRecord.requestType,
        func.count(ApprovalRequestRecord.id),
    ).filter(
        ApprovalRequestRecord.companyId == user.companyId,
        ApprovalRequestRecord.status == "pending_approval",
    )
    if user.role not in ADMIN_ROLES:
        query = query.filter(ApprovalRequestRecord.assignedApproverRole == user.role)
    counts_by_type = {
        request_type: count
        for request_type, count in query.group_by(ApprovalRequestRecord.requestType).all()
    }
    counts_by_type = {request_type: counts_by_type.get(request_type, 0) for request_type in sorted(REQUEST_TYPES)}
    return {
        "total": sum(counts_by_type.values()),
        "byRequestType": counts_by_type,
    }


def submit_approval_request(
    payload: ApprovalRequestCreate,
    db: DbDependency,
    authorization: str | None,
    schedule_import: Callable[[int, int], None] | None = None,
) -> dict:
    user = _get_user(db, authorization)
    configuration = _get_workflow_configuration(db, user.companyId, payload.requestType)
    if configuration is None:
        raise HTTPException(status_code=500, detail="Unable to initialize workflow configuration")
    if not configuration.isActive:
        raise HTTPException(status_code=409, detail="This workflow is inactive")
    now = datetime.now(timezone.utc)
    request = ApprovalRequestRecord(
        companyId=user.companyId,
        requesterId=user.id,
        requestType=payload.requestType,
        title=payload.title,
        description=payload.description,
        reason=payload.reason,
        relatedRecord=payload.relatedRecord,
        requestedChanges=json.dumps(payload.requestedChanges or {}),
        assignedApproverRole=configuration.approverRole,
        currentValues=json.dumps(_current_values(
            _related_entity(db, payload.requestType, payload.relatedRecord, user.companyId),
            payload.requestType,
        )),
        details=json.dumps(payload.details),
        status="draft",
        createdAt=now,
        updatedAt=now,
    )
    db.add(request)
    db.flush()
    _record_history_event(db, user, request, "created", "Request created")
    if payload.submit:
        try:
            _advance_submission(db, user, request, configuration, schedule_import)
        except Exception:
            db.rollback()
            raise
    else:
        _record_history_event(db, user, request, "draft", "Draft saved")
    db.commit()
    db.refresh(request)
    if payload.submit and not configuration.approvalRequired:
        _invalidate_forecast_cache_for_request(request)
    return _serialize_request(db, request)


def _advance_submission(
    db: DbDependency,
    user: User,
    request: ApprovalRequestRecord,
    configuration: WorkflowConfiguration,
    schedule_import: Callable[[int, int], None] | None,
) -> None:
    if not configuration.isActive:
        raise HTTPException(status_code=409, detail="This workflow is inactive")
    request.assignedApproverRole = configuration.approverRole
    _transition_request(db, user, request, "submitted")
    if configuration.approvalRequired:
        _transition_request(db, user, request, "pending_approval", "Awaiting authorized review")
        return
    _apply_requested_changes(db, user, request, schedule_import)
    _transition_request(db, user, request, "approved", "Approval is not required by workflow configuration")


def _transition_request(
    db: DbDependency,
    user: User,
    request: ApprovalRequestRecord,
    next_status: str,
    comment: str = "",
) -> None:
    current_status = "pending_approval" if request.status == "pending" else request.status
    if next_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition approval request from {current_status} to {next_status}",
        )

    now = datetime.now(timezone.utc)
    updated = db.query(ApprovalRequestRecord).filter(
        ApprovalRequestRecord.id == request.id,
        ApprovalRequestRecord.companyId == user.companyId,
        ApprovalRequestRecord.status == request.status,
    ).update(
        {
            ApprovalRequestRecord.status: next_status,
            ApprovalRequestRecord.updatedAt: now,
        },
        synchronize_session=False,
    )
    if not updated:
        db.rollback()
        raise HTTPException(status_code=409, detail="Approval request state changed; reload and try again")

    request.status = next_status
    request.updatedAt = now
    _record_history_event(db, user, request, next_status, comment)

    if next_status == "pending_approval":
        for approver in _users_in_approver_role(
            db,
            user.companyId,
            request.assignedApproverRole or "admin",
        ):
            create_notification(
                db,
                company_id=user.companyId,
                user_id=approver.id,
                message=f"{user.name or user.email} submitted {request.title} for your review.",
                notification_type="approval_request_assigned",
                title="Approval assigned",
                severity="info",
                priority="medium",
                resource_type="Approval Request",
                resource_id=request.id,
            )
    elif next_status == "submitted":
        create_notification(
            db,
            company_id=user.companyId,
            user_id=request.requesterId,
            message=f"Your request {request.title} was submitted.",
            notification_type="approval_request_submitted",
            title="Request submitted",
            severity="info",
            priority="low",
            resource_type="Approval Request",
            resource_id=request.id,
        )
    elif next_status in {"approved", "rejected"}:
        create_notification(
            db,
            company_id=user.companyId,
            user_id=request.requesterId,
            message=f"Your request {request.title} was {next_status}.",
            notification_type=f"approval_request_{next_status}",
            title=f"Request {next_status}",
            severity="success" if next_status == "approved" else "warning",
            priority="medium",
            resource_type="Approval Request",
            resource_id=request.id,
        )
    elif next_status == "cancelled":
        create_notification(
            db,
            company_id=user.companyId,
            user_id=request.requesterId,
            message=f"Your request {request.title} was cancelled.",
            notification_type="approval_request_cancelled",
            title="Request cancelled",
            severity="info",
            priority="low",
            resource_type="Approval Request",
            resource_id=request.id,
        )
        if current_status in {"submitted", "pending_approval"}:
            for approver in _users_in_approver_role(
                db,
                user.companyId,
                request.assignedApproverRole or "admin",
            ):
                if approver.id == user.id:
                    continue
                create_notification(
                    db,
                    company_id=user.companyId,
                    user_id=approver.id,
                    message=f"{user.name or user.email} cancelled {request.title}.",
                    notification_type="approval_request_cancelled",
                    title="Approval request cancelled",
                    severity="info",
                    priority="low",
                    resource_type="Approval Request",
                    resource_id=request.id,
                )


def _get_accessible_request(db: DbDependency, request_id: int, user: User) -> ApprovalRequestRecord:
    request = db.query(ApprovalRequestRecord).filter(
        ApprovalRequestRecord.id == request_id,
        ApprovalRequestRecord.companyId == user.companyId,
    ).first()
    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if request.requesterId != user.id and user.role not in ADMIN_ROLES and not _role_matches(user, request.assignedApproverRole or "admin"):
        raise HTTPException(status_code=403, detail="You cannot view this approval request")
    return request


def get_approval_request(request_id: int, db: DbDependency, authorization: str | None) -> dict:
    user = _get_user(db, authorization)
    request = _get_accessible_request(db, request_id, user)
    _record_history_event(db, user, request, "viewed", f"Request viewed by {user.name or user.email}")
    db.commit()
    return _serialize_request(db, request)


def submit_draft_approval_request(
    request_id: int,
    db: DbDependency,
    authorization: str | None,
    schedule_import: Callable[[int, int], None] | None = None,
) -> dict:
    user = _get_user(db, authorization)
    request = _get_accessible_request(db, request_id, user)
    if request.requesterId != user.id:
        raise HTTPException(status_code=403, detail="Only the requester can submit this draft")
    try:
        configuration = _get_workflow_configuration(db, user.companyId, request.requestType)
        if configuration is None:
            raise HTTPException(status_code=500, detail="Unable to initialize workflow configuration")
        _advance_submission(db, user, request, configuration, schedule_import)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(request)
    if not configuration.approvalRequired:
        _invalidate_forecast_cache_for_request(request)
    return _serialize_request(db, request)


def cancel_approval_request(request_id: int, db: DbDependency, authorization: str | None) -> dict:
    user = _get_user(db, authorization)
    request = _get_accessible_request(db, request_id, user)
    if request.requesterId != user.id:
        raise HTTPException(status_code=403, detail="Only the requester can cancel this request")
    try:
        _transition_request(db, user, request, "cancelled", "Cancelled by requester")
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(request)
    return _serialize_request(db, request)


def decide_approval_request(
    request_id: int,
    payload: ApprovalDecision,
    db: DbDependency,
    authorization: str | None,
    schedule_import: Callable[[int, int], None] | None = None,
) -> dict:
    user = _get_user(db, authorization)
    request = _get_accessible_request(db, request_id, user)
    if not _can_review(db, user, request):
        raise HTTPException(status_code=403, detail="You are not an assigned approver for this request")
    requester = db.query(User).filter(
        User.id == request.requesterId,
        User.companyId == request.companyId,
    ).first()
    if request.companyId != user.companyId or requester is None:
        raise HTTPException(status_code=409, detail="Approval request company context is invalid")
    comment = payload.comment.strip()
    if payload.decision == "rejected" and not comment:
        raise HTTPException(status_code=422, detail="A comment is required when rejecting a request")

    if request.status not in {"pending", "pending_approval"}:
        raise HTTPException(status_code=409, detail=f"Cannot review a request with status {request.status}")
    try:
        _claim_pending_request(db, user, request)
        if payload.decision == "approved":
            _apply_requested_changes(db, user, request, schedule_import)
        _transition_request(db, user, request, payload.decision, comment)
        request.reviewerId = user.id
        request.reviewerComment = comment
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(request)
    if payload.decision == "approved":
        _invalidate_forecast_cache_for_request(request)
    return _serialize_request(db, request)


def _claim_pending_request(db: DbDependency, user: User, request: ApprovalRequestRecord) -> None:
    pending_status = request.status
    updated = db.query(ApprovalRequestRecord).filter(
        ApprovalRequestRecord.id == request.id,
        ApprovalRequestRecord.companyId == user.companyId,
        ApprovalRequestRecord.requesterId == request.requesterId,
        ApprovalRequestRecord.status == pending_status,
    ).update(
        {ApprovalRequestRecord.status: "processing"},
        synchronize_session=False,
    )
    if updated != 1:
        raise HTTPException(status_code=409, detail="Approval request is no longer pending; reload and try again")
    request.status = "processing"


def _invalidate_forecast_cache_for_request(request: ApprovalRequestRecord) -> None:
    if request.requestType in {"stock_adjustment", "product_price_change", "product_deactivation"}:
        invalidate_forecast_cache(request.companyId)


def _apply_requested_changes(
    db: DbDependency,
    reviewer: User,
    request: ApprovalRequestRecord,
    schedule_import: Callable[[int, int], None] | None,
) -> None:
    if reviewer.companyId != request.companyId:
        raise HTTPException(status_code=404, detail="Approval request not found")
    entity = _related_entity(db, request.requestType, request.relatedRecord, request.companyId)
    try:
        proposed = json.loads(request.requestedChanges or "{}")
        original = json.loads(request.currentValues or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Approval request data is invalid") from exc
    current = _current_values(entity, request.requestType)
    if original and any(current.get(key) != value for key, value in original.items()):
        raise HTTPException(status_code=409, detail="The related record changed after this request was submitted; cancel and resubmit")

    now = datetime.now(timezone.utc)
    if request.requestType == "stock_adjustment":
        new_quantity = proposed.get("stockQuantity")
        if isinstance(new_quantity, bool) or not isinstance(new_quantity, int) or new_quantity < 0:
            raise HTTPException(status_code=422, detail="Requested changes must include a non-negative integer stockQuantity")
        previous_quantity = int(entity.stockQuantity or 0)
        difference = new_quantity - previous_quantity
        if difference == 0:
            raise HTTPException(status_code=422, detail="Requested stock must differ from current stock")
        entity.stockQuantity = new_quantity
        entity.updatedAt = now
        db.add(StockAdjustment(
            companyId=reviewer.companyId,
            productId=entity.id,
            adjustmentType="manual_adjustment",
            quantity=abs(difference),
            reason=request.reason,
            remarks=f"Approved workflow request #{request.id}",
            adjustedBy=reviewer.email,
            adjustedByUserId=reviewer.id,
            adjustmentDate=now,
        ))
        db.add(StockMovement(
            companyId=reviewer.companyId,
            productId=entity.id,
            productName=entity.name,
            sku=entity.sku,
            movementType="manual_adjustment",
            previousQuantity=previous_quantity,
            updatedQuantity=new_quantity,
            quantityChanged=difference,
            actor=reviewer.email,
            actorUserId=reviewer.id,
            reference=f"Approval Request #{request.id}: {request.reason}",
            createdAt=now,
        ))
        _record_history_event(
            db,
            reviewer,
            request,
            "inventory_updated",
            f"Stock changed from {previous_quantity} to {new_quantity} ({difference:+d}).",
        )
    elif request.requestType == "product_price_change":
        price = proposed.get("unitPrice")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise HTTPException(status_code=422, detail="Requested changes must include a positive unitPrice")
        before = entity.unitPrice
        entity.unitPrice = float(price)
        entity.price = str(price)
        entity.updatedAt = now
        _record_business_change(db, reviewer, request, "Product Price Change", entity.name, "Product", entity.id, before, price)
    elif request.requestType == "product_deactivation":
        if proposed.get("status") != "inactive":
            raise HTTPException(status_code=422, detail="Product deactivation must request status 'inactive'")
        if entity.status != "active":
            raise HTTPException(status_code=409, detail="Only active products can be deactivated")
        entity.status = "inactive"
        entity.updatedAt = now
        _record_business_change(db, reviewer, request, "Product Deactivation", entity.name, "Product", entity.id, "active", "inactive")
    elif request.requestType == "customer_information_change":
        changes = {key: value for key, value in proposed.items() if key in CUSTOMER_CHANGE_FIELDS}
        if not changes or len(changes) != len(proposed):
            raise HTTPException(status_code=422, detail="Customer changes contain unsupported fields")
        for field, value in changes.items():
            if value is not None and not isinstance(value, str):
                raise HTTPException(status_code=422, detail=f"Customer field {field} must be text")
            if isinstance(value, str) and len(value) > 500:
                raise HTTPException(status_code=422, detail=f"Customer field {field} is too long")
        email = changes.get("email")
        if email is not None and (not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()) or len(email) > 255):
            raise HTTPException(status_code=422, detail="A valid customer email is required")
        if "name" in changes and not (changes["name"] or "").strip():
            raise HTTPException(status_code=422, detail="Customer name cannot be blank")
        for field in ("email", "phone"):
            value = changes.get(field)
            if value:
                normalized_value = value.strip()
                duplicate_value = (
                    func.lower(Customer.email) == normalized_value.lower()
                    if field == "email"
                    else Customer.phone == normalized_value
                )
                duplicate = db.query(Customer).filter(
                    Customer.companyId == reviewer.companyId,
                    or_(Customer.isDeleted.is_(None), Customer.isDeleted == 0),
                    duplicate_value,
                    Customer.id != entity.id,
                ).first()
                if duplicate:
                    raise HTTPException(status_code=409, detail=f"Another customer already uses this {field}")
        before = {field: getattr(entity, field) for field in changes}
        for field, value in changes.items():
            setattr(entity, field, value.strip() if isinstance(value, str) else value)
        db.add(entity)
        _record_business_change(db, reviewer, request, "Customer Information Change", entity.name, "Customer", entity.id, before, changes)
    elif request.requestType == "inventory_import_approval":
        batch = entity
        if batch.entityType != "inventory" or batch.status not in {"uploaded", "pending"}:
            raise HTTPException(status_code=409, detail="Only staged inventory import batches can be approved")
        if proposed.get("importBatchId") is not None and str(proposed["importBatchId"]) != str(batch.id):
            raise HTTPException(status_code=422, detail="Requested import batch does not match the related record")
        if schedule_import is None:
            raise HTTPException(status_code=500, detail="Inventory import approval processing is unavailable")
        batch.status = "queued"
        batch.processedCount = 0
        batch.cancelRequested = 0
        batch.failureMessage = None
        batch.startedAt = None
        batch.completedAt = None
        batch.durationSeconds = None
        db.add(batch)
        db.flush()
        schedule_import(batch.id, reviewer.id)
        _record_history_event(
            db,
            reviewer,
            request,
            "inventory_import_queued",
            f"Inventory import batch {batch.id} was queued for processing.",
        )


def _record_business_change(
    db: DbDependency,
    user: User,
    request: ApprovalRequestRecord,
    action: str,
    entity_name: str,
    resource_type: str,
    resource_id: int,
    before,
    after,
) -> None:
    _record_history_event(
        db,
        user,
        request,
        "business_record_updated",
        f"{action}: {json.dumps({'before': before, 'after': after})}",
    )
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        user_id=user.id,
        company_id=user.companyId,
        action=action,
        entity_name=entity_name,
        resource_type=resource_type,
        resource_id=resource_id,
        description=json.dumps({"before": before, "after": after}),
        commit=False,
    )
