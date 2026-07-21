from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import asc, desc, func

from backend.auth_utils import get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_sales_user, create_audit_log, create_notification
from backend.models import Category, Product, SalesTransaction, SalesTransactionLine, StockAdjustment
from backend.schemas import InventoryMovementResponse, InventoryResponse, StockAdjustmentRequest, StockAdjustmentResponse

LOW_STOCK_THRESHOLD = 5


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def list_inventory(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    brand: str | None = None,
    status_filter: str | None = None,
    authorization: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
) -> list[InventoryResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    query = db.query(Product).filter(Product.companyId == user.companyId)
    if q:
        wildcard = f"%{q}%"
        query = query.filter(
            Product.name.ilike(wildcard) | Product.sku.ilike(wildcard) | Product.brand.ilike(wildcard)
        )
    if categoryId:
        query = query.filter(Product.categoryId == categoryId)
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if status_filter:
        normalized_status = status_filter.lower().strip()
        query = query.filter(Product.status == normalized_status)

    normalized_sort_by = (sort_by or "product_name").strip().lower()
    normalized_sort_direction = (sort_direction or "asc").strip().lower()
    if normalized_sort_by == "current_stock":
        sort_expression = func.coalesce(Product.stockQuantity, Product.initialStockQuantity, 0)
    elif normalized_sort_by == "recently_updated":
        sort_expression = Product.updatedAt
    else:
        sort_expression = Product.name

    if normalized_sort_direction == "desc":
        query = query.order_by(desc(sort_expression))
    else:
        query = query.order_by(asc(sort_expression))

    items: list[InventoryResponse] = []
    for product in query.all():
        category_name = ""
        if product.categoryId:
            category = (
                db.query(Category)
                .filter(Category.id == product.categoryId, Category.companyId == user.companyId)
                .first()
            )
            if category:
                category_name = category.name or ""

        current_stock = int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0)
        initial_stock = int(product.initialStockQuantity if product.initialStockQuantity is not None else current_stock)
        reserved_stock = max(0, initial_stock - current_stock)
        available_stock = max(0, current_stock - reserved_stock)
        normalized_status = (product.status or "active").lower()
        if available_stock <= 0:
            stock_status = "out_of_stock"
            normalized_status = "out_of_stock"
        elif available_stock <= max(1, int(product.initialStockQuantity or 0) // 4 if product.initialStockQuantity else 5):
            stock_status = "low_stock"
            normalized_status = "low_stock"
        else:
            stock_status = "in_stock"
            normalized_status = "active"
        product.status = normalized_status

        items.append(
            InventoryResponse(
                productId=product.id,
                productName=product.name,
                sku=product.sku,
                categoryId=product.categoryId,
                categoryName=category_name,
                brand=product.brand or "",
                currentStock=current_stock,
                reservedStock=reserved_stock,
                availableStock=available_stock,
                reorderLevel=max(0, int(initial_stock * 0.25)),
                stockStatus=stock_status,
                status=normalized_status,
                updatedAt=product.updatedAt.isoformat() if product.updatedAt else None,
            )
        )

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="List Inventory",
        ip_address="Unknown",
        browser="Unknown",
    )
    return items


def create_stock_adjustment(
    product_id: int,
    payload: StockAdjustmentRequest,
    db: DbDependency,
    authorization: str | None = None,
) -> StockAdjustmentResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    current_stock = int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0)
    if current_stock < 0:
        raise HTTPException(status_code=400, detail="Stock quantity cannot be negative")

    normalized_reason = (payload.reason or "").strip()
    if not normalized_reason:
        raise HTTPException(status_code=400, detail="A reason is required for every stock adjustment")

    adjustment_quantity = payload.quantity
    if adjustment_quantity <= 0:
        raise HTTPException(status_code=400, detail="Adjustment quantity must be greater than zero")

    if payload.adjustmentType == "stock_out":
        if current_stock < adjustment_quantity:
            raise HTTPException(status_code=400, detail="Stock out quantity cannot exceed available stock")
        new_stock = current_stock - adjustment_quantity
    else:
        new_stock = current_stock + adjustment_quantity

    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Stock quantity cannot become negative")

    product.stockQuantity = new_stock
    product.initialStockQuantity = new_stock if product.initialStockQuantity is None else product.initialStockQuantity
    product.updatedAt = datetime.now(timezone.utc)

    movement_type = "Stock Added" if payload.adjustmentType == "stock_in" else "Stock Removed" if payload.adjustmentType == "stock_out" else "Stock Adjusted"
    action_name = "Stock Added" if payload.adjustmentType == "stock_in" else "Stock Removed" if payload.adjustmentType == "stock_out" else "Stock Adjusted"

    if payload.adjustmentType == "manual_adjustment":
        create_notification(
            db,
            user.companyId,
            product.id,
            product.name,
            f"{product.name} stock was manually adjusted ({adjustment_quantity} units).",
            "manual_adjustment",
        )
        create_audit_log(
            db,
            company=str(user.companyId),
            user=user.email,
            action="Stock Adjusted",
            entity_name=product.name,
            product_name=product.name,
            ip_address="Unknown",
            browser="Unknown",
            commit=False,
        )
    if new_stock <= 0:
        product.status = "out_of_stock"
        create_notification(
            db,
            user.companyId,
            product.id,
            product.name,
            f"{product.name} is out of stock.",
            "out_of_stock",
        )
        create_audit_log(
            db,
            company=str(user.companyId),
            user=user.email,
            action="Product Became Out of Stock",
            entity_name=product.name,
            product_name=product.name,
            ip_address="Unknown",
            browser="Unknown",
            commit=False,
        )
    elif new_stock <= LOW_STOCK_THRESHOLD:
        product.status = "low_stock"
        create_notification(
            db,
            user.companyId,
            product.id,
            product.name,
            f"{product.name} stock is low ({new_stock} remaining).",
            "low_stock",
        )
        create_audit_log(
            db,
            company=str(user.companyId),
            user=user.email,
            action="Product Reached Low Stock",
            entity_name=product.name,
            product_name=product.name,
            ip_address="Unknown",
            browser="Unknown",
            commit=False,
        )
    elif (product.status or "").lower() in {"out_of_stock", "low_stock"}:
        product.status = "active"

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action=action_name,
        entity_name=product.name,
        product_name=product.name,
        ip_address="Unknown",
        browser="Unknown",
        commit=False,
    )

    adjustment = StockAdjustment(
        companyId=user.companyId,
        productId=product.id,
        adjustmentType=payload.adjustmentType,
        quantity=adjustment_quantity,
        reason=normalized_reason,
        remarks=payload.remarks or "",
        adjustedBy=user.email,
        adjustedByUserId=user.id,
        adjustmentDate=datetime.now(timezone.utc),
    )
    db.add(adjustment)
    db.commit()
    db.refresh(adjustment)

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Create Stock Adjustment",
        entity_name=product.name,
        product_name=product.name,
        ip_address="Unknown",
        browser="Unknown",
    )

    return StockAdjustmentResponse(
        id=adjustment.id,
        productId=product.id,
        productName=product.name,
        sku=product.sku,
        adjustmentType=adjustment.adjustmentType,
        quantity=adjustment.quantity,
        reason=adjustment.reason,
        remarks=adjustment.remarks or None,
        adjustedBy=adjustment.adjustedBy,
        adjustmentDate=adjustment.adjustmentDate.isoformat() if adjustment.adjustmentDate else None,
    )


def list_inventory_movements(
    product_id: int,
    db: DbDependency,
    authorization: str | None = None,
) -> list[InventoryMovementResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    movements: list[InventoryMovementResponse] = []
    initial_stock = int(product.initialStockQuantity if product.initialStockQuantity is not None else product.stockQuantity or 0)
    if initial_stock > 0:
        movements.append(
            InventoryMovementResponse(
                id=f"initial-{product.id}",
                productId=product.id,
                productName=product.name,
                sku=product.sku,
                movementType="Initial Stock",
                previousQuantity=0,
                updatedQuantity=initial_stock,
                quantityChanged=initial_stock,
                reason="Initial stock",
                user="System",
                reference="Initial stock",
                timestamp=product.createdAt.isoformat() if product.createdAt else None,
            )
        )

    sale_lines = (
        db.query(SalesTransactionLine, SalesTransaction)
        .join(SalesTransaction, SalesTransaction.id == SalesTransactionLine.transactionId)
        .filter(SalesTransaction.companyId == user.companyId, SalesTransactionLine.productId == product_id)
        .order_by(SalesTransaction.saleDateTime.asc(), SalesTransactionLine.id.asc())
        .all()
    )
    for sale_line, transaction in sale_lines:
        movements.append(
            InventoryMovementResponse(
                id=f"sale-{sale_line.id}",
                productId=product.id,
                productName=product.name,
                sku=product.sku,
                movementType="Sale",
                previousQuantity=(int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0) + int(sale_line.quantity or 0)),
                updatedQuantity=int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0),
                quantityChanged=-int(sale_line.quantity or 0),
                reason=transaction.invoiceNumber or f"Sale #{transaction.id}",
                user=transaction.createdBy or "System",
                reference=transaction.invoiceNumber or f"Sale #{transaction.id}",
                timestamp=transaction.saleDateTime.isoformat() if transaction.saleDateTime else None,
            )
        )

    adjustments = (
        db.query(StockAdjustment)
        .filter(StockAdjustment.companyId == user.companyId, StockAdjustment.productId == product_id)
        .order_by(StockAdjustment.adjustmentDate.asc(), StockAdjustment.id.asc())
        .all()
    )
    for adjustment in adjustments:
        quantity_change = adjustment.quantity if adjustment.adjustmentType == "stock_in" else -adjustment.quantity
        previous_quantity = int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0) - quantity_change
        if adjustment.adjustmentType == "stock_out":
            updated_quantity = previous_quantity + quantity_change
        else:
            updated_quantity = previous_quantity + quantity_change
        movements.append(
            InventoryMovementResponse(
                id=f"adjustment-{adjustment.id}",
                productId=product.id,
                productName=product.name,
                sku=product.sku,
                movementType="Stock Addition" if adjustment.adjustmentType == "stock_in" else "Stock Removal" if adjustment.adjustmentType == "stock_out" else "Manual Adjustment",
                previousQuantity=previous_quantity,
                updatedQuantity=updated_quantity,
                quantityChanged=quantity_change,
                reason=adjustment.reason,
                user=adjustment.adjustedBy,
                reference=adjustment.reason,
                timestamp=adjustment.adjustmentDate.isoformat() if adjustment.adjustmentDate else None,
            )
        )

    if not movements:
        movements.append(
            InventoryMovementResponse(
                id=f"empty-{product.id}",
                productId=product.id,
                productName=product.name,
                sku=product.sku,
                movementType="No Activity",
                previousQuantity=0,
                updatedQuantity=0,
                quantityChanged=0,
                reason="No stock movements recorded",
                user="System",
                reference="No stock movements recorded",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

    movements.sort(key=lambda item: item.timestamp or "", reverse=True)
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="View Inventory Movements",
        entity_name=product.name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return movements


def list_stock_adjustments(
    product_id: int,
    db: DbDependency,
    authorization: str | None = None,
) -> list[StockAdjustmentResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    adjustments = (
        db.query(StockAdjustment)
        .filter(StockAdjustment.companyId == user.companyId, StockAdjustment.productId == product_id)
        .order_by(StockAdjustment.adjustmentDate.desc(), StockAdjustment.id.desc())
        .all()
    )
    return [
        StockAdjustmentResponse(
            id=adjustment.id,
            productId=product.id,
            productName=product.name,
            sku=product.sku,
            adjustmentType=adjustment.adjustmentType,
            quantity=adjustment.quantity,
            reason=adjustment.reason,
            remarks=adjustment.remarks or None,
            adjustedBy=adjustment.adjustedBy,
            adjustmentDate=adjustment.adjustmentDate.isoformat() if adjustment.adjustmentDate else None,
        )
        for adjustment in adjustments
    ]
