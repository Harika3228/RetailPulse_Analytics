import re
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.database import engine
from backend.models import (
    AuditLog, Category, Notification, Product, SalesTransaction,
    SalesTransactionLine,
)
from backend.schemas import (
    NotificationResponse,
    ProductResponse, ProductSummaryResponse, SalesDashboardSummaryResponse,
    SalesLineRequest, SalesLineResponse,
    SalesTransactionRequest, SalesTransactionResponse,
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
    ip_address: str | None = None,
    browser: str | None = None,
    commit: bool = True,
) -> None:
    entry = AuditLog(
        company=company,
        entityName=entity_name,
        invoiceNumber=invoice_number,
        productName=product_name,
        user=user,
        action=action,
        ipAddress=ip_address or "Unknown",
        browser=browser or "Unknown",
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    if commit:
        db.commit()


def create_notification(db, company_id: int, product_id: int, product_name: str, message: str, notification_type: str) -> None:
    existing = (
        db.query(Notification)
        .filter(
            Notification.companyId == company_id,
            Notification.productId == product_id,
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
            productId=product_id,
            productName=product_name,
            message=message,
            type=notification_type,
            isRead=0,
        )
    )


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
    transactions = db.query(SalesTransaction).filter(SalesTransaction.companyId == company_id).all()
    total_orders = len(transactions)
    total_revenue = sum(float(item.totalAmount or 0) for item in transactions)
    total_sales = sum(
        int(line.quantity or 0)
        for line in db.query(SalesTransactionLine)
        .join(SalesTransaction, SalesTransaction.id == SalesTransactionLine.transactionId)
        .filter(SalesTransaction.companyId == company_id)
        .all()
    )
    average_order_value = (total_revenue / total_orders) if total_orders else 0
    return SalesDashboardSummaryResponse(
        totalSales=total_sales,
        totalRevenue=total_revenue,
        totalOrders=total_orders,
        averageOrderValue=average_order_value,
    )


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


def _apply_sales_stock_delta(db, company_id: int, deltas: dict[int, int], company_name: str | None = None, actor_email: str | None = None, invoice_number: str | None = None) -> None:
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


def _save_sales_transaction(db, tx, line_payloads: list[dict], payload: SalesTransactionRequest, user) -> object:
    subtotal_amount = sum(float(line["lineTotal"]) for line in line_payloads)
    discount_amount = float(payload.discountAmount or 0)
    tax_amount = float(payload.taxAmount or 0)
    if discount_amount > subtotal_amount:
        raise HTTPException(status_code=400, detail="Discount cannot exceed total product value")
    total_amount = subtotal_amount - discount_amount + tax_amount
    if total_amount < 0:
        raise HTTPException(status_code=400, detail="Total amount cannot be negative")

    tx.customerName = (payload.customerName or "Walk-in Customer").strip()
    tx.saleDateTime = _parse_sale_datetime(payload.saleDateTime)
    tx.salesChannel = (payload.salesChannel or "In-Store").strip()
    tx.paymentMethod = (payload.paymentMethod or "Cash").strip()
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
    return SalesTransactionResponse(
        transactionId=tx.id,
        invoiceNumber=tx.invoiceNumber or _format_invoice_number(
            (tx.saleDateTime or datetime.now(timezone.utc)).year, tx.id
        ),
        companyId=tx.companyId,
        createdBy=tx.createdBy,
        customerName=tx.customerName,
        saleDateTime=_datetime_to_iso(tx.saleDateTime) or "",
        salesChannel=tx.salesChannel,
        paymentMethod=tx.paymentMethod,
        subtotalAmount=float(tx.subtotalAmount or 0),
        discountAmount=float(tx.discountAmount or 0),
        taxAmount=float(tx.taxAmount or 0),
        totalAmount=float(tx.totalAmount or 0),
        createdAt=tx.createdAt.strftime("%Y-%m-%d %H:%M:%S") if tx.createdAt else "",
        updatedAt=_datetime_to_iso(tx.updatedAt),
        lines=line_responses,
    )
