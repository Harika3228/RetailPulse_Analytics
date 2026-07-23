from sqlalchemy import desc

from fastapi import APIRouter, Header

from backend.controllers.dashboard_controller import (
    dashboard,
    dashboard_analytics_summary,
    dashboard_export,
    dashboard_inventory_summary,
    dashboard_product_summary,
    dashboard_sales_summary,
    get_notifications,
    list_audit_logs,
    list_company_users,
)
from backend.database import DbDependency
from backend.schemas import (
    AnalyticsDashboardResponse,
    AuditLogResponse,
    DashboardResponse,
    InventoryDashboardSummaryResponse,
    NotificationResponse,
    ProductSummaryResponse,
    SalesDashboardSummaryResponse,
)

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard_route(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    return dashboard(db, authorization)


@router.get("/dashboard/product-summary", response_model=ProductSummaryResponse)
def dashboard_product_summary_route(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    return dashboard_product_summary(db, authorization)


@router.get("/dashboard/sales-summary", response_model=SalesDashboardSummaryResponse)
def dashboard_sales_summary_route(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    return dashboard_sales_summary(db, authorization)


@router.get("/dashboard/inventory-summary", response_model=InventoryDashboardSummaryResponse)
def dashboard_inventory_summary_route(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    return dashboard_inventory_summary(db, authorization)


@router.get("/dashboard/analytics", response_model=AnalyticsDashboardResponse)
def dashboard_analytics_summary_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
):
    return dashboard_analytics_summary(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
    )


@router.get("/dashboard/export")
def dashboard_export_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    format: str = "csv",
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
):
    return dashboard_export(
        db,
        authorization,
        export_format=format,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
    )


@router.get("/notifications", response_model=list[NotificationResponse])
def get_notifications_route(
    db: DbDependency,
    limit: int = 20,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_notifications(db, limit, authorization)


@router.get("/companies/{company_id}/users")
def list_company_users_route(
    company_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_company_users(company_id, db, authorization)


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs_route(
    db: DbDependency,
    limit: int = 200,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_audit_logs(db, limit, authorization)
