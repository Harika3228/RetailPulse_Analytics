from fastapi import APIRouter, Header, Query

from backend.controllers.governance_controller import (
    create_access_review,
    get_governance_overview,
    initiate_access_review_workflow,
    list_access_request_history,
    list_access_review_history,
    list_access_reviews,
    get_role_permission_matrix,
    list_governance_roles,
    list_permission_change_history,
    list_governance_users,
    update_role_permissions,
    update_governance_user_access,
)
from backend.database import DbDependency
from backend.schemas import (
    AccessReviewCreate,
    AccessReviewHistoryResponse,
    AccessReviewResponse,
    AccessReviewWorkflowCreate,
    ApprovalRequestResponse,
    GovernanceOverviewResponse,
    GovernancePermissionChangeResponse,
    GovernanceUserAccessUpdate,
    GovernanceUserResponse,
    RolePermissionMatrixResponse,
    RolePermissionUpdate,
)

router = APIRouter(prefix="/governance", tags=["data-governance"])


@router.get(
    "/roles",
    response_model=RolePermissionMatrixResponse,
    summary="List company roles and effective permissions",
)
def governance_roles_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_governance_roles(db, authorization)


@router.get(
    "/access-requests",
    response_model=list[ApprovalRequestResponse],
    summary="List access request history",
    description=(
        "Company administrators can use scope=all; individual users can retrieve "
        "their own submitted requests with scope=submitted."
    ),
)
def access_request_history_route(
    db: DbDependency,
    scope: str = "submitted",
    status: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_access_request_history(db, authorization, scope, status)


@router.get(
    "/permission-changes",
    response_model=list[GovernancePermissionChangeResponse],
    summary="Retrieve immutable permission change history",
)
def permission_change_history_route(
    db: DbDependency,
    userId: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_permission_change_history(
        db,
        authorization,
        userId,
        limit,
        offset,
    )


@router.get(
    "/access-reviews",
    response_model=list[AccessReviewResponse],
    summary="List company user access for periodic review",
)
def access_reviews_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_access_reviews(db, authorization)


@router.get(
    "/access-reviews/history",
    response_model=list[AccessReviewHistoryResponse],
    summary="List immutable access review history",
)
def access_review_history_route(
    db: DbDependency,
    userId: int | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_access_review_history(db, authorization, userId)


@router.post(
    "/access-reviews/{user_id}",
    response_model=AccessReviewHistoryResponse,
    summary="Record an access review decision",
)
def create_access_review_route(
    user_id: int,
    payload: AccessReviewCreate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return create_access_review(user_id, payload, db, authorization)


@router.post(
    "/access-reviews/{user_id}/workflow",
    response_model=ApprovalRequestResponse,
    summary="Initiate an approval workflow for an access change",
)
def access_review_workflow_route(
    user_id: int,
    payload: AccessReviewWorkflowCreate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return initiate_access_review_workflow(user_id, payload, db, authorization)


@router.get(
    "/users",
    response_model=list[GovernanceUserResponse],
    summary="List company user access assignments",
)
def governance_users_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_governance_users(db, authorization)


@router.patch(
    "/users/{user_id}/access",
    response_model=GovernanceUserResponse,
    summary="Update a company user's role and access status",
)
def update_governance_user_access_route(
    user_id: int,
    payload: GovernanceUserAccessUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_governance_user_access(user_id, payload, db, authorization)


@router.get(
    "/overview",
    response_model=GovernanceOverviewResponse,
    summary="Get data governance overview",
    description=(
        "Returns company-scoped user, assigned-role, pending access/role approval, "
        "elevated-role, recent permission audit, and access-review metrics. "
        "Requires an authenticated administrator."
    ),
)
def governance_overview_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_governance_overview(db, authorization)


@router.get(
    "/roles/permissions",
    response_model=RolePermissionMatrixResponse,
    summary="Get company role permission matrix",
    description="Returns configured module permissions for this company's roles. Requires an administrator.",
)
def role_permission_matrix_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_role_permission_matrix(db, authorization)


@router.put(
    "/roles/{role}/permissions",
    response_model=RolePermissionMatrixResponse,
    summary="Update a role's configured permissions",
    description="Updates a non-administrator role's company-scoped permission matrix and records an audit event.",
)
def update_role_permissions_route(
    role: str,
    payload: RolePermissionUpdate,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    update_role_permissions(role, payload, db, authorization)
    return get_role_permission_matrix(db, authorization)
