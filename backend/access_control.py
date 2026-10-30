import json

from fastapi import HTTPException, Request
from sqlalchemy import func

from backend.models import RolePermissionConfiguration

ADMIN_ROLES = {"admin", "company_admin", "super_admin"}
ROLE_PERMISSION_ACTIONS = (
    "view",
    "create",
    "update",
    "delete",
    "export",
    "approve",
    "manage_access",
)
ROLE_PERMISSION_MODULES = (
    "dashboard_analytics",
    "products",
    "inventory",
    "sales",
    "customers",
    "reports",
    "data_imports",
    "workflows_approvals",
    "audit_logs",
    "system_monitoring",
    "data_governance",
)
ADMIN_ROLE_PERMISSIONS = {
    module: list(ROLE_PERMISSION_ACTIONS)
    for module in ROLE_PERMISSION_MODULES
}
DEFAULT_ROLE_PERMISSIONS = {
    "analyst": {
        "dashboard_analytics": ["view"],
        "inventory": ["view"],
        "sales": ["view", "create", "update", "delete", "export"],
        "reports": ["view", "create", "export"],
        "workflows_approvals": ["view", "create", "approve"],
    },
    "viewer": {
        "dashboard_analytics": ["view"],
        "reports": ["view"],
        "workflows_approvals": ["view", "create"],
    },
}


def normalize_role(role: str | None) -> str:
    return (role or "").strip().lower().replace(" ", "_")


def effective_role_permissions(db, company_id: int, role: str | None) -> dict[str, list[str]]:
    normalized_role = normalize_role(role)
    if normalized_role in ADMIN_ROLES:
        return {module: list(actions) for module, actions in ADMIN_ROLE_PERMISSIONS.items()}
    configuration = db.query(RolePermissionConfiguration).filter(
        RolePermissionConfiguration.companyId == company_id,
        func.lower(RolePermissionConfiguration.role) == normalized_role,
    ).first()
    if configuration is None:
        configured = DEFAULT_ROLE_PERMISSIONS.get(normalized_role, {})
    else:
        try:
            configured = json.loads(configuration.permissions or "{}")
        except (TypeError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=500,
                detail="Stored role permission configuration is invalid",
            ) from error
    return {
        module: sorted(configured.get(module, []))
        for module in ROLE_PERMISSION_MODULES
    }


def has_permission(db, company_id: int, role: str | None, module: str, action: str) -> bool:
    return action in effective_role_permissions(db, company_id, role).get(module, [])


def permission_for_request(request: Request) -> tuple[str, str] | None:
    path = request.url.path.rstrip("/") or "/"
    if path in {"/health", "/api/health"}:
        return None

    routes = (
        ("/governance/access-requests", "workflows_approvals", "view"),
        ("/governance", "data_governance", "manage_access"),
        ("/companies", "data_governance", "manage_access"),
        ("/system-health", "system_monitoring", "manage_access"),
        ("/api/system-health", "system_monitoring", "manage_access"),
        ("/data-quality", "data_governance", "manage_access"),
        ("/audit-logs", "audit_logs", None),
        ("/workflows", "workflows_approvals", None),
        ("/imports", "data_imports", None),
        ("/data-import", "data_imports", None),
        ("/customers", "customers", None),
        ("/categories", "products", None),
        ("/products", "products", None),
        ("/inventory", "inventory", None),
        ("/forecasting", "inventory", None),
        ("/sales", "sales", None),
        ("/api/sales", "sales", None),
        ("/analytics/sales", "sales", None),
        ("/api/analytics/sales", "sales", None),
        ("/reports", "reports", None),
        ("/scheduled-reports", "reports", None),
        ("/dashboard", "dashboard_analytics", None),
        ("/notifications", "dashboard_analytics", "view"),
    )
    match = next(
        (
            (module, fixed_action)
            for prefix, module, fixed_action in routes
            if path == prefix or path.startswith(f"{prefix}/")
        ),
        None,
    )
    if match is None:
        return None

    module, fixed_action = match
    if fixed_action:
        return module, fixed_action
    if path.startswith("/workflows/") and any(
        segment in path for segment in ("/decision", "/approve", "/reject")
    ):
        return module, "approve"
    if path.startswith("/workflows/configuration"):
        return module, "manage_access"
    if path.endswith("/export") or "/export/" in path or path.endswith("/failed-records"):
        return module, "export"
    method = request.method.upper()
    if method in {"POST"}:
        return module, "create"
    if method in {"PUT", "PATCH"}:
        return module, "update"
    if method == "DELETE":
        return module, "delete"
    return module, "view"
