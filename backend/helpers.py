import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, case, desc, func

from backend.database import engine
from backend.models import (
    AuditLog, Category, Company, Customer, Notification, Product, SalesTransaction,
    SalesTransactionLine, StockMovement, User,
)
from backend.schemas import (
    AnalyticsDashboardResponse,
    InventoryDashboardSummaryResponse,
    NotificationResponse,
    ProductResponse,
    ProductSummaryResponse,
    SalesDashboardSummaryResponse,
    SalesLineRequest,
    SalesLineResponse,
    SalesTransactionRequest,
    SalesTransactionResponse,
)

LOW_STOCK_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def create_audit_log(
    db,
    company: str,
    user: str,
    action: str,
    entity_name: str | None = None,
    invoice_number: str | None = None,
    product_name: str | None = None,
    category_name: str | None = None,
    forecast_period: str | None = None,
    ip_address: str | None = None,
    browser: str | None = None,
    company_id: int | None = None,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    description: str | None = None,
    status: str = "success",
    commit: bool = True,
) -> None:
    resolved_company_id = company_id
    if resolved_company_id is None:
        resolved_company_id = int(company) if company.isdigit() else (
            db.query(Company.id).filter(Company.name == company).scalar()
        )
    resolved_user_id = user_id
    if resolved_user_id is None:
        resolved_user_id = db.query(User.id).filter(User.email == user).scalar()
    entry = AuditLog(
        companyId=resolved_company_id,
        userId=resolved_user_id,
        resourceType=resource_type or entity_name,
        resourceId=str(resource_id) if resource_id is not None else None,
        description=description or action,
        userAgent=browser or "Unknown",
        createdAt=datetime.now(timezone.utc),
        status=status,
        company=company,
        entityName=entity_name,
        invoiceNumber=invoice_number,
        productName=product_name,
        categoryName=category_name,
        forecastPeriod=forecast_period,
        user=user,
        action=action,
        ipAddress=ip_address or "Unknown",
        browser=browser or "Unknown",
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    if commit:
        db.commit()


def create_notification(db, company_id: int, product_id: int | None = None, product_name: str | None = None, message: str = "", notification_type: str = "info") -> None:
    existing = (
        db.query(Notification)
        .filter(
            Notification.companyId == company_id,
            Notification.message == message,
            Notification.type == notification_type,
            Notification.isRead == 0,
        )
        .first()
    )
    if existing:
        return
    db.add(
        Notification(
            companyId=company_id,
            productId=product_id or 0,
            productName=product_name or "",
            message=message,
            type=notification_type,
            isRead=0,
        )
    )


# ---------------------------------------------------------------------------
# Batch helpers (reduce per-product DB round-trips)
# ---------------------------------------------------------------------------

class AuditLogCollector:
    """Collects audit log entries and flushes them in a single commit."""

    def __init__(self, db) -> None:
        self._db = db
        self._entries: list[AuditLog] = []
        self._seen_actions: set[str] = set()

    def add(
        self,
        company: str,
        user: str,
        action: str,
        entity_name: str | None = None,
        invoice_number: str | None = None,
        product_name: str | None = None,
        category_name: str | None = None,
        forecast_period: str | None = None,
        ip_address: str | None = None,
        browser: str | None = None,
        deduplicate_key: str | None = None,
    ) -> None:
        key = deduplicate_key or f"{action}:{entity_name}:{product_name}"
        if key in self._seen_actions:
            return
        self._seen_actions.add(key)
        self._entries.append(
            AuditLog(
                company=company,
                entityName=entity_name,
                invoiceNumber=invoice_number,
                productName=product_name,
                categoryName=category_name,
                forecastPeriod=forecast_period,
                user=user,
                action=action,
                ipAddress=ip_address or "Unknown",
                browser=browser or "Unknown",
                timestamp=datetime.now(timezone.utc),
            )
        )

    def flush(self) -> None:
        if self._entries:
            self._db.add_all(self._entries)
            self._entries.clear()


class NotificationCollector:
    """Collects notifications and writes them in bulk, de-duplicating messages."""

    def __init__(self, db) -> None:
        self._db = db
        self._entries: list[Notification] = []
        self._seen_messages: set[str] = set()

    def add(
        self,
        company_id: int,
        product_id: int | None = None,
        product_name: str | None = None,
        message: str = "",
        notification_type: str = "info",
    ) -> None:
        dedup_key = f"{company_id}:{message}:{notification_type}"
        if dedup_key in self._seen_messages:
            return
        self._seen_messages.add(dedup_key)
        self._entries.append(
            Notification(
                companyId=company_id,
                productId=product_id or 0,
                productName=product_name or "",
                message=message,
                type=notification_type,
                isRead=0,
            )
        )

    def flush(self) -> None:
        if self._entries:
            self._db.add_all(self._entries)
            self._entries.clear()


def list_company_notifications(db, company_id: int, limit: int = 20) -> list[NotificationResponse]:
    items = (
        db.query(Notification)
        .filter(Notification.companyId == company_id)
        .order_by(Notification.createdAt.desc(), Notification.id.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        NotificationResponse(
            id=item.id,
            productId=item.productId or 0,
            productName=item.productName or "",
            message=item.message or "",
            type=item.type or "info",
            createdAt=_datetime_to_iso(item.createdAt) or "",
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# Role guards
# ---------------------------------------------------------------------------

def _ensure_admin(user) -> None:
    if user.role not in ("admin", "company_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin role required")


def _ensure_sales_user(user) -> None:
    if user.role not in ("admin", "company_admin", "super_admin", "analyst"):
        raise HTTPException(status_code=403, detail="Sales role required")


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------

def _format_invoice_number(year: int, sequence: int) -> str:
    return f"INV-{year}-{sequence:06d}"


def _next_company_invoice_number(db, company_id: int, sale_date_time: datetime) -> str:
    year = sale_date_time.year
    prefix = f"INV-{year}-"

    existing_invoices = [
        row[0]
        for row in db.query(SalesTransaction.invoiceNumber)
        .filter(
            SalesTransaction.companyId == company_id,
            SalesTransaction.invoiceNumber.ilike(f"{prefix}%"),
        )
        .all()
        if row[0]
    ]

    max_sequence = 0
    for invoice in existing_invoices:
        match = re.fullmatch(r"INV-(\d{4})-(\d{6})", invoice.strip())
        if not match:
            continue
        if int(match.group(1)) != year:
            continue
        max_sequence = max(max_sequence, int(match.group(2)))

    next_sequence = max_sequence + 1
    candidate = _format_invoice_number(year, next_sequence)
    while (
        db.query(SalesTransaction)
        .filter(
            SalesTransaction.companyId == company_id,
            SalesTransaction.invoiceNumber == candidate,
        )
        .first()
        is not None
    ):
        next_sequence += 1
        candidate = _format_invoice_number(year, next_sequence)

    return candidate


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------

def _parse_sale_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Product helpers
# ---------------------------------------------------------------------------

def _normalize_sku(sku: str) -> str:
    return sku.strip().upper()


def _is_product_active(product) -> bool:
    return (product.status or "active").lower() == "active"


def _product_stock_expr():
    """Effective current stock for a product, falling back to the initial stock quantity."""
    return func.coalesce(Product.stockQuantity, Product.initialStockQuantity, 0)


def _to_product_response(product) -> ProductResponse:
    stock_quantity = int(
        product.stockQuantity if product.stockQuantity is not None else (product.initialStockQuantity or 0)
    )
    return ProductResponse(
        id=product.id,
        name=product.name,
        sku=product.sku,
        categoryId=product.categoryId,
        brand=product.brand or "",
        description=product.description,
        unitPrice=float(product.unitPrice or 0),
        costPrice=float(product.costPrice or 0),
        stockQuantity=stock_quantity,
        initialStockQuantity=stock_quantity,
        maxStockLevel=product.maxStockLevel if hasattr(product, 'maxStockLevel') else None,
        unitOfMeasure=product.unitOfMeasure or "",
        status=product.status or "active",
        createdAt=product.createdAt.isoformat() if product.createdAt else None,
        updatedAt=product.updatedAt.isoformat() if product.updatedAt else None,
    )


def _get_company_product_summary(db, company_id: int) -> ProductSummaryResponse:
    total = db.query(Product).filter(Product.companyId == company_id).count()
    active = db.query(Product).filter(Product.companyId == company_id, Product.status == "active").count()
    inactive = db.query(Product).filter(Product.companyId == company_id, Product.status == "inactive").count()
    categories = db.query(Category).filter(Category.companyId == company_id).count()
    return ProductSummaryResponse(
        totalProducts=total,
        activeProducts=active,
        inactiveProducts=inactive,
        totalCategories=categories,
    )


def _get_company_sales_summary(db, company_id: int) -> SalesDashboardSummaryResponse:
    order_row = (
        db.query(
            func.count(SalesTransaction.id).label("orders"),
            func.coalesce(func.sum(SalesTransaction.totalAmount), 0).label("revenue"),
        )
        .filter(SalesTransaction.companyId == company_id)
        .first()
    )
    total_orders = int(order_row.orders)
    total_revenue = float(order_row.revenue)
    total_sales = int(
        db.query(func.coalesce(func.sum(SalesTransactionLine.quantity), 0))
        .join(SalesTransaction, SalesTransaction.id == SalesTransactionLine.transactionId)
        .filter(SalesTransaction.companyId == company_id)
        .scalar()
        or 0
    )
    average_order_value = (total_revenue / total_orders) if total_orders else 0
    return SalesDashboardSummaryResponse(
        totalSales=total_sales,
        totalRevenue=total_revenue,
        totalOrders=total_orders,
        averageOrderValue=average_order_value,
    )


def _get_company_inventory_summary(db, company_id: int) -> InventoryDashboardSummaryResponse:
    stock_expr = _product_stock_expr()
    row = (
        db.query(
            func.count(Product.id).label("total_products"),
            func.coalesce(func.sum(stock_expr), 0).label("total_quantity"),
            func.sum(case((stock_expr <= 0, 1), else_=0)).label("out_of_stock"),
            func.sum(case((and_(stock_expr > 0, stock_expr <= LOW_STOCK_THRESHOLD), 1), else_=0)).label("low_stock"),
        )
        .filter(Product.companyId == company_id)
        .first()
    )
    return InventoryDashboardSummaryResponse(
        totalProducts=int(row.total_products),
        totalInventoryQuantity=int(row.total_quantity),
        lowStockProducts=int(row.low_stock or 0),
        outOfStockProducts=int(row.out_of_stock or 0),
    )


def _parse_dashboard_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _date_bucket_expr(column, bucket: str, dialect: str):
    """Return a SQL expression that groups a datetime column into daily/weekly/monthly buckets."""
    if bucket == "daily":
        return func.to_char(column, "YYYY-MM-DD") if dialect == "postgresql" else func.strftime("%Y-%m-%d", column)
    if bucket == "weekly":
        return func.to_char(column, 'IYYY-"W"IW') if dialect == "postgresql" else func.strftime("%Y-W%W", column)
    return func.to_char(column, "Mon YYYY") if dialect == "postgresql" else func.strftime("%Y-%m", column)


def _friendly_bucket_label(bucket: str, label) -> str:
    """Normalize SQL bucket labels into a human-friendly string for any dialect."""
    if label is None:
        return ""
    text = str(label)
    if bucket == "monthly" and re.fullmatch(r"\d{4}-\d{2}", text):
        try:
            return datetime.strptime(text, "%Y-%m").strftime("%b %Y")
        except ValueError:
            return text
    if bucket == "weekly" and re.fullmatch(r"\d{4}-W\d{2}", text):
        return f"{text[:4]}-W{int(text[6:]):02d}"
    return text


def _matching_line_transaction_ids(
    db,
    company_id: int,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
):
    """Subquery of transaction ids that contain at least one line matching product/category/brand filters."""
    query = (
        db.query(SalesTransactionLine.transactionId)
        .join(Product, Product.id == SalesTransactionLine.productId)
        .filter(SalesTransactionLine.transactionId.isnot(None))
    )
    if product:
        query = query.filter(Product.name.ilike(f"%{product}%"))
    if category:
        category_ids = [
            row[0]
            for row in db.query(Category.id)
            .filter(Category.companyId == company_id, Category.name.ilike(f"%{category}%"))
            .all()
        ]
        query = query.filter(Product.categoryId.in_(category_ids))
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    return query.distinct()


def _base_sales_transaction_query(
    db,
    company_id: int,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    sales_channel: str | None = None,
    payment_method: str | None = None,
    customer: str | None = None,
):
    """SalesTransaction query scoped to a company and all supported analytics filters."""
    query = db.query(SalesTransaction).filter(SalesTransaction.companyId == company_id)
    if from_date:
        query = query.filter(SalesTransaction.saleDateTime >= from_date)
    if to_date:
        query = query.filter(SalesTransaction.saleDateTime <= to_date)
    if sales_channel:
        query = query.filter(SalesTransaction.salesChannel.ilike(f"%{sales_channel}%"))
    if payment_method:
        query = query.filter(SalesTransaction.paymentMethod.ilike(f"%{payment_method}%"))
    if customer:
        query = query.filter(SalesTransaction.customerName.ilike(f"%{customer}%"))
    if product or category or brand:
        query = query.filter(
            SalesTransaction.id.in_(
                _matching_line_transaction_ids(db, company_id, product=product, category=category, brand=brand)
            )
        )
    return query


def _base_sales_line_query(
    db,
    company_id: int,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    sales_channel: str | None = None,
    payment_method: str | None = None,
    customer: str | None = None,
):
    """SalesTransactionLine query (joined to Product and SalesTransaction) scoped to a company and all filters."""
    query = (
        db.query(SalesTransactionLine)
        .join(Product, Product.id == SalesTransactionLine.productId)
        .join(SalesTransaction, SalesTransaction.id == SalesTransactionLine.transactionId)
        .filter(SalesTransaction.companyId == company_id)
    )
    if from_date:
        query = query.filter(SalesTransaction.saleDateTime >= from_date)
    if to_date:
        query = query.filter(SalesTransaction.saleDateTime <= to_date)
    if sales_channel:
        query = query.filter(SalesTransaction.salesChannel.ilike(f"%{sales_channel}%"))
    if payment_method:
        query = query.filter(SalesTransaction.paymentMethod.ilike(f"%{payment_method}%"))
    if customer:
        query = query.filter(SalesTransaction.customerName.ilike(f"%{customer}%"))
    if product:
        query = query.filter(Product.name.ilike(f"%{product}%"))
    if category:
        category_ids = [
            row[0]
            for row in db.query(Category.id)
            .filter(Category.companyId == company_id, Category.name.ilike(f"%{category}%"))
            .all()
        ]
        query = query.filter(Product.categoryId.in_(category_ids))
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    return query


def _sales_line_revenue_expr():
    """Revenue for a line item, mirroring stored lineTotal with a unit-price fallback."""
    return func.coalesce(
        SalesTransactionLine.lineTotal,
        SalesTransactionLine.unitPrice * SalesTransactionLine.quantity,
        0,
    )


def _aggregated_trends(base_transactions, base_lines, dialect: str) -> tuple[dict, dict, dict]:
    """Build daily/weekly/monthly revenue, sales-quantity and order trends via SQL GROUP BY."""
    revenue_trend: dict[str, list[dict[str, object]]] = {}
    sales_trend: dict[str, list[dict[str, object]]] = {}
    order_trend: dict[str, list[dict[str, object]]] = {}
    for bucket in ("daily", "weekly", "monthly"):
        bucket_col = _date_bucket_expr(SalesTransaction.saleDateTime, bucket, dialect).label("bucket")
        revenue_rows = (
            base_transactions.with_entities(bucket_col, func.coalesce(func.sum(SalesTransaction.totalAmount), 0))
            .group_by(bucket_col)
            .order_by(bucket_col)
            .all()
        )
        order_rows = (
            base_transactions.with_entities(bucket_col, func.count(SalesTransaction.id))
            .group_by(bucket_col)
            .order_by(bucket_col)
            .all()
        )
        sales_rows = (
            base_lines.with_entities(bucket_col, func.coalesce(func.sum(SalesTransactionLine.quantity), 0))
            .group_by(bucket_col)
            .order_by(bucket_col)
            .all()
        )
        revenue_trend[bucket] = [{"label": _friendly_bucket_label(bucket, row[0]), "value": round(float(row[1]), 2)} for row in revenue_rows]
        sales_trend[bucket] = [{"label": _friendly_bucket_label(bucket, row[0]), "value": int(row[1])} for row in sales_rows]
        order_trend[bucket] = [{"label": _friendly_bucket_label(bucket, row[0]), "value": int(row[1])} for row in order_rows]
    return revenue_trend, sales_trend, order_trend


def _dimension_distribution(base_transactions, column) -> list[dict[str, object]]:
    """Aggregate revenue and order counts grouped by a transaction dimension (payment method, channel, status)."""
    rows = (
        base_transactions.with_entities(
            func.coalesce(column, "Unknown").label("label"),
            func.coalesce(func.sum(SalesTransaction.totalAmount), 0).label("revenue"),
            func.count(SalesTransaction.id).label("orders"),
        )
        .group_by("label")
        .order_by("label")
        .all()
    )
    return [{"label": row.label, "revenue": round(float(row.revenue), 2), "orders": int(row.orders)} for row in rows]


def _sanitized_limit(limit: int | None, default: int, maximum: int) -> int:
    try:
        requested = int(limit or default)
    except (TypeError, ValueError):
        requested = default
    return max(1, min(requested, maximum))


def _get_company_analytics_summary(
    db,
    company_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    sales_channel: str | None = None,
    payment_method: str | None = None,
    customer: str | None = None,
) -> AnalyticsDashboardResponse:
    from_date = _parse_dashboard_datetime(date_from)
    to_date = _parse_dashboard_datetime(date_to)
    dialect = db.bind.dialect.name

    base_transactions = _base_sales_transaction_query(
        db,
        company_id,
        from_date=from_date,
        to_date=to_date,
        product=product,
        category=category,
        brand=brand,
        sales_channel=sales_channel,
        payment_method=payment_method,
        customer=customer,
    )
    base_lines = _base_sales_line_query(
        db,
        company_id,
        from_date=from_date,
        to_date=to_date,
        product=product,
        category=category,
        brand=brand,
        sales_channel=sales_channel,
        payment_method=payment_method,
        customer=customer,
    )

    kpi_row = (
        base_transactions.with_entities(
            func.count(SalesTransaction.id).label("orders"),
            func.coalesce(func.sum(SalesTransaction.totalAmount), 0).label("revenue"),
            func.coalesce(func.sum(SalesTransaction.discountAmount), 0).label("discount"),
            func.coalesce(func.sum(SalesTransaction.taxAmount), 0).label("tax"),
        )
        .first()
    )
    total_orders = int(kpi_row.orders)
    total_revenue = float(kpi_row.revenue)
    total_discount = float(kpi_row.discount)
    total_tax = float(kpi_row.tax)
    total_products_sold = int(base_lines.with_entities(func.coalesce(func.sum(SalesTransactionLine.quantity), 0)).scalar() or 0)
    average_order_value = (total_revenue / total_orders) if total_orders else 0

    revenue_trend, sales_trend, order_trend = _aggregated_trends(base_transactions, base_lines, dialect)

    product_rows = (
        base_lines.with_entities(
            Product.id,
            func.coalesce(func.sum(SalesTransactionLine.quantity), 0).label("quantity"),
            _sales_line_revenue_expr().label("revenue"),
        )
        .group_by(Product.id)
        .order_by(desc("quantity"))
        .limit(10)
        .all()
    )
    product_ids = [row[0] for row in product_rows]
    product_names: dict[int, str] = {}
    if product_ids:
        product_names = {
            row.id: row.name
            for row in db.query(Product.id, Product.name).filter(Product.id.in_(product_ids)).all()
        }
    top_selling_products = [
        {"name": product_names.get(row[0], "Unknown"), "quantity": int(row[1]), "revenue": round(float(row[2]), 2)}
        for row in product_rows
    ]

    category_rows = (
        base_lines.with_entities(
            Product.categoryId,
            _sales_line_revenue_expr().label("revenue"),
            func.coalesce(func.sum(SalesTransactionLine.quantity), 0).label("units"),
        )
        .filter(Product.categoryId.isnot(None), Product.categoryId != 0)
        .group_by(Product.categoryId)
        .order_by(desc("revenue"))
        .limit(10)
        .all()
    )
    category_ids = [row[0] for row in category_rows]
    category_names: dict[int, str] = {}
    if category_ids:
        category_names = {
            row.id: row.name
            for row in db.query(Category.id, Category.name).filter(Category.id.in_(category_ids)).all()
        }
    top_performing_categories = [
        {"name": category_names.get(row[0], "Uncategorized"), "revenue": round(float(row[1]), 2), "unitsSold": int(row[2])}
        for row in category_rows
    ]

    payment_rows = _dimension_distribution(base_transactions, SalesTransaction.paymentMethod)
    channel_rows = _dimension_distribution(base_transactions, SalesTransaction.salesChannel)
    status_rows = _dimension_distribution(base_transactions, SalesTransaction.paymentStatus)
    sales_by_payment_method = [{"label": entry["label"], "value": entry["revenue"]} for entry in payment_rows]
    orders_by_payment_method = [{"label": entry["label"], "value": entry["orders"]} for entry in payment_rows]
    sales_by_sales_channel = [{"label": entry["label"], "value": entry["revenue"]} for entry in channel_rows]
    orders_by_sales_channel = [{"label": entry["label"], "value": entry["orders"]} for entry in channel_rows]
    sales_by_payment_status = [{"label": entry["label"], "value": entry["revenue"]} for entry in status_rows]

    stock_expr = _product_stock_expr()
    inventory_metrics = (
        db.query(
            func.count(Product.id).label("product_count"),
            func.coalesce(func.sum(Product.unitPrice * stock_expr), 0).label("inventory_value"),
            func.sum(case((stock_expr <= 0, 1), else_=0)).label("out_of_stock"),
            func.sum(case((and_(stock_expr > 0, stock_expr <= LOW_STOCK_THRESHOLD), 1), else_=0)).label("low_stock"),
        )
        .filter(Product.companyId == company_id)
        .first()
    )
    total_inventory_value = float(inventory_metrics.inventory_value)
    low_stock_products = int(inventory_metrics.low_stock or 0)
    out_of_stock_products = int(inventory_metrics.out_of_stock or 0)
    product_count = int(inventory_metrics.product_count)

    category_inventory_rows = (
        db.query(
            func.coalesce(Product.categoryId, 0).label("category_id"),
            func.coalesce(func.sum(stock_expr), 0).label("quantity"),
            func.coalesce(func.sum(Product.unitPrice * stock_expr), 0).label("value"),
        )
        .filter(Product.companyId == company_id)
        .group_by("category_id")
        .all()
    )
    inventory_category_ids = [row.category_id for row in category_inventory_rows if row.category_id]
    inventory_category_names: dict[int, str] = {}
    if inventory_category_ids:
        inventory_category_names = {
            row.id: row.name
            for row in db.query(Category.id, Category.name).filter(Category.id.in_(inventory_category_ids)).all()
        }
    inventory_distribution = [
        {"name": inventory_category_names.get(row.category_id, "Uncategorized"), "value": int(row.quantity)}
        for row in category_inventory_rows
    ]
    inventory_distribution.sort(key=lambda item: int(item["value"]), reverse=True)
    inventory_value_by_category = [
        {"name": inventory_category_names.get(row.category_id, "Uncategorized"), "value": round(float(row.value), 2)}
        for row in category_inventory_rows
    ]
    inventory_value_by_category.sort(key=lambda item: float(item["value"]), reverse=True)

    top_low_stock_rows = (
        db.query(Product.name, Product.sku, stock_expr.label("stock"))
        .filter(Product.companyId == company_id, stock_expr > 0, stock_expr <= LOW_STOCK_THRESHOLD)
        .order_by(stock_expr, Product.id)
        .limit(10)
        .all()
    )
    top_low_stock_products = [
        {"name": row.name or "Unknown", "stock": int(row.stock), "sku": row.sku or ""}
        for row in top_low_stock_rows
    ]
    out_of_stock_rows = (
        db.query(Product.name, Product.sku, Product.categoryId)
        .filter(Product.companyId == company_id, stock_expr <= 0)
        .order_by(Product.name)
        .all()
    )
    out_of_stock_product_items = [
        {"name": row.name or "Unknown", "sku": row.sku or "", "category": row.categoryId or ""}
        for row in out_of_stock_rows
    ]

    total_categories = db.query(Category).filter(Category.companyId == company_id).count()
    top_customer_rows = (
        db.query(Customer.name, Customer.totalSpend, Customer.purchaseCount)
        .filter(Customer.companyId == company_id)
        .order_by(desc(func.coalesce(Customer.totalSpend, 0)), Customer.id)
        .limit(8)
        .all()
    )
    top_customers_by_revenue = [
        {"name": row.name or "Unknown", "revenue": round(float(row.totalSpend or 0), 2), "orders": int(row.purchaseCount or 0)}
        for row in top_customer_rows
    ]
    recent_customer_rows = (
        db.query(Customer)
        .filter(Customer.companyId == company_id)
        .order_by(desc(func.coalesce(Customer.createdAt, datetime.now(timezone.utc))), Customer.id)
        .limit(5)
        .all()
    )
    recent_customers = [
        {
            "id": customer.id,
            "name": customer.name or "Unknown",
            "email": customer.email or "",
            "status": customer.status or "active",
            "purchaseCount": int(customer.purchaseCount or 0),
            "totalSpend": round(float(customer.totalSpend or 0), 2),
        }
        for customer in recent_customer_rows
    ]
    month_expr = _date_bucket_expr(Customer.createdAt, "monthly", dialect)
    growth_rows = (
        db.query(month_expr.label("month"), func.count(Customer.id))
        .filter(Customer.companyId == company_id)
        .group_by(month_expr)
        .all()
    )
    customer_count_by_month = {row.month: int(row[1]) for row in growth_rows}
    customer_growth_trend = []
    for month_index in range(6):
        month_date = datetime.now(timezone.utc).replace(day=1) - timedelta(days=30 * month_index)
        month_label = month_date.strftime("%b %Y")
        customer_growth_trend.append({"month": month_label, "customers": customer_count_by_month.get(month_label, 0)})
    customer_growth_trend.reverse()
    total_customer_revenue = float(
        db.query(func.coalesce(func.sum(Customer.totalSpend), 0))
        .filter(Customer.companyId == company_id)
        .scalar()
        or 0
    )
    customer_revenue_contribution = []
    for customer in top_customers_by_revenue:
        share = round((customer["revenue"] / total_customer_revenue) * 100, 2) if total_customer_revenue else 0
        customer_revenue_contribution.append({"name": customer["name"], "value": customer["revenue"], "share": share})
    return AnalyticsDashboardResponse(
        totalRevenue=total_revenue,
        totalOrders=total_orders,
        totalProductsSold=total_products_sold,
        averageOrderValue=average_order_value,
        totalDiscount=total_discount,
        totalTax=total_tax,
        totalInventoryValue=total_inventory_value,
        lowStockProducts=low_stock_products,
        outOfStockProducts=out_of_stock_products,
        totalCategories=total_categories,
        revenueTrend=revenue_trend,
        salesTrend=sales_trend,
        orderTrend=order_trend,
        topSellingProducts=top_selling_products,
        topPerformingCategories=top_performing_categories,
        salesByPaymentMethod=sales_by_payment_method,
        salesBySalesChannel=sales_by_sales_channel,
        salesByPaymentStatus=sales_by_payment_status,
        ordersBySalesChannel=orders_by_sales_channel,
        ordersByPaymentMethod=orders_by_payment_method,
        inventoryDistributionByCategory=[
            {"name": entry["name"], "value": int(entry["value"])} for entry in inventory_distribution
        ],
        stockStatusSummary={
            "inStock": product_count - low_stock_products - out_of_stock_products,
            "lowStock": low_stock_products,
            "outOfStock": out_of_stock_products,
        },
        topLowStockProducts=top_low_stock_products,
        outOfStockProductDetails=out_of_stock_product_items,
        inventoryValueByCategory=[
            {"name": entry["name"], "value": round(float(entry["value"]), 2)} for entry in inventory_value_by_category
        ],
        topCustomersByRevenue=top_customers_by_revenue,
        recentCustomers=recent_customers,
        customerGrowthTrend=customer_growth_trend,
        customerRevenueContribution=customer_revenue_contribution,
    )


def _get_company_sales_analytics(
    db,
    company_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    sales_channel: str | None = None,
    payment_method: str | None = None,
    customer: str | None = None,
) -> dict[str, object]:
    from_date = _parse_dashboard_datetime(date_from)
    to_date = _parse_dashboard_datetime(date_to)
    dialect = db.bind.dialect.name

    base_transactions = _base_sales_transaction_query(
        db,
        company_id,
        from_date=from_date,
        to_date=to_date,
        product=product,
        category=category,
        brand=brand,
        sales_channel=sales_channel,
        payment_method=payment_method,
        customer=customer,
    )
    base_lines = _base_sales_line_query(
        db,
        company_id,
        from_date=from_date,
        to_date=to_date,
        product=product,
        category=category,
        brand=brand,
        sales_channel=sales_channel,
        payment_method=payment_method,
        customer=customer,
    )

    kpi_row = (
        base_transactions.with_entities(
            func.count(SalesTransaction.id).label("orders"),
            func.coalesce(func.sum(SalesTransaction.totalAmount), 0).label("revenue"),
            func.coalesce(func.sum(SalesTransaction.discountAmount), 0).label("discount"),
            func.coalesce(func.sum(SalesTransaction.taxAmount), 0).label("tax"),
        )
        .first()
    )
    total_orders = int(kpi_row.orders)
    total_revenue = float(kpi_row.revenue)
    total_discount = float(kpi_row.discount)
    total_tax = float(kpi_row.tax)
    total_products_sold = int(base_lines.with_entities(func.coalesce(func.sum(SalesTransactionLine.quantity), 0)).scalar() or 0)
    average_order_value = (total_revenue / total_orders) if total_orders else 0

    revenue_trend, sales_trend, order_trend = _aggregated_trends(base_transactions, base_lines, dialect)

    payment_rows = _dimension_distribution(base_transactions, SalesTransaction.paymentMethod)
    payment_methods = [
        {"paymentMethod": entry["label"], "revenue": entry["revenue"], "orders": entry["orders"]}
        for entry in payment_rows
    ]
    payment_methods.sort(key=lambda item: item["revenue"], reverse=True)

    return {
        "totalRevenue": round(total_revenue, 2),
        "totalOrders": total_orders,
        "totalProductsSold": total_products_sold,
        "averageOrderValue": round(average_order_value, 2),
        "totalDiscount": round(total_discount, 2),
        "totalTax": round(total_tax, 2),
        "revenueTrend": revenue_trend,
        "salesTrend": sales_trend,
        "orderTrend": order_trend,
        "paymentMethods": payment_methods,
    }


def _get_company_top_products(
    db,
    company_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    sales_channel: str | None = None,
    payment_method: str | None = None,
    customer: str | None = None,
    limit: int | None = 50,
) -> list[dict[str, object]]:
    from_date = _parse_dashboard_datetime(date_from)
    to_date = _parse_dashboard_datetime(date_to)
    base_lines = _base_sales_line_query(
        db,
        company_id,
        from_date=from_date,
        to_date=to_date,
        product=product,
        category=category,
        brand=brand,
        sales_channel=sales_channel,
        payment_method=payment_method,
        customer=customer,
    )
    rows = (
        base_lines.with_entities(
            Product.name,
            Product.sku,
            func.coalesce(func.sum(SalesTransactionLine.quantity), 0).label("quantity"),
            _sales_line_revenue_expr().label("revenue"),
        )
        .group_by(Product.id, Product.name, Product.sku)
        .order_by(desc("revenue"))
        .limit(_sanitized_limit(limit, 50, 200))
        .all()
    )
    return [
        {"name": row.name, "sku": row.sku, "quantity": int(row.quantity), "revenue": round(float(row.revenue), 2)}
        for row in rows
    ]


def _get_company_top_customers(
    db,
    company_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    sales_channel: str | None = None,
    payment_method: str | None = None,
    customer: str | None = None,
    limit: int | None = 20,
) -> list[dict[str, object]]:
    from_date = _parse_dashboard_datetime(date_from)
    to_date = _parse_dashboard_datetime(date_to)
    query = db.query(SalesTransaction).filter(SalesTransaction.companyId == company_id)
    if from_date:
        query = query.filter(SalesTransaction.saleDateTime >= from_date)
    if to_date:
        query = query.filter(SalesTransaction.saleDateTime <= to_date)
    if sales_channel:
        query = query.filter(SalesTransaction.salesChannel.ilike(f"%{sales_channel}%"))
    if payment_method:
        query = query.filter(SalesTransaction.paymentMethod.ilike(f"%{payment_method}%"))
    if customer:
        query = query.filter(SalesTransaction.customerName.ilike(f"%{customer}%"))

    name_expr = func.coalesce(SalesTransaction.customerName, "Walk-in Customer")
    rows = (
        query.with_entities(
            name_expr.label("name"),
            func.count(SalesTransaction.id).label("orders"),
            func.coalesce(func.sum(SalesTransaction.totalAmount), 0).label("total_spend"),
        )
        .group_by(SalesTransaction.customerId, name_expr)
        .order_by(desc("total_spend"))
        .limit(_sanitized_limit(limit, 20, 200))
        .all()
    )
    return [
        {
            "name": row.name,
            "orders": int(row.orders),
            "totalSpend": round(float(row.total_spend), 2),
            "averageOrderValue": round(float(row.total_spend) / int(row.orders), 2) if int(row.orders) else 0.0,
        }
        for row in rows
    ]


def _product_category_snapshot(db, category_id: int) -> tuple[int, str]:
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="Invalid category")
    return category.id, category.name


# ---------------------------------------------------------------------------
# Sales helpers
# ---------------------------------------------------------------------------

def _build_sales_line_payloads(db, user, payload: SalesTransactionRequest) -> list[dict]:
    if payload.lines:
        raw_lines = payload.lines
    elif payload.productId is not None and payload.quantity is not None:
        raw_lines = [SalesLineRequest(productId=payload.productId, quantity=payload.quantity, unitPrice=payload.unitPrice)]
    else:
        raise HTTPException(status_code=400, detail="At least one line item is required")

    line_payloads: list[dict] = []
    for line in raw_lines:
        product = db.query(Product).filter(Product.id == line.productId, Product.companyId == user.companyId).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {line.productId}")
        if not _is_product_active(product):
            raise HTTPException(
                status_code=400,
                detail=f"Inactive product cannot be used in new transactions: {product.sku}",
            )

        category_id = product.categoryId or 0
        category_name = ""
        if category_id:
            category_id, category_name = _product_category_snapshot(db, category_id)

        unit_price = float(line.unitPrice if line.unitPrice is not None else product.unitPrice or 0)
        quantity = int(line.quantity)
        available_stock = int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0)
        if quantity > available_stock:
            raise HTTPException(status_code=400, detail=f"Quantity sold cannot exceed available stock for product: {product.sku}")
        line_total = unit_price * quantity
        line_payloads.append(
            {
                "product": product,
                "productId": product.id,
                "categoryIdSnapshot": category_id,
                "categoryNameSnapshot": category_name,
                "quantity": quantity,
                "unitPrice": unit_price,
                "availableStock": available_stock,
                "lineTotal": line_total,
            }
        )

    return line_payloads


def _sales_transaction_delta_map(line_payloads: list[dict], sign: int) -> dict[int, int]:
    deltas: dict[int, int] = {}
    for line in line_payloads:
        product_id = int(line["productId"])
        deltas[product_id] = deltas.get(product_id, 0) + (int(line["quantity"]) * sign)
    return deltas


def _record_stock_movement(
    db,
    company_id: int,
    product,
    movement_type: str,
    previous_quantity: int,
    updated_quantity: int,
    quantity_changed: int,
    reference: str | None = None,
    sale_id: int | None = None,
    actor: str | None = None,
    actor_user_id: int | None = None,
) -> None:
    db.add(
        StockMovement(
            companyId=company_id,
            productId=product.id,
            productName=product.name,
            sku=product.sku,
            movementType=movement_type,
            previousQuantity=previous_quantity,
            updatedQuantity=updated_quantity,
            quantityChanged=quantity_changed,
            reference=reference,
            saleId=sale_id,
            actor=actor,
            actorUserId=actor_user_id,
        )
    )


def _apply_sales_stock_delta(
    db,
    company_id: int,
    deltas: dict[int, int],
    company_name: str | None = None,
    actor_email: str | None = None,
    invoice_number: str | None = None,
    movement_type: str = "Sale",
    sale_id: int | None = None,
    actor_user_id: int | None = None,
) -> None:
    for product_id, delta in deltas.items():
        if delta == 0:
            continue
        product = db.query(Product).filter(Product.id == product_id, Product.companyId == company_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {product_id}")
        current_stock = int(product.stockQuantity if product.stockQuantity is not None else 0)
        updated_stock = current_stock + delta
        if updated_stock < 0:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for product: {product.sku}")
        _record_stock_movement(
            db,
            company_id,
            product,
            movement_type,
            current_stock,
            updated_stock,
            delta,
            reference=invoice_number,
            sale_id=sale_id,
            actor=actor_email,
            actor_user_id=actor_user_id,
        )
        product.stockQuantity = updated_stock
        product.initialStockQuantity = updated_stock
        if actor_email:
            create_audit_log(
                db,
                company=company_name or str(company_id),
                user=actor_email,
                action="Inventory Updated",
                entity_name=product.name,
                invoice_number=invoice_number,
                product_name=product.name,
                commit=False,
            )
        if updated_stock == 0:
            product.status = "out_of_stock"
            create_notification(db, company_id, product.id, product.name, f"{product.name} is out of stock.", "out_of_stock")
            if actor_email:
                create_audit_log(
                    db,
                    company=company_name or str(company_id),
                    user=actor_email,
                    action="Product Marked Out of Stock",
                    entity_name=product.name,
                    invoice_number=invoice_number,
                    product_name=product.name,
                    commit=False,
                )
        elif updated_stock <= LOW_STOCK_THRESHOLD:
            create_notification(db, company_id, product.id, product.name, f"{product.name} stock is low ({updated_stock} remaining).", "low_stock")
        elif (product.status or "").lower() == "out_of_stock":
            product.status = "active"
        product.updatedAt = datetime.now(timezone.utc)


def _resolve_sale_customer(
    db,
    user,
    payload: SalesTransactionRequest,
    current_customer_name: str | None = None,
    current_customer_id: int | None = None,
) -> tuple[str, int | None]:
    customer_id = payload.customerId
    customer = None
    if customer_id is not None:
        customer = (
            db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.companyId == user.companyId,
                Customer.isDeleted != 1,
            )
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail=f"Customer not found: {customer_id}")
    elif current_customer_id is not None:
        customer_id = current_customer_id

    customer_name = (payload.customerName or "").strip()
    if not customer_name and current_customer_name:
        customer_name = current_customer_name.strip()
    if customer and not customer_name:
        customer_name = (customer.name or "").strip()
    if not customer_name:
        customer_name = "Walk-in Customer"
    return customer_name, customer_id


def _save_sales_transaction(db, tx, line_payloads: list[dict], payload: SalesTransactionRequest, user) -> object:
    subtotal_amount = sum(float(line["lineTotal"]) for line in line_payloads)
    discount_amount = float(payload.discountAmount or 0)
    tax_amount = float(payload.taxAmount or 0)
    if discount_amount > subtotal_amount:
        raise HTTPException(status_code=400, detail="Discount cannot exceed total product value")
    total_amount = subtotal_amount - discount_amount + tax_amount
    if total_amount < 0:
        raise HTTPException(status_code=400, detail="Total amount cannot be negative")

    customer_name, customer_id = _resolve_sale_customer(
        db,
        user,
        payload,
        current_customer_name=tx.customerName,
        current_customer_id=tx.customerId,
    )
    tx.customerId = customer_id
    tx.customerName = customer_name
    tx.status = "completed"
    tx.saleDateTime = _parse_sale_datetime(payload.saleDateTime)
    tx.salesChannel = (payload.salesChannel or "In-Store").strip()
    tx.paymentMethod = (payload.paymentMethod or "Cash").strip()
    tx.paymentStatus = (payload.paymentStatus or "Paid").strip()
    tx.notes = (payload.notes or "").strip() or None
    tx.subtotalAmount = subtotal_amount
    tx.discountAmount = discount_amount
    tx.taxAmount = tax_amount
    tx.totalAmount = total_amount
    tx.updatedAt = datetime.now(timezone.utc)

    db.flush()
    if not tx.invoiceNumber:
        tx.invoiceNumber = _next_company_invoice_number(db, tx.companyId, tx.saleDateTime or datetime.now(timezone.utc))
    duplicate_invoice = (
        db.query(SalesTransaction)
        .filter(
            SalesTransaction.companyId == tx.companyId,
            SalesTransaction.invoiceNumber == tx.invoiceNumber,
            SalesTransaction.id != tx.id,
        )
        .first()
    )
    if duplicate_invoice:
        raise HTTPException(status_code=400, detail="Duplicate invoice number")

    db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == tx.id).delete()
    remaining_stock_by_product = {
        row.id: int(row.stockQuantity if row.stockQuantity is not None else row.initialStockQuantity or 0)
        for row in db.query(Product).filter(
            Product.companyId == tx.companyId,
            Product.id.in_([line["productId"] for line in line_payloads]),
        ).all()
    }
    for index, line in enumerate(line_payloads):
        line_subtotal = float(line["lineTotal"])
        line_discount = 0.0
        line_tax = 0.0
        if subtotal_amount > 0:
            line_discount = round(discount_amount * (line_subtotal / subtotal_amount), 2)
            line_tax = round(tax_amount * (line_subtotal / subtotal_amount), 2)
        if index == len(line_payloads) - 1:
            allocated_discount = sum(
                round(discount_amount * (float(item["lineTotal"]) / subtotal_amount), 2) if subtotal_amount > 0 else 0.0
                for item in line_payloads[:-1]
            )
            allocated_tax = sum(
                round(tax_amount * (float(item["lineTotal"]) / subtotal_amount), 2) if subtotal_amount > 0 else 0.0
                for item in line_payloads[:-1]
            )
            line_discount = round(discount_amount - allocated_discount, 2)
            line_tax = round(tax_amount - allocated_tax, 2)
        db.add(
            SalesTransactionLine(
                transactionId=tx.id,
                productId=line["productId"],
                categoryIdSnapshot=line["categoryIdSnapshot"],
                categoryNameSnapshot=line["categoryNameSnapshot"],
                quantity=line["quantity"],
                unitPrice=line["unitPrice"],
                discountAmount=line_discount,
                taxAmount=line_tax,
                lineTotal=round(line_subtotal - line_discount + line_tax, 2),
                productNameSnapshot=line["product"].name,
                skuSnapshot=line["product"].sku,
                remainingStockSnapshot=remaining_stock_by_product.get(line["productId"]),
            )
        )

    db.commit()
    db.refresh(tx)
    return tx


def _transaction_response(db, tx) -> SalesTransactionResponse:
    lines = db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == tx.id).all()
    line_responses = [
        SalesLineResponse(
            productId=line.productId,
            productName=line.productNameSnapshot or "",
            sku=line.skuSnapshot or "",
            categoryId=line.categoryIdSnapshot or 0,
            categoryName=line.categoryNameSnapshot or "",
            quantity=line.quantity or 0,
            unitPrice=float(line.unitPrice or 0),
            lineTotal=float(line.lineTotal or 0),
            remainingStock=line.remainingStockSnapshot,
        )
        for line in lines
    ]
    salesperson = None
    if tx.createdBy:
        creator = db.query(User).filter(User.id == tx.createdBy).first()
        if creator:
            salesperson = creator.name or creator.email
    return SalesTransactionResponse(
        transactionId=tx.id,
        invoiceNumber=tx.invoiceNumber or _format_invoice_number(
            (tx.saleDateTime or datetime.now(timezone.utc)).year, tx.id
        ),
        companyId=tx.companyId,
        createdBy=tx.createdBy,
        customerId=tx.customerId,
        customerName=tx.customerName,
        saleDateTime=_datetime_to_iso(tx.saleDateTime) or "",
        status=tx.status or "completed",
        salesChannel=tx.salesChannel,
        paymentMethod=tx.paymentMethod,
        paymentStatus=tx.paymentStatus or "Paid",
        notes=tx.notes,
        salesperson=salesperson,
        subtotalAmount=float(tx.subtotalAmount or 0),
        discountAmount=float(tx.discountAmount or 0),
        taxAmount=float(tx.taxAmount or 0),
        totalAmount=float(tx.totalAmount or 0),
        createdAt=tx.createdAt.strftime("%Y-%m-%d %H:%M:%S") if tx.createdAt else "",
        updatedAt=_datetime_to_iso(tx.updatedAt),
        lines=line_responses,
    )
