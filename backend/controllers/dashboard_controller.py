from sqlalchemy import desc

from fastapi import HTTPException

from backend.auth_utils import get_company_for_user, get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, _get_company_product_summary, _get_company_sales_summary, create_audit_log, list_company_notifications
from backend.models import AuditLog, User
from backend.schemas import AuditLogResponse, DashboardResponse, NotificationResponse, ProductSummaryResponse, SalesDashboardSummaryResponse


def dashboard(db: DbDependency, authorization: str | None = None) -> DashboardResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    company = get_company_for_user(db, user)
    summary = _get_company_product_summary(db, user.companyId)
    return {
        "companyName": company.name,
        "metrics": {
            "totalProducts": summary.totalProducts,
            "activeProducts": summary.activeProducts,
            "inactiveProducts": summary.inactiveProducts,
            "totalCategories": summary.totalCategories,
        },
        "visibility": ["Sales", "Inventory", f"Region: {company.address or 'Unknown'}"],
    }


def dashboard_product_summary(db: DbDependency, authorization: str | None = None) -> ProductSummaryResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    return _get_company_product_summary(db, user.companyId)


def dashboard_sales_summary(db: DbDependency, authorization: str | None = None) -> SalesDashboardSummaryResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    return _get_company_sales_summary(db, user.companyId)


def get_notifications(db: DbDependency, limit: int = 20, authorization: str | None = None) -> list[NotificationResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    return list_company_notifications(db, user.companyId, limit)


def list_company_users(company_id: int, db: DbDependency, authorization: str | None = None) -> list[dict]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    if user.companyId != company_id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    users = db.query(User).filter(User.companyId == company_id).all()
    create_audit_log(db, company=str(company_id), user=user.email, action="List Company Users",
                     ip_address="Unknown", browser="Unknown")
    return [{"id": u.id, "email": u.email, "name": u.name, "role": u.role, "status": u.status} for u in users]


def list_audit_logs(db: DbDependency, limit: int = 200, authorization: str | None = None) -> list[AuditLogResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    sanitized_limit = max(1, min(limit, 1000))
    company_keys = [str(user.companyId)]
    if company and company.name:
        company_keys.append(company.name)

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.company.in_(company_keys))
        .order_by(desc(AuditLog.timestamp), desc(AuditLog.id))
        .limit(sanitized_limit)
        .all()
    )
    response: list[AuditLogResponse] = []
    for item in logs:
        formatted_time = item.timestamp.strftime("%d %b %Y %H:%M") if item.timestamp else ""
        response.append(
            AuditLogResponse(
                id=item.id,
                company=item.company or (company.name if company else ""),
                entity=item.entityName,
                invoiceNumber=item.invoiceNumber,
                productName=item.productName,
                action=item.action or "",
                performedBy=item.user or "",
                time=formatted_time,
            )
        )
    return response
