import csv
import io

from sqlalchemy import desc

from fastapi import HTTPException
from fastapi.responses import Response

from backend.auth_utils import get_company_for_user, get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, _get_company_analytics_summary, _get_company_inventory_summary, _get_company_product_summary, _get_company_sales_summary, create_audit_log, list_company_notifications
from backend.models import AuditLog, SalesTransaction, User
from backend.schemas import AnalyticsDashboardResponse, AuditLogResponse, DashboardResponse, InventoryDashboardSummaryResponse, NotificationResponse, ProductSummaryResponse, SalesDashboardSummaryResponse


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
    if any([dateFrom, dateTo, product, category, brand, salesChannel, paymentMethod]):
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
