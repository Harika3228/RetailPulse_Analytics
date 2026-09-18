import csv
import io
import json
from datetime import datetime, time, timezone

from sqlalchemy import and_, desc, or_

from fastapi import HTTPException
from fastapi.responses import Response

from backend.auth_utils import get_company_for_user, get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, _ensure_report_access, _ensure_sales_user, _get_company_analytics_summary, _get_company_inventory_summary, _get_company_product_summary, _get_company_sales_summary, _get_company_top_customers, _get_company_top_products, count_unread_notifications, create_audit_log, list_company_notifications
from backend.models import AuditLog, Category, Notification, Product, ReportHistory, ScheduledReport, SalesTransaction, StockMovement, User
from backend.schemas import AnalyticsDashboardResponse, AuditLogResponse, DashboardResponse, InventoryDashboardSummaryResponse, NotificationResponse, ProductSummaryResponse, ReportHistoryRequest, ReportHistoryResponse, SalesDashboardSummaryResponse, ScheduledReportRequest, ScheduledReportResponse, TopCustomerResponse, TopProductResponse


def dashboard(db: DbDependency, authorization: str | None = None) -> DashboardResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    company = get_company_for_user(db, user)
    summary = _get_company_product_summary(db, user.companyId)
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Dashboard Viewed",
        entity_name="dashboard",
        ip_address="Unknown",
        browser="Unknown",
    )
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


def dashboard_inventory_summary(db: DbDependency, authorization: str | None = None) -> InventoryDashboardSummaryResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    return _get_company_inventory_summary(db, user.companyId)


def dashboard_analytics_summary(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
) -> AnalyticsDashboardResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Dashboard Viewed",
        entity_name="dashboard",
        ip_address="Unknown",
        browser="Unknown",
    )
    if any([dateFrom, dateTo, product, category, brand, salesChannel, paymentMethod, customer]):
        create_audit_log(
            db,
            company=str(user.companyId),
            user=user.email,
            action="Dashboard Filters Applied",
            entity_name="dashboard",
            ip_address="Unknown",
            browser="Unknown",
        )
    return _get_company_analytics_summary(
        db,
        user.companyId,
        date_from=dateFrom,
        date_to=dateTo,
        product=product,
        category=category,
        brand=brand,
        sales_channel=salesChannel,
        payment_method=paymentMethod,
        customer=customer,
    )


def dashboard_top_products(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 50,
) -> list[TopProductResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    return _get_company_top_products(
        db,
        user.companyId,
        date_from=dateFrom,
        date_to=dateTo,
        product=product,
        category=category,
        brand=brand,
        sales_channel=salesChannel,
        payment_method=paymentMethod,
        customer=customer,
        limit=limit,
    )


def dashboard_top_customers(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 20,
) -> list[TopCustomerResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    return _get_company_top_customers(
        db,
        user.companyId,
        date_from=dateFrom,
        date_to=dateTo,
        sales_channel=salesChannel,
        payment_method=paymentMethod,
        customer=customer,
        limit=limit,
    )


def dashboard_export(
    db: DbDependency,
    authorization: str | None = None,
    export_format: str = "csv",
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
) -> Response:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    company = get_company_for_user(db, user)

    analytics = _get_company_analytics_summary(
        db,
        user.companyId,
        date_from=dateFrom,
        date_to=dateTo,
        product=product,
        category=category,
        brand=brand,
        sales_channel=salesChannel,
        payment_method=paymentMethod,
        customer=customer,
    )
    sales_summary = _get_company_sales_summary(db, user.companyId)
    inventory_summary = _get_company_inventory_summary(db, user.companyId)
    product_summary = _get_company_product_summary(db, user.companyId)

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action=f"Report Exported ({export_format.upper()})",
        entity_name="dashboard",
        invoice_number=export_format.upper(),
        ip_address="Unknown",
        browser="Unknown",
    )

    if export_format.lower() == "pdf":
        pdf_lines = [
            "%PDF-1.4",
            "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj",
            "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj",
            "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj",
            "4 0 obj<< /Length 0 >>stream",
            f"BT /F1 12 Tf 72 720 Td ({company.name or 'Dashboard'} Report) Tj ET",
            "endstream",
            "endobj",
            "5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj",
            "xref",
            "0 6",
            "0000000000 65535 f ",
            "0000000010 00000 n ",
            "0000000062 00000 n ",
            "0000000119 00000 n ",
            "0000000207 00000 n ",
            "0000000306 00000 n ",
            "trailer<< /Size 6 /Root 1 0 R >>",
            "startxref",
            "0",
            "%%EOF",
        ]
        return Response("\n".join(pdf_lines).encode("latin-1"), media_type="application/pdf")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "value"])
    writer.writerow(["company", company.name or ""])
    writer.writerow(["totalRevenue", analytics.totalRevenue])
    writer.writerow(["totalOrders", analytics.totalOrders])
    writer.writerow(["totalProductsSold", analytics.totalProductsSold])
    writer.writerow(["averageOrderValue", analytics.averageOrderValue])
    writer.writerow(["totalInventoryValue", analytics.totalInventoryValue])
    writer.writerow(["lowStockProducts", analytics.lowStockProducts])
    writer.writerow(["outOfStockProducts", analytics.outOfStockProducts])
    writer.writerow(["totalCategories", analytics.totalCategories])
    writer.writerow(["salesTotal", sales_summary.totalRevenue])
    writer.writerow(["salesOrders", sales_summary.totalOrders])
    writer.writerow(["inventoryProducts", inventory_summary.totalProducts])
    writer.writerow(["inventoryQuantity", inventory_summary.totalInventoryQuantity])
    writer.writerow(["productSummaryTotal", product_summary.totalProducts])
    writer.writerow(["productSummaryActive", product_summary.activeProducts])

    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.saleDateTime.desc(), SalesTransaction.id.desc())
        .all()
    )
    writer.writerow([])
    writer.writerow(["invoice", "customer", "date", "total"])
    for transaction in transactions:
        writer.writerow([transaction.invoiceNumber or "", transaction.customerName or "", transaction.saleDateTime or "", transaction.totalAmount or 0])

    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=dashboard-report.csv"})


def get_notifications(db: DbDependency, limit: int = 20, page: int = 1, unread: str | None = None, notification_type: str | None = None, priority: str | None = None, authorization: str | None = None) -> list[NotificationResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    unread_filter = True if unread == "true" else False if unread == "false" else None
    return list_company_notifications(db, user.companyId, user.role, user.id, limit, max(0, page - 1) * limit, unread_filter, notification_type, priority)


def stock_movement_report(db: DbDependency, date_from: str | None = None, date_to: str | None = None, q: str | None = None, category: str | None = None, brand: str | None = None, authorization: str | None = None) -> list[dict]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    query = db.query(StockMovement).join(Product, Product.id == StockMovement.productId).outerjoin(Category, Category.id == Product.categoryId).filter(StockMovement.companyId == user.companyId, Product.companyId == user.companyId)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(StockMovement.productName.ilike(pattern) | StockMovement.sku.ilike(pattern) | StockMovement.movementType.ilike(pattern))
    if category:
        query = query.filter(Category.name.ilike(f"%{category.strip()}%"))
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand.strip()}%"))
    if date_from:
        query = query.filter(StockMovement.createdAt >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(StockMovement.createdAt <= datetime.fromisoformat(date_to + "T23:59:59"))
    movements = query.order_by(StockMovement.createdAt.desc(), StockMovement.id.desc()).limit(5000).all()
    return [
        {
            "id": item.id,
            "product": item.productName or "",
            "sku": item.sku or "",
            "movementType": item.movementType or "",
            "previousQuantity": item.previousQuantity,
            "updatedQuantity": item.updatedQuantity,
            "quantityChanged": item.quantityChanged,
            "reference": item.reference or "",
            "actor": item.actor or "System",
            "createdAt": item.createdAt.isoformat() if item.createdAt else "",
        }
        for item in movements
    ]


def _scheduled_report_response(item: ScheduledReport) -> ScheduledReportResponse:
    return ScheduledReportResponse(
        id=item.id,
        name=item.name or "",
        reportType=item.reportType or "sales",
        filters=json.loads(item.filters or "{}"),
        frequency=item.frequency or "daily",
        executionTime=item.executionTime or "09:00",
        recipients=json.loads(item.recipients or "[]"),
        exportFormat=item.exportFormat or "csv",
        isActive=bool(item.isActive),
        lastGeneratedAt=item.lastGeneratedAt.isoformat() if item.lastGeneratedAt else None,
        lastStatus=item.lastStatus or "not_run",
        lastError=item.lastError,
        nextRunAt=item.nextRunAt.isoformat() if item.nextRunAt else None,
        createdAt=item.createdAt.isoformat() if item.createdAt else "",
    )


def _report_history_response(item: ReportHistory) -> ReportHistoryResponse:
    return ReportHistoryResponse(
        id=item.id,
        reportType=item.reportType or "sales",
        filters=json.loads(item.filters or "{}"),
        exportFormat=item.exportFormat or "table",
        status=item.status or "completed",
        rowCount=item.rowCount or 0,
        errorMessage=item.errorMessage,
        generatedAt=item.generatedAt.isoformat() if item.generatedAt else "",
        generatedByUserId=item.generatedByUserId,
        generatedBy=f"User #{item.generatedByUserId}",
    )


def list_report_history(db: DbDependency, limit: int = 50, authorization: str | None = None) -> list[ReportHistoryResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_report_access(user)
    items = db.query(ReportHistory).filter(ReportHistory.companyId == user.companyId).order_by(ReportHistory.generatedAt.desc(), ReportHistory.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_report_history_response(item) for item in items]


def create_report_history(payload: ReportHistoryRequest, db: DbDependency, authorization: str | None = None) -> ReportHistoryResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_report_access(user)
    item = ReportHistory(
        companyId=user.companyId,
        generatedByUserId=user.id,
        reportType=payload.reportType,
        filters=json.dumps(payload.filters),
        exportFormat=payload.exportFormat,
        status=payload.status,
        rowCount=max(0, payload.rowCount),
        errorMessage=payload.errorMessage,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    create_audit_log(db, company=str(user.companyId), user=user.email, action="Report Generated", entity_name=payload.reportType, resource_type="ReportHistory", resource_id=item.id, company_id=user.companyId, user_id=user.id, ip_address="Unknown", browser="Unknown")
    return _report_history_response(item)


def list_scheduled_reports(db: DbDependency, authorization: str | None = None) -> list[ScheduledReportResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_report_access(user)
    query = db.query(ScheduledReport).filter(ScheduledReport.companyId == user.companyId)
    if user.role in {"analyst", "viewer"}:
        query = query.filter(ScheduledReport.createdByUserId == user.id)
    return [_scheduled_report_response(item) for item in query.order_by(ScheduledReport.createdAt.desc()).all()]


def create_scheduled_report(payload: ScheduledReportRequest, db: DbDependency, authorization: str | None = None) -> ScheduledReportResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_report_access(user)
    if payload.frequency not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="frequency must be daily, weekly, or monthly")
    if payload.exportFormat not in {"csv", "pdf"}:
        raise HTTPException(status_code=400, detail="exportFormat must be csv or pdf")
    item = ScheduledReport(
        companyId=user.companyId,
        createdByUserId=user.id,
        name=payload.name.strip(),
        reportType=payload.reportType,
        filters=json.dumps(payload.filters),
        frequency=payload.frequency,
        executionTime=payload.executionTime,
        recipients=json.dumps([str(email) for email in payload.recipients]),
        exportFormat=payload.exportFormat,
        isActive=1 if payload.isActive else 0,
        lastStatus="not_run",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    create_audit_log(db, company=str(user.companyId), user=user.email, action="Scheduled Report Created", entity_name=item.name, resource_type="ScheduledReport", resource_id=item.id, company_id=user.companyId, user_id=user.id, ip_address="Unknown", browser="Unknown")
    return _scheduled_report_response(item)


def update_scheduled_report(schedule_id: int, payload: ScheduledReportRequest, db: DbDependency, authorization: str | None = None) -> ScheduledReportResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_report_access(user)
    item_query = db.query(ScheduledReport).filter(ScheduledReport.id == schedule_id, ScheduledReport.companyId == user.companyId)
    if user.role in {"analyst", "viewer"}:
        item_query = item_query.filter(ScheduledReport.createdByUserId == user.id)
    item = item_query.first()
    if not item:
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    if payload.frequency not in {"daily", "weekly", "monthly"} or payload.exportFormat not in {"csv", "pdf"}:
        raise HTTPException(status_code=400, detail="Invalid schedule frequency or export format")
    item.name = payload.name.strip()
    item.reportType = payload.reportType
    item.filters = json.dumps(payload.filters)
    item.frequency = payload.frequency
    item.executionTime = payload.executionTime
    item.recipients = json.dumps([str(email) for email in payload.recipients])
    item.exportFormat = payload.exportFormat
    item.isActive = 1 if payload.isActive else 0
    db.commit()
    db.refresh(item)
    return _scheduled_report_response(item)


def set_scheduled_report_status(schedule_id: int, active: bool, db: DbDependency, authorization: str | None = None) -> ScheduledReportResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_report_access(user)
    item_query = db.query(ScheduledReport).filter(ScheduledReport.id == schedule_id, ScheduledReport.companyId == user.companyId)
    if user.role in {"analyst", "viewer"}:
        item_query = item_query.filter(ScheduledReport.createdByUserId == user.id)
    item = item_query.first()
    if not item:
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    item.isActive = 1 if active else 0
    db.commit()
    return _scheduled_report_response(item)


def delete_scheduled_report(schedule_id: int, db: DbDependency, authorization: str | None = None) -> dict[str, bool]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    _ensure_report_access(user)
    item_query = db.query(ScheduledReport).filter(ScheduledReport.id == schedule_id, ScheduledReport.companyId == user.companyId)
    if user.role in {"analyst", "viewer"}:
        item_query = item_query.filter(ScheduledReport.createdByUserId == user.id)
    item = item_query.first()
    if not item:
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    db.delete(item)
    db.commit()
    return {"success": True}


def get_unread_notification_count(db: DbDependency, authorization: str | None = None) -> dict[str, int]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    return {"count": count_unread_notifications(db, user.companyId, user.role, user.id)}


def mark_notification_read(notification_id: int, db: DbDependency, authorization: str | None = None) -> dict[str, bool]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.companyId == user.companyId,
        or_(Notification.userId.is_(None), Notification.userId == user.id),
        or_(
            Notification.targetRole.is_(None),
            Notification.targetRole == user.role,
            and_(Notification.targetRole == "admin", user.role in {"admin", "company_admin", "super_admin"}),
        ),
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.isRead = 1
    notification.readAt = datetime.now(timezone.utc)
    db.commit()
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Notification Marked Read",
        entity_name=notification.title or notification.type,
        resource_type="Notification",
        resource_id=notification.id,
        company_id=user.companyId,
        user_id=user.id,
        ip_address="Unknown",
        browser="Unknown",
    )
    return {"success": True}


def mark_all_notifications_read(db: DbDependency, authorization: str | None = None) -> dict[str, int]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    notifications = db.query(Notification).filter(
        Notification.companyId == user.companyId,
        Notification.isRead == 0,
        or_(Notification.userId.is_(None), Notification.userId == user.id),
        or_(
            Notification.targetRole.is_(None),
            Notification.targetRole == user.role,
            and_(Notification.targetRole == "admin", user.role in {"admin", "company_admin", "super_admin"}),
        ),
    ).all()
    now = datetime.now(timezone.utc)
    for notification in notifications:
        notification.isRead = 1
        notification.readAt = now
    db.commit()
    if notifications:
        create_audit_log(
            db,
            company=str(user.companyId),
            user=user.email,
            action="All Notifications Marked Read",
            entity_name="notifications",
            description=f"Marked {len(notifications)} notifications as read.",
            company_id=user.companyId,
            user_id=user.id,
            ip_address="Unknown",
            browser="Unknown",
        )
    return {"updated": len(notifications)}


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


def list_audit_logs(
    db: DbDependency,
    limit: int = 50,
    page: int | None = None,
    offset: int = 0,
    user_filter: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    sort_order: str = "desc",
    authorization: str | None = None,
) -> list[AuditLogResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    sanitized_limit = max(1, min(limit, 100))
    sanitized_offset = max(0, offset) if page is None else (max(1, page) - 1) * sanitized_limit
    if sort_order.lower() not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="sort must be 'asc' or 'desc'")
    company_keys = [str(user.companyId)]
    if company and company.name:
        company_keys.append(company.name)

    logs = (
        db.query(AuditLog)
        .outerjoin(User, AuditLog.userId == User.id)
        .filter(or_(
            AuditLog.companyId == user.companyId,
            and_(AuditLog.companyId.is_(None), AuditLog.company.in_(company_keys)),
        ))
    )
    if user_filter:
        user_pattern = f"%{user_filter.strip()}%"
        logs = logs.filter(or_(AuditLog.user.ilike(user_pattern), User.name.ilike(user_pattern), User.email.ilike(user_pattern)))
    if action:
        logs = logs.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if resource_type:
        logs = logs.filter(AuditLog.resourceType.ilike(f"%{resource_type.strip()}%"))
    if status:
        logs = logs.filter(AuditLog.status.ilike(status.strip()))
    if search:
        search_pattern = f"%{search.strip()}%"
        logs = logs.filter(or_(
            AuditLog.user.ilike(search_pattern),
            User.name.ilike(search_pattern),
            User.email.ilike(search_pattern),
            AuditLog.action.ilike(search_pattern),
            AuditLog.resourceType.ilike(search_pattern),
            AuditLog.resourceId.ilike(search_pattern),
            AuditLog.description.ilike(search_pattern),
        ))
    if date_from:
        try:
            logs = logs.filter(AuditLog.createdAt >= datetime.combine(datetime.fromisoformat(date_from).date(), time.min, tzinfo=timezone.utc))
        except ValueError:
            raise HTTPException(status_code=400, detail="dateFrom must be an ISO date")
    if date_to:
        try:
            logs = logs.filter(AuditLog.createdAt < datetime.combine(datetime.fromisoformat(date_to).date(), time.max, tzinfo=timezone.utc))
        except ValueError:
            raise HTTPException(status_code=400, detail="dateTo must be an ISO date")

    order = desc if sort_order.lower() == "desc" else lambda column: column.asc()
    logs = (
        logs.order_by(order(AuditLog.createdAt), order(AuditLog.timestamp), order(AuditLog.id))
        .offset(sanitized_offset)
        .limit(sanitized_limit)
        .all()
    )
    response: list[AuditLogResponse] = []
    for item in logs:
        formatted_time = item.timestamp.strftime("%d %b %Y %H:%M") if item.timestamp else ""
        response.append(
            AuditLogResponse(
                id=item.id,
                companyId=item.companyId,
                userId=item.userId,
                resourceType=item.resourceType or item.entityName,
                resourceId=item.resourceId,
                description=item.description or item.action or "",
                ipAddress=item.ipAddress or "Unknown",
                userAgent=item.userAgent or item.browser or "Unknown",
                createdAt=item.createdAt.isoformat() if item.createdAt else (item.timestamp.isoformat() if item.timestamp else ""),
                status=item.status or "success",
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


def get_audit_log(audit_log_id: int, db: DbDependency, authorization: str | None = None) -> AuditLogResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)
    company_keys = [str(user.companyId)]
    if company and company.name:
        company_keys.append(company.name)
    item = (
        db.query(AuditLog)
        .filter(
            AuditLog.id == audit_log_id,
            or_(
                AuditLog.companyId == user.companyId,
                and_(AuditLog.companyId.is_(None), AuditLog.company.in_(company_keys)),
            ),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Audit log not found")
    formatted_time = item.timestamp.strftime("%d %b %Y %H:%M") if item.timestamp else ""
    return AuditLogResponse(
        id=item.id,
        companyId=item.companyId,
        userId=item.userId,
        resourceType=item.resourceType or item.entityName,
        resourceId=item.resourceId,
        description=item.description or item.action or "",
        ipAddress=item.ipAddress or "Unknown",
        userAgent=item.userAgent or item.browser or "Unknown",
        createdAt=item.createdAt.isoformat() if item.createdAt else (item.timestamp.isoformat() if item.timestamp else ""),
        status=item.status or "success",
        company=item.company or (company.name if company else ""),
        entity=item.entityName,
        invoiceNumber=item.invoiceNumber,
        productName=item.productName,
        action=item.action or "",
        performedBy=item.user or "",
        time=formatted_time,
    )


def export_audit_logs(
    db: DbDependency,
    export_format: str = "csv",
    user_filter: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    sort_order: str = "desc",
    authorization: str | None = None,
) -> Response:
    if export_format.lower() not in {"csv", "pdf"}:
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'pdf'")
    records = list_audit_logs(
        db, limit=10000, user_filter=user_filter, action=action,
        resource_type=resource_type, status=status, date_from=date_from,
        date_to=date_to, search=search, sort_order=sort_order,
        authorization=authorization,
    )
    headers = ["user", "action", "resource", "resource_id", "description", "ip_address", "user_agent", "timestamp", "status"]
    rows = [[item.performedBy, item.action, item.resourceType or "", item.resourceId or "", item.description, item.ipAddress, item.userAgent, item.createdAt, item.status] for item in records]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    if export_format.lower() == "csv":
        return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit-logs.csv"})
    pdf_lines = ["%PDF-1.4", "% Audit Logs", "", " | ".join(headers)]
    pdf_lines.extend(" | ".join(str(value).replace("\n", " ") for value in row) for row in rows)
    pdf_lines.append("%%EOF")
    return Response("\n".join(pdf_lines).encode("utf-8"), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=audit-logs.pdf"})


def clear_audit_logs(db: DbDependency, authorization: str | None = None) -> dict[str, int | str]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    deleted_count = db.query(AuditLog).filter(AuditLog.companyId == user.companyId).delete(synchronize_session=False)
    db.commit()
    create_audit_log(
        db, company=str(user.companyId), user=user.email, action="Audit Logs Cleared",
        entity_name="audit_logs", description=f"Cleared {deleted_count} audit log records.",
        company_id=user.companyId, user_id=user.id, ip_address="Unknown", browser="Unknown",
    )
    return {"message": "Audit logs cleared", "deletedCount": deleted_count}
