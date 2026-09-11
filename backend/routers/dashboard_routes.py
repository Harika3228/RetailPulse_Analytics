from sqlalchemy import desc

from fastapi import APIRouter, Header

from backend.controllers.dashboard_controller import (
    dashboard,
    dashboard_analytics_summary,
    dashboard_export,
    dashboard_inventory_summary,
    dashboard_product_summary,
    dashboard_sales_summary,
    dashboard_top_customers,
    dashboard_top_products,
    get_audit_log,
    export_audit_logs,
    clear_audit_logs,
    get_notifications,
    get_unread_notification_count,
    mark_all_notifications_read,
    mark_notification_read,
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
    TopCustomerResponse,
    TopProductResponse,
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
    customer: str | None = None,
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
        customer=customer,
    )


@router.get("/dashboard/analytics/top-products", response_model=list[TopProductResponse])
def dashboard_top_products_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 50,
):
    return dashboard_top_products(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
        limit=limit,
    )


@router.get("/dashboard/analytics/top-customers", response_model=list[TopCustomerResponse])
def dashboard_top_customers_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 20,
):
    return dashboard_top_customers(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
        limit=limit,
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
    customer: str | None = None,
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
        customer=customer,
    )


@router.get("/notifications", response_model=list[NotificationResponse])
def get_notifications_route(
    db: DbDependency,
    limit: int = 20,
    page: int = 1,
    unread: str | None = None,
    type: str | None = None,
    priority: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_notifications(db, limit, page, unread, type, priority, authorization)


@router.get("/notifications/unread-count")
def get_unread_notification_count_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_unread_notification_count(db, authorization)


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read_route(
    notification_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return mark_notification_read(notification_id, db, authorization)


@router.patch("/notifications/read-all")
def mark_all_notifications_read_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return mark_all_notifications_read(db, authorization)


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
    limit: int = 50,
    page: int | None = None,
    offset: int = 0,
    user: str | None = None,
    action: str | None = None,
    resourceType: str | None = None,
    status: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    search: str | None = None,
    sort: str = "desc",
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_audit_logs(
        db,
        limit=limit,
        page=page,
        offset=offset,
        user_filter=user,
        action=action,
        resource_type=resourceType,
        status=status,
        date_from=dateFrom,
        date_to=dateTo,
        search=search,
        sort_order=sort,
        authorization=authorization,
    )


@router.get("/audit-logs/export")
def export_audit_logs_route(
    db: DbDependency,
    format: str = "csv",
    user: str | None = None,
    action: str | None = None,
    resourceType: str | None = None,
    status: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    search: str | None = None,
    sort: str = "desc",
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_audit_logs(db, format, user, action, resourceType, status, dateFrom, dateTo, search, sort, authorization)


@router.delete("/audit-logs")
def clear_audit_logs_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return clear_audit_logs(db, authorization)


@router.get("/audit-logs/{audit_log_id}", response_model=AuditLogResponse)
def get_audit_log_route(
    audit_log_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_audit_log(audit_log_id, db, authorization)
