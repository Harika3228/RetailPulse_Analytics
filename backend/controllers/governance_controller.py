import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, or_

from backend.access_control import (
    ADMIN_ROLE_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    ROLE_PERMISSION_ACTIONS,
    ROLE_PERMISSION_MODULES,
    effective_role_permissions,
)
from backend.auth_utils import get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, create_audit_log
from backend.models import (
    AccessReviewRecord,
    ApprovalRequestRecord,
    AuditLog,
    RolePermissionConfiguration,
    User,
)
from backend.schemas import (
    AccessReviewCreate,
    AccessReviewWorkflowCreate,
    ApprovalRequestCreate,
    GovernanceUserAccessUpdate,
    RolePermissionUpdate,
)

ELEVATED_ROLES = {"admin", "company_admin", "super_admin"}
PENDING_ACCESS_STATUSES = {"submitted", "pending_approval"}


def _normalize_role(role: str) -> str:
    return role.strip().lower().replace(" ", "_")


def _default_role_permissions(role: str) -> dict[str, list[str]]:
    normalized = _normalize_role(role)
    if normalized in ELEVATED_ROLES:
        return {module: list(actions) for module, actions in ADMIN_ROLE_PERMISSIONS.items()}
    configured = DEFAULT_ROLE_PERMISSIONS.get(normalized, {})
    return {
        module: sorted(configured.get(module, []))
        for module in ROLE_PERMISSION_MODULES
    }


def _get_admin(db: DbDependency, authorization: str | None):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_admin(user)
    return user


def get_governance_overview(
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _get_admin(db, authorization)
    company_id = user.companyId
    total_users = db.query(func.count(User.id)).filter(
        User.companyId == company_id
    ).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(
        User.companyId == company_id,
        func.lower(User.status) == "active",
    ).scalar() or 0
    total_roles = db.query(func.count(func.distinct(func.lower(User.role)))).filter(
        User.companyId == company_id,
        User.role.isnot(None),
        func.trim(User.role) != "",
    ).scalar() or 0
    elevated_users = db.query(func.count(User.id)).filter(
        User.companyId == company_id,
        func.lower(User.role).in_(ELEVATED_ROLES),
    ).scalar() or 0
    access_request_type = or_(
        func.lower(ApprovalRequestRecord.requestType).like("%access%"),
        func.lower(ApprovalRequestRecord.requestType).like("%permission%"),
        func.lower(ApprovalRequestRecord.requestType).like("%role%"),
    )
    pending_access_requests = db.query(func.count(ApprovalRequestRecord.id)).filter(
        ApprovalRequestRecord.companyId == company_id,
        access_request_type,
        func.lower(ApprovalRequestRecord.status).in_(PENDING_ACCESS_STATUSES),
    ).scalar() or 0

    permission_change_action = or_(
        func.lower(AuditLog.action).like("%permission%"),
        func.lower(AuditLog.action).like("%role%"),
        and_(
            func.lower(AuditLog.action).like("%access%"),
            ~func.lower(AuditLog.action).like("%review%"),
        ),
    )
    permission_changes = (
        db.query(AuditLog, User.name, User.email)
        .outerjoin(User, AuditLog.userId == User.id)
        .filter(
            AuditLog.companyId == company_id,
            permission_change_action,
        )
        .order_by(AuditLog.createdAt.desc(), AuditLog.id.desc())
        .limit(10)
        .all()
    )
    last_access_review = db.query(func.max(AuditLog.createdAt)).filter(
        AuditLog.companyId == company_id,
        or_(
            func.lower(AuditLog.action).like("%access review%"),
            func.lower(AuditLog.action).like("%permission review%"),
        ),
    ).scalar()

    return {
        "totalUsers": int(total_users),
        "activeUsers": int(active_users),
        "inactiveUsers": max(0, int(total_users) - int(active_users)),
        "totalRoles": int(total_roles),
        "pendingAccessRequests": int(pending_access_requests),
        "elevatedPermissionUsers": int(elevated_users),
        "recentPermissionChanges": [
            _serialize_permission_change(entry, actor_name, actor_email)
            for entry, actor_name, actor_email in permission_changes
        ],
        "lastAccessReviewAt": last_access_review,
    }


def _serialize_permission_change(entry: AuditLog, actor_name: str | None, actor_email: str | None) -> dict:
    details: dict = {}
    try:
        decoded = json.loads(entry.description or "")
        if isinstance(decoded, dict):
            details = decoded
    except json.JSONDecodeError:
        pass
    return {
        "id": entry.id,
        "action": entry.action or "Permission change",
        "actor": actor_name or actor_email or entry.user or "Unknown user",
        "target": details.get("targetEmail") or details.get("role") or entry.resourceId,
        "previous": details.get("before"),
        "newValue": details.get("after"),
        "reason": details.get("reason"),
        "relatedRequestId": details.get("requestId"),
        "resourceType": entry.resourceType,
        "timestamp": entry.createdAt or entry.timestamp,
        "description": entry.description or entry.action or "",
    }


def get_role_permission_matrix(
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _get_admin(db, authorization)
    observed_roles = {
        _normalize_role(role)
        for (role,) in db.query(User.role).filter(
            User.companyId == user.companyId,
            User.role.isnot(None),
            func.trim(User.role) != "",
        ).distinct().all()
    }
    roles = sorted(
        observed_roles | {"admin", "company_admin", "super_admin", "analyst", "viewer"}
    )
    rows = db.query(RolePermissionConfiguration).filter(
        RolePermissionConfiguration.companyId == user.companyId,
        RolePermissionConfiguration.role.in_(roles),
    ).all()
    configurations = {row.role: row for row in rows}
    matrix: dict[str, dict[str, list[str]]] = {}
    latest_updated_at = None
    for role in roles:
        row = configurations.get(role)
        if role in ELEVATED_ROLES or row is None:
            matrix[role] = _default_role_permissions(role)
        else:
            try:
                parsed_permissions = json.loads(row.permissions or "{}")
            except (TypeError, json.JSONDecodeError) as error:
                raise HTTPException(
                    status_code=500,
                    detail="Stored role permission configuration is invalid",
                ) from error
            matrix[role] = {
                module: sorted(parsed_permissions.get(module, []))
                for module in ROLE_PERMISSION_MODULES
            }
        if row and row.updatedAt and (
            latest_updated_at is None or row.updatedAt > latest_updated_at
        ):
            latest_updated_at = row.updatedAt
    return {
        "roles": roles,
        "modules": list(ROLE_PERMISSION_MODULES),
        "actions": list(ROLE_PERMISSION_ACTIONS),
        "permissions": matrix,
        "updatedAt": latest_updated_at,
    }


def list_governance_roles(db: DbDependency, authorization: str | None) -> dict:
    return get_role_permission_matrix(db, authorization)


def list_access_request_history(
    db: DbDependency,
    authorization: str | None,
    scope: str,
    status: str | None,
) -> list[dict]:
    from backend.controllers.workflows_controller import list_approval_requests

    return list_approval_requests(
        db,
        scope,
        "role_access_change",
        status,
        authorization,
    )


def list_permission_change_history(
    db: DbDependency,
    authorization: str | None,
    target_user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    admin = _get_admin(db, authorization)
    permission_change_actions = {
        "User Access Assignment Updated",
        "Access Request Approved",
        "Role Permissions Updated",
        "User Role Changed",
        "User Status Changed",
    }
    query = db.query(AuditLog, User.name, User.email).outerjoin(
        User, AuditLog.userId == User.id
    ).filter(
        AuditLog.companyId == admin.companyId,
        AuditLog.action.in_(permission_change_actions),
    )
    if target_user_id is not None:
        target = db.query(User.id).filter(
            User.id == target_user_id,
            User.companyId == admin.companyId,
        ).first()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        query = query.filter(
            AuditLog.resourceType == "User Access Assignment",
            AuditLog.resourceId == str(target_user_id),
        )
    entries = query.order_by(
        AuditLog.createdAt.desc(),
        AuditLog.id.desc(),
    ).offset(offset).limit(limit).all()
    return [
        _serialize_permission_change(entry, actor_name, actor_email)
        for entry, actor_name, actor_email in entries
    ]


def update_role_permissions(
    role: str,
    payload: RolePermissionUpdate,
    db: DbDependency,
    authorization: str | None,
) -> None:
    user = _get_admin(db, authorization)
    normalized_role = _normalize_role(role)
    if normalized_role in ELEVATED_ROLES:
        raise HTTPException(
            status_code=409,
            detail="Built-in administrator roles retain immutable full access",
        )
    known_roles = {
        _normalize_role(row[0])
        for row in db.query(User.role).filter(
            User.companyId == user.companyId,
            User.role.isnot(None),
            func.trim(User.role) != "",
        ).distinct().all()
    }
    known_roles.update({"analyst", "viewer"})
    if normalized_role not in known_roles:
        raise HTTPException(status_code=404, detail="Role not found for this company")

    if set(payload.permissions) != set(ROLE_PERMISSION_MODULES):
        raise HTTPException(
            status_code=422,
            detail="Permissions must include exactly the supported application modules",
        )
    normalized_permissions: dict[str, list[str]] = {}
    for module, actions in payload.permissions.items():
        if len(actions) != len(set(actions)) or set(actions) - set(ROLE_PERMISSION_ACTIONS):
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported or duplicate permission action for module '{module}'",
            )
        normalized_permissions[module] = sorted(actions)

    configuration = db.query(RolePermissionConfiguration).filter(
        RolePermissionConfiguration.companyId == user.companyId,
        RolePermissionConfiguration.role == normalized_role,
    ).first()
    try:
        before_permissions = (
            json.loads(configuration.permissions or "{}")
            if configuration is not None
            else _default_role_permissions(normalized_role)
        )
    except (TypeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Stored role permission configuration is invalid",
        ) from error
    if configuration is None:
        configuration = RolePermissionConfiguration(
            companyId=user.companyId,
            role=normalized_role,
        )
        db.add(configuration)
    configuration.permissions = json.dumps(
        normalized_permissions,
        separators=(",", ":"),
    )
    configuration.updatedByUserId = user.id
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Role Permissions Updated",
        entity_name=normalized_role,
        resource_type="RolePermissionConfiguration",
        resource_id=normalized_role,
        description=json.dumps({
            "role": normalized_role,
            "before": before_permissions,
            "after": normalized_permissions,
            "reason": payload.reason,
        }),
        company_id=user.companyId,
        user_id=user.id,
        commit=False,
    )
    db.commit()


def _company_roles(db: DbDependency, company_id: int) -> set[str]:
    roles = {
        _normalize_role(row[0])
        for row in db.query(User.role).filter(
            User.companyId == company_id,
            User.role.isnot(None),
            func.trim(User.role) != "",
        ).distinct().all()
    }
    roles.update({"admin", "company_admin", "super_admin", "analyst", "viewer"})
    roles.update(
        _normalize_role(row[0])
        for row in db.query(RolePermissionConfiguration.role).filter(
            RolePermissionConfiguration.companyId == company_id,
        ).all()
        if row[0]
    )
    return roles


def _permissions_for_role(db: DbDependency, company_id: int, role: str) -> dict[str, list[str]]:
    return effective_role_permissions(db, company_id, role)


def list_governance_users(db: DbDependency, authorization: str | None) -> list[dict]:
    admin = _get_admin(db, authorization)
    users = db.query(User).filter(User.companyId == admin.companyId).order_by(User.name, User.id).all()
    result = []
    for managed_user in users:
        latest_access_audit = db.query(AuditLog).filter(
            AuditLog.companyId == admin.companyId,
            AuditLog.resourceType == "User Access Assignment",
            AuditLog.resourceId == str(managed_user.id),
        ).order_by(AuditLog.createdAt.desc(), AuditLog.id.desc()).first()
        actor = db.query(User).filter(
            User.id == latest_access_audit.userId,
            User.companyId == admin.companyId,
        ).first() if latest_access_audit and latest_access_audit.userId else None
        normalized_role = _normalize_role(managed_user.role or "viewer")
        result.append({
            "id": managed_user.id,
            "name": managed_user.name or managed_user.email,
            "email": managed_user.email,
            "role": normalized_role,
            "status": (managed_user.status or "active").lower(),
            "permissions": _permissions_for_role(db, admin.companyId, normalized_role),
            "accessUpdatedAt": latest_access_audit.createdAt if latest_access_audit else None,
            "accessUpdatedBy": (actor.name or actor.email) if actor else (
                latest_access_audit.user if latest_access_audit else None
            ),
        })
    return result


def update_governance_user_access(
    target_user_id: int,
    payload: GovernanceUserAccessUpdate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    admin = _get_admin(db, authorization)
    target = db.query(User).filter(
        User.id == target_user_id,
        User.companyId == admin.companyId,
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=409, detail="Administrators cannot change their own access")

    current_role = _normalize_role(target.role or "viewer")
    requested_role = _normalize_role(payload.role)
    if requested_role not in _company_roles(db, admin.companyId):
        raise HTTPException(status_code=422, detail="Role is not configured for this company")
    if (current_role in ELEVATED_ROLES or requested_role in ELEVATED_ROLES) and _normalize_role(admin.role) != "super_admin":
        raise HTTPException(status_code=403, detail="Only a super administrator can change administrator access")
    removing_last_admin = (
        current_role in ELEVATED_ROLES
        and (payload.status == "inactive" or requested_role not in ELEVATED_ROLES)
    )
    if removing_last_admin:
        active_admin_count = db.query(func.count(User.id)).filter(
            User.companyId == admin.companyId,
            func.lower(User.status) == "active",
            func.lower(User.role).in_(ELEVATED_ROLES),
        ).scalar() or 0
        if active_admin_count <= 1 and (target.status or "active").lower() == "active":
            raise HTTPException(status_code=409, detail="The company's last active administrator cannot be removed")

    before = {"role": target.role, "status": target.status or "active"}
    target.role = requested_role
    target.status = payload.status
    create_audit_log(
        db,
        company=str(admin.companyId),
        user=admin.email,
        user_id=admin.id,
        company_id=admin.companyId,
        action="User Access Assignment Updated",
        resource_type="User Access Assignment",
        resource_id=str(target.id),
        description=json.dumps({
            "targetUserId": target.id,
            "targetEmail": target.email,
            "before": before,
            "after": {"role": requested_role, "status": payload.status},
            "reason": payload.reason,
        }),
        commit=False,
    )
    db.commit()
    db.refresh(target)
    return {
        "id": target.id,
        "name": target.name or target.email,
        "email": target.email,
        "role": requested_role,
        "status": payload.status,
        "permissions": _permissions_for_role(db, admin.companyId, requested_role),
        "accessUpdatedAt": datetime.now(timezone.utc),
        "accessUpdatedBy": admin.name or admin.email,
    }


def _serialize_access_review(
    db: DbDependency,
    record: AccessReviewRecord,
    company_id: int,
) -> dict:
    target = db.query(User).filter(
        User.id == record.targetUserId,
        User.companyId == company_id,
    ).first()
    reviewer = db.query(User).filter(
        User.id == record.reviewerId,
        User.companyId == company_id,
    ).first()
    if target is None or reviewer is None:
        raise HTTPException(status_code=500, detail="Access review references an invalid company user")
    try:
        flagged_permissions = json.loads(record.flaggedPermissions or "[]")
    except (TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Stored access review data is invalid") from error
    return {
        "id": record.id,
        "userId": target.id,
        "userName": target.name or target.email,
        "reviewerId": reviewer.id,
        "reviewerName": reviewer.name or reviewer.email,
        "status": record.status,
        "comment": record.comment or "",
        "flaggedPermissions": flagged_permissions,
        "createdAt": record.createdAt,
    }


def list_access_reviews(db: DbDependency, authorization: str | None) -> list[dict]:
    admin = _get_admin(db, authorization)
    users = db.query(User).filter(
        User.companyId == admin.companyId,
    ).order_by(User.name, User.id).all()
    latest_by_user: dict[int, AccessReviewRecord] = {}
    for record in db.query(AccessReviewRecord).filter(
        AccessReviewRecord.companyId == admin.companyId,
    ).order_by(AccessReviewRecord.createdAt.desc(), AccessReviewRecord.id.desc()).all():
        latest_by_user.setdefault(record.targetUserId, record)
    result = []
    for target in users:
        latest = latest_by_user.get(target.id)
        latest_audit = db.query(AuditLog).filter(
            AuditLog.companyId == admin.companyId,
            AuditLog.resourceType == "User Access Assignment",
            AuditLog.resourceId == str(target.id),
        ).order_by(AuditLog.createdAt.desc(), AuditLog.id.desc()).first()
        role_configuration = db.query(RolePermissionConfiguration).filter(
            RolePermissionConfiguration.companyId == admin.companyId,
            RolePermissionConfiguration.role == _normalize_role(target.role or "viewer"),
        ).first()
        access_updated_at = latest_audit.createdAt if latest_audit else None
        if role_configuration and role_configuration.updatedAt and (
            access_updated_at is None or role_configuration.updatedAt > access_updated_at
        ):
            access_updated_at = role_configuration.updatedAt
        reviewer = None
        if latest:
            reviewer = db.query(User).filter(
                User.id == latest.reviewerId,
                User.companyId == admin.companyId,
            ).first()
        try:
            flagged_permissions = json.loads(latest.flaggedPermissions or "[]") if latest else []
        except (TypeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=500, detail="Stored access review data is invalid") from error
        result.append({
            "userId": target.id,
            "userName": target.name or target.email,
            "userEmail": target.email,
            "role": _normalize_role(target.role or "viewer"),
            "permissions": _permissions_for_role(
                db, admin.companyId, _normalize_role(target.role or "viewer")
            ),
            "lastAccessUpdatedAt": access_updated_at,
            "reviewStatus": latest.status if latest else None,
            "reviewedBy": (reviewer.name or reviewer.email) if reviewer else None,
            "reviewDate": latest.createdAt if latest else None,
            "reviewComment": latest.comment if latest else None,
            "flaggedPermissions": flagged_permissions,
        })
    return result


def list_access_review_history(
    db: DbDependency,
    authorization: str | None,
    target_user_id: int | None = None,
) -> list[dict]:
    admin = _get_admin(db, authorization)
    query = db.query(AccessReviewRecord).filter(
        AccessReviewRecord.companyId == admin.companyId,
    )
    if target_user_id is not None:
        target = db.query(User.id).filter(
            User.id == target_user_id,
            User.companyId == admin.companyId,
        ).first()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        query = query.filter(AccessReviewRecord.targetUserId == target_user_id)
    records = query.order_by(
        AccessReviewRecord.createdAt.desc(),
        AccessReviewRecord.id.desc(),
    ).all()
    return [
        _serialize_access_review(db, record, admin.companyId)
        for record in records
    ]


def create_access_review(
    target_user_id: int,
    payload: AccessReviewCreate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    admin = _get_admin(db, authorization)
    target = db.query(User).filter(
        User.id == target_user_id,
        User.companyId == admin.companyId,
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    assigned_permissions = _permissions_for_role(
        db,
        admin.companyId,
        _normalize_role(target.role or "viewer"),
    )
    for permission in payload.flaggedPermissions:
        parts = permission.split(":")
        if (
            len(parts) != 2
            or parts[0] not in ROLE_PERMISSION_MODULES
            or parts[1] not in ROLE_PERMISSION_ACTIONS
            or parts[1] not in assigned_permissions.get(parts[0], [])
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Flagged permission '{permission}' is not assigned to this user",
            )
    record = AccessReviewRecord(
        companyId=admin.companyId,
        targetUserId=target.id,
        reviewerId=admin.id,
        status=payload.status,
        comment=payload.comment.strip(),
        flaggedPermissions=json.dumps(sorted(set(payload.flaggedPermissions))),
        createdAt=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    create_audit_log(
        db,
        company=str(admin.companyId),
        user=admin.email,
        user_id=admin.id,
        company_id=admin.companyId,
        action="Access Review Flagged" if payload.status == "flagged" else "Access Review Completed",
        resource_type="Access Review",
        resource_id=str(target.id),
        description=json.dumps({
            "reviewId": record.id,
            "targetUserId": target.id,
            "status": payload.status,
            "comment": payload.comment.strip(),
            "flaggedPermissions": sorted(set(payload.flaggedPermissions)),
        }),
        commit=False,
    )
    db.commit()
    db.refresh(record)
    return _serialize_access_review(db, record, admin.companyId)


def initiate_access_review_workflow(
    target_user_id: int,
    payload: AccessReviewWorkflowCreate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    admin = _get_admin(db, authorization)
    target = db.query(User).filter(
        User.id == target_user_id,
        User.companyId == admin.companyId,
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    requested_changes: dict[str, str] = {}
    if payload.role is not None:
        requested_role = _normalize_role(payload.role)
        if requested_role not in _company_roles(db, admin.companyId):
            raise HTTPException(status_code=422, detail="Role is not configured for this company")
        if (
            _normalize_role(target.role) in ELEVATED_ROLES
            or requested_role in ELEVATED_ROLES
        ) and _normalize_role(admin.role) != "super_admin":
            raise HTTPException(status_code=403, detail="Only a super administrator can request administrator access changes")
        requested_changes["role"] = requested_role
    if payload.status is not None:
        if (
            _normalize_role(target.role) in ELEVATED_ROLES
            and _normalize_role(admin.role) != "super_admin"
        ):
            raise HTTPException(status_code=403, detail="Only a super administrator can request administrator access changes")
        requested_changes["status"] = payload.status
    from backend.controllers.workflows_controller import submit_approval_request

    return submit_approval_request(
        ApprovalRequestCreate(
            requestType="role_access_change",
            relatedRecord=str(target.id),
            requestedChanges=requested_changes,
            reason=payload.reason,
            title=f"Access review change for {target.name or target.email}",
            details={"initiatedFromAccessReview": True, "targetUserId": target.id},
        ),
        db,
        authorization,
    )
