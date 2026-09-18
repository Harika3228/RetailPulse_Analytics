import math
import json
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import asc, desc, func

from backend.auth_utils import get_current_user
from backend.cache import invalidate_forecast_cache, get_cached_forecast, set_cached_forecast
from backend.database import DbDependency
from backend.helpers import (
    AuditLogCollector,
    NotificationCollector,
    _ensure_sales_user,
    create_audit_log,
    create_notification,
)
from backend.models import Category, Product, SalesTransaction, SalesTransactionLine, StockAdjustment
from backend.schemas import (
    ForecastSeriesPoint,
    ForecastSeriesResponse,
    InventoryForecastItemResponse,
    InventoryForecastSummaryResponse,
    InventoryMovementResponse,
    InventoryRecommendationItem,
    InventoryRecommendationSummary,
    InventoryResponse,
    ProductRecommendationDetail,
    StockAdjustmentRequest,
    StockAdjustmentResponse,
    TrendAnalysis,
    WeeklyDemandPoint,
)

LOW_STOCK_THRESHOLD = 5


def _classify_inventory_risk(
    current_stock: int,
    days_remaining: float,
    forecasted_demand: float,
    reorder_level: int,
    lead_time: int = 4,
    max_stock_level: int | None = None,
) -> str:
    if current_stock <= 0:
        return "out_of_stock"
    if days_remaining <= lead_time:
        return "stockout_risk"
    if current_stock <= reorder_level:
        return "low_stock"
    if max_stock_level is not None and current_stock > max_stock_level:
        return "overstock"
    return "healthy"


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def _resolve_forecast_period(period: str | None) -> tuple[str, int]:
    if period in {"7d", "next_7_days", "7-days"}:
        return "Next 7 Days", 7
    if period in {"30d", "next_30_days", "30-days"}:
        return "Next 30 Days", 30
    if period in {"90d", "next_90_days", "90-days"}:
        return "Next 90 Days", 90
    return "Next 30 Days", 30


def _build_recommendation(current_stock: int, reorder_level: int, historical_sales: float, predicted_demand: float) -> str:
    if current_stock <= 0:
        return "Immediate Restock Required"
    if current_stock <= max(1, reorder_level):
        return "Reorder Soon"
    if predicted_demand > historical_sales * 1.2 and current_stock < reorder_level * 2:
        return "Reorder Soon"
    if current_stock >= reorder_level * 2 and predicted_demand <= historical_sales * 1.05:
        return "Stock Level Healthy"
    if current_stock > reorder_level * 3:
        return "Overstock Risk"
    return "Stock Level Healthy"


def list_inventory(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    brand: str | None = None,
    status_filter: str | None = None,
    authorization: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    product: str | None = None,
    forecast_period: str | None = None,
    offset: int = 0,
    limit: int = 50,
    category: str | None = None,
) -> list[InventoryResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    cache_params = {
        "q": q, "categoryId": categoryId, "brand": brand,
        "status_filter": status_filter, "sort_by": sort_by,
        "sort_direction": sort_direction, "product": product,
        "forecast_period": forecast_period,
    }
    cached = get_cached_forecast(user.companyId, "inventory_list", **cache_params)
    if cached is not None:
        return cached

    query = db.query(Product).filter(Product.companyId == user.companyId)
    if q:
        wildcard = f"%{q}%"
        query = query.filter(
            Product.name.ilike(wildcard) | Product.sku.ilike(wildcard) | Product.brand.ilike(wildcard)
        )
    if product:
        wildcard = f"%{product}%"
        query = query.filter(Product.name.ilike(wildcard) | Product.sku.ilike(wildcard))
    if categoryId:
        query = query.filter(Product.categoryId == categoryId)
    if category:
        category_ids = [item.id for item in db.query(Category.id).filter(Category.companyId == user.companyId, Category.name.ilike(f"%{category.strip()}%" )).all()]
        query = query.filter(Product.categoryId.in_(category_ids)) if category_ids else query.filter(Product.id == -1)
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if status_filter:
        normalized_status = status_filter.lower().strip()
        query = query.filter(Product.status == normalized_status)

    normalized_sort_by = (sort_by or "product_name").strip().lower()
    normalized_sort_direction = (sort_direction or "asc").strip().lower()

    forecast_label, _ = _resolve_forecast_period(forecast_period)

    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.saleDateTime.asc())
        .all()
    )
    sales_lines = (
        db.query(SalesTransactionLine)
        .filter(SalesTransactionLine.transactionId.in_([transaction.id for transaction in transactions]))
        .all()
    )
    lines_by_product: dict[int, list[SalesTransactionLine]] = defaultdict(list)
    for line in sales_lines:
        lines_by_product[line.productId].append(line)

    audit_collector = AuditLogCollector(db)
    notif_collector = NotificationCollector(db)

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
        product_lines = lines_by_product.get(product.id, [])
        monthly_history: list[tuple[str, float]] = []
        for transaction in transactions:
            month = transaction.saleDateTime.strftime("%Y-%m") if transaction.saleDateTime else None
            if not month:
                continue
            matching_quantity = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
            monthly_history.append((month, float(matching_quantity)))
        history_by_month: dict[str, float] = defaultdict(float)
        for month, value in monthly_history:
            history_by_month[month] += value
        ordered_history = [(month, history_by_month[month]) for month in sorted(history_by_month.keys())[-6:]]
        historical_sales = sum(item[1] for item in ordered_history)
        if ordered_history:
            recent_values = [value for _, value in ordered_history[-3:]]
            trend = sum(recent_values[i + 1] - recent_values[i] for i in range(len(recent_values) - 1)) / max(1, len(recent_values) - 1)
            predicted_demand = max(0.0, float(ordered_history[-1][1] + trend))
            growth_rate = round(((predicted_demand - historical_sales) / max(abs(historical_sales), 1.0)) * 100, 2) if historical_sales else 0.0
            forecast_accuracy = round(max(0.0, min(100.0, 100 - abs(predicted_demand - historical_sales) / max(abs(historical_sales), 1.0) * 100)), 2) if historical_sales else 100.0
        else:
            predicted_demand = 0.0
            growth_rate = 0.0
            forecast_accuracy = 100.0
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

        num_days_with_sales = len(history_by_month) if history_by_month else 1
        first_sale_date = transactions[0].saleDateTime if transactions else None
        last_sale_date = transactions[-1].saleDateTime if transactions else None
        if first_sale_date and last_sale_date:
            span_days = max(1, (last_sale_date - first_sale_date).days + 1)
        else:
            span_days = max(1, num_days_with_sales)
        daily_demand_rate = historical_sales / span_days if span_days > 0 else 0.0
        forecasted_period_demand = predicted_demand
        days_of_stock_remaining = current_stock / max(daily_demand_rate, 0.01) if daily_demand_rate > 0 else 999.0

        daily_sales_map: dict[str, float] = defaultdict(float)
        for transaction in transactions:
            sale_date = transaction.saleDateTime
            if not sale_date:
                continue
            day_key = sale_date.strftime("%Y-%m-%d")
            matching_qty = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
            daily_sales_map[day_key] += float(matching_qty)
        all_daily_values = list(daily_sales_map.values())
        average_daily_sales = historical_sales / span_days if span_days > 0 else 0.0

        safety_stock = math.ceil(1.65 * (sum((v - average_daily_sales) ** 2 for v in all_daily_values) / max(1, len(all_daily_values))) ** 0.5) if all_daily_values else 0
        safety_stock = max(0, safety_stock)
        reorder_level = math.ceil(daily_demand_rate * 7 + safety_stock)

        risk_classification = _classify_inventory_risk(current_stock, days_of_stock_remaining, forecasted_period_demand, reorder_level)

        recommendation = _build_recommendation(current_stock, reorder_level, historical_sales, predicted_demand)
        latest_history_value = ordered_history[-1][1] if ordered_history else 0.0
        if available_stock <= 0:
            notif_collector.add(
                user.companyId,
                product.id,
                product.name,
                f"{product.name} is predicted to run out of stock.",
                "forecast_out_of_stock",
                target_role="admin",
                priority="critical",
                resource_type="Product",
                resource_id=product.id,
                alert_key=f"inventory:{user.companyId}:{product.id}:stockout",
            )
        elif current_stock <= reorder_level:
            notif_collector.add(
                user.companyId,
                product.id,
                product.name,
                f"{product.name} is at or below its reorder point ({reorder_level}).",
                "low_stock",
                target_role="admin",
                priority="medium",
                resource_type="Product",
                resource_id=product.id,
                alert_key=f"inventory:{user.companyId}:{product.id}:low_stock",
            )
        elif product.maxStockLevel is not None and current_stock > product.maxStockLevel:
            notif_collector.add(
                user.companyId,
                product.id,
                product.name,
                f"{product.name} exceeds its maximum stock level ({product.maxStockLevel}).",
                "overstock",
                target_role="admin",
                priority="medium",
                resource_type="Product",
                resource_id=product.id,
                alert_key=f"inventory:{user.companyId}:{product.id}:overstock",
            )
        elif predicted_demand > current_stock:
            notif_collector.add(
                user.companyId,
                product.id,
                product.name,
                f"{product.name} forecasted demand exceeds available inventory.",
                "forecast_demand_exceeds_inventory",
                target_role="admin",
                priority="high",
                resource_type="Product",
                resource_id=product.id,
                alert_key=f"inventory:{user.companyId}:{product.id}:forecast_risk",
            )
        elif predicted_demand > latest_history_value * 1.1:
            notif_collector.add(
                user.companyId,
                product.id,
                product.name,
                f"{product.name} shows significant demand growth.",
                "demand_growth_alert",
                target_role="admin",
                resource_type="Product",
                resource_id=product.id,
                alert_key=f"inventory:{user.companyId}:{product.id}:sales_growth",
            )

        audit_collector.add(
            company=str(user.companyId),
            user=user.email,
            action="Inventory Recommendation Generated",
            entity_name=product.name,
            product_name=product.name,
            category_name=category_name,
            forecast_period=forecast_label,
            ip_address="Unknown",
            browser="Unknown",
            deduplicate_key=f"inventory_recommendation:{product.id}",
        )

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
                reorderLevel=reorder_level,
                stockStatus=stock_status,
                status=normalized_status,
                riskClassification=risk_classification,
                recommendation=recommendation,
                predictedDemand=round(predicted_demand, 2),
                growthRate=round(growth_rate, 2),
                forecastAccuracy=round(forecast_accuracy, 2),
                forecastPeriod=forecast_label,
                updatedAt=product.updatedAt.isoformat() if product.updatedAt else None,
            )
        )

    def sort_key(item: InventoryResponse):
        if normalized_sort_by == "current_stock":
            return item.currentStock
        if normalized_sort_by == "recently_updated":
            return item.updatedAt or ""
        if normalized_sort_by == "highest_predicted_demand":
            return item.predictedDemand
        if normalized_sort_by == "lowest_stock":
            return item.currentStock
        if normalized_sort_by == "highest_growth":
            return item.growthRate
        if normalized_sort_by == "forecast_accuracy":
            return item.forecastAccuracy
        return item.productName.lower()

    items.sort(key=sort_key, reverse=normalized_sort_direction == "desc")

    audit_collector.add(
        company=str(user.companyId),
        user=user.email,
        action="List Inventory",
        ip_address="Unknown",
        browser="Unknown",
        deduplicate_key="list_inventory",
    )
    notif_collector.resolve_missing_inventory_alerts(user.companyId)
    audit_collector.flush()
    notif_collector.flush()
    db.commit()

    result = items[offset:offset + limit] if limit > 0 else items
    set_cached_forecast(user.companyId, "inventory_list", result, ttl=120, **cache_params)
    return result


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
            target_role="admin",
            resource_type="Product",
            resource_id=product.id,
            alert_key=f"inventory:{user.companyId}:{product.id}:manual_adjustment",
        )
        create_audit_log(
            db,
            company=str(user.companyId),
            user=user.email,
            action="Stock Adjusted",
            entity_name=product.name,
            product_name=product.name,
            resource_type="Product",
            resource_id=product.id,
            description=json.dumps({"before": {"stockQuantity": current_stock}, "after": {"stockQuantity": new_stock}, "reason": normalized_reason}),
            company_id=user.companyId,
            user_id=user.id,
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
            target_role="admin",
            priority="critical",
            resource_type="Product",
            resource_id=product.id,
            alert_key=f"inventory:{user.companyId}:{product.id}:stockout",
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
            target_role="admin",
            priority="medium",
            resource_type="Product",
            resource_id=product.id,
            alert_key=f"inventory:{user.companyId}:{product.id}:low_stock",
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
        resource_type="Product",
        resource_id=product.id,
        description=json.dumps({"before": {"stockQuantity": current_stock}, "after": {"stockQuantity": new_stock}, "reason": normalized_reason}),
        company_id=user.companyId,
        user_id=user.id,
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
    invalidate_forecast_cache(user.companyId)

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Create Stock Adjustment",
        entity_name=product.name,
        product_name=product.name,
        resource_type="Product",
        resource_id=product.id,
        description=json.dumps({"adjustmentId": adjustment.id, "quantity": adjustment_quantity, "reason": normalized_reason}),
        company_id=user.companyId,
        user_id=user.id,
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
                user=str(transaction.createdBy) if transaction.createdBy is not None else "System",
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
                user=str(adjustment.adjustedBy) if adjustment.adjustedBy is not None else "System",
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


def get_inventory_forecast(
    db: DbDependency,
    authorization: str | None = None,
    forecast_period: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    risk_filter: str | None = None,
    category_filter: str | None = None,
    brand_filter: str | None = None,
    reorder_required: str | None = None,
    q: str | None = None,
    lead_time: int = 4,
) -> InventoryForecastSummaryResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    cache_params = {
        "forecast_period": forecast_period, "sort_by": sort_by,
        "sort_direction": sort_direction, "risk_filter": risk_filter,
        "category_filter": category_filter, "brand_filter": brand_filter,
        "reorder_required": reorder_required, "q": q,
    }
    cached = get_cached_forecast(user.companyId, "inventory_forecast", **cache_params)
    if cached is not None:
        return cached

    _, period_days = _resolve_forecast_period(forecast_period)
    period_fraction = period_days / 30.0

    products = db.query(Product).filter(Product.companyId == user.companyId).all()
    if not products:
        return InventoryForecastSummaryResponse(
            totalProducts=0,
            outOfStockCount=0,
            stockoutRiskCount=0,
            lowStockCount=0,
            healthyCount=0,
            overstockCount=0,
            totalReorderQty=0,
            items=[],
        )

    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.saleDateTime.asc())
        .all()
    )

    transaction_ids = [tx.id for tx in transactions]
    sales_lines = (
        db.query(SalesTransactionLine)
        .filter(SalesTransactionLine.transactionId.in_(transaction_ids))
        .all()
        if transaction_ids
        else []
    )

    lines_by_product: dict[int, list[SalesTransactionLine]] = defaultdict(list)
    for line in sales_lines:
        lines_by_product[line.productId].append(line)

    category_cache: dict[int, str] = {}
    notif_collector = NotificationCollector(db)

    items: list[InventoryForecastItemResponse] = []

    for product in products:
        current_stock = int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0)

        if q:
            wildcard = q.lower().strip()
            if wildcard not in (product.name or "").lower() and wildcard not in (product.sku or "").lower():
                continue

        if product.categoryId not in category_cache:
            cat = db.query(Category).filter(Category.id == product.categoryId, Category.companyId == user.companyId).first()
            category_cache[product.categoryId] = cat.name if cat else "Uncategorized"
        category_name = category_cache[product.categoryId]

        product_lines = lines_by_product.get(product.id, [])

        daily_sales_map: dict[str, float] = defaultdict(float)
        for transaction in transactions:
            sale_date = transaction.saleDateTime
            if not sale_date:
                continue
            day_key = sale_date.strftime("%Y-%m-%d")
            matching_qty = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
            daily_sales_map[day_key] += float(matching_qty)

        all_daily_values = list(daily_sales_map.values())
        total_historical_sales = sum(all_daily_values)

        num_days_with_sales = len(daily_sales_map) if daily_sales_map else 1
        first_sale_date = transactions[0].saleDateTime if transactions else None
        last_sale_date = transactions[-1].saleDateTime if transactions else None
        if first_sale_date and last_sale_date:
            span_days = max(1, (last_sale_date - first_sale_date).days + 1)
        else:
            span_days = max(1, num_days_with_sales)

        average_daily_sales = total_historical_sales / span_days if span_days > 0 else 0.0

        monthly_history: dict[str, float] = defaultdict(float)
        for transaction in transactions:
            month = transaction.saleDateTime.strftime("%Y-%m") if transaction.saleDateTime else None
            if not month:
                continue
            matching_qty = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
            monthly_history[month] += float(matching_qty)

        ordered_months = [(m, monthly_history[m]) for m in sorted(monthly_history.keys())[-6:]]

        if len(ordered_months) >= 2:
            recent_values = [v for _, v in ordered_months[-3:]]
            trend = sum(recent_values[i + 1] - recent_values[i] for i in range(len(recent_values) - 1)) / max(1, len(recent_values) - 1)
            forecasted_demand = max(0.0, ordered_months[-1][1] + trend) * period_fraction
        elif ordered_months:
            forecasted_demand = ordered_months[-1][1] * period_fraction
        else:
            forecasted_demand = 0.0

        daily_demand_rate = forecasted_demand / period_days if period_days > 0 else average_daily_sales
        if daily_demand_rate <= 0 and average_daily_sales > 0:
            daily_demand_rate = average_daily_sales
        elif daily_demand_rate <= 0:
            daily_demand_rate = 0.001

        days_of_stock_remaining = current_stock / daily_demand_rate if daily_demand_rate > 0 else 9999.0

        safety_stock = math.ceil(1.65 * (sum((v - average_daily_sales) ** 2 for v in all_daily_values) / max(1, len(all_daily_values))) ** 0.5) if all_daily_values else 0
        safety_stock = max(0, safety_stock)

        reorder_point = math.ceil(daily_demand_rate * lead_time + safety_stock)

        max_stock_level = product.maxStockLevel if hasattr(product, 'maxStockLevel') and product.maxStockLevel else None

        if current_stock <= reorder_point:
            target_stock = forecasted_demand + safety_stock
            base_reorder_qty = math.ceil(target_stock - current_stock)
            if max_stock_level is not None:
                max_capacity_qty = max(0, max_stock_level - current_stock)
                recommended_reorder_qty = max(0, min(base_reorder_qty, max_capacity_qty))
            else:
                recommended_reorder_qty = max(0, base_reorder_qty)
        else:
            recommended_reorder_qty = 0

        risk_classification = _classify_inventory_risk(current_stock, days_of_stock_remaining, forecasted_demand, reorder_point, lead_time, max_stock_level)
        stock_risk = risk_classification
        reorder_required = recommended_reorder_qty > 0

        if risk_classification == "out_of_stock":
            recommendation = "Immediate Reorder Required"
        elif risk_classification == "stockout_risk":
            recommendation = "Reorder Soon"
        elif risk_classification == "low_stock":
            recommendation = "Plan Reorder"
        elif risk_classification == "overstock":
            recommendation = "Reduce Stock Level"
        else:
            recommendation = "Stock Level Adequate"

        if current_stock <= 0:
            notif_collector.add(
                user.companyId,
                product.id,
                product.name,
                f"{product.name} is out of stock and requires immediate reorder.",
                "reorder_critical",
            )
        elif days_of_stock_remaining <= 7:
            notif_collector.add(
                user.companyId,
                product.id,
                product.name,
                f"{product.name} has approximately {days_of_stock_remaining:.0f} days of stock remaining.",
                "reorder_warning",
            )

        items.append(
            InventoryForecastItemResponse(
                productId=product.id,
                productName=product.name,
                sku=product.sku,
                categoryId=product.categoryId,
                categoryName=category_name,
                brand=product.brand or "",
                currentStock=current_stock,
                averageDailySales=round(average_daily_sales, 2),
                forecastedDemand=round(forecasted_demand, 2),
                daysOfStockRemaining=round(days_of_stock_remaining, 1),
                leadTime=lead_time,
                reorderPoint=reorder_point,
                safetyStock=safety_stock,
                maxStockLevel=max_stock_level,
                recommendedReorderQty=recommended_reorder_qty,
                stockRisk=stock_risk,
                riskClassification=risk_classification,
                reorderRequired=reorder_required,
                recommendation=recommendation,
            )
        )

    risk_order = {"out_of_stock": 0, "stockout_risk": 1, "low_stock": 2, "healthy": 3, "overstock": 4}
    normalized_sort = (sort_by or "stock_risk").strip().lower()
    normalized_direction = (sort_direction or "asc").strip().lower()

    def _sort_key(item: InventoryForecastItemResponse):
        if normalized_sort == "product_name":
            return item.productName.lower()
        if normalized_sort == "current_stock":
            return item.currentStock
        if normalized_sort == "average_daily_sales":
            return item.averageDailySales
        if normalized_sort == "forecasted_demand":
            return item.forecastedDemand
        if normalized_sort == "days_of_stock_remaining":
            return item.daysOfStockRemaining
        if normalized_sort == "reorder_point":
            return item.reorderPoint
        if normalized_sort == "recommended_reorder_qty":
            return item.recommendedReorderQty
        if normalized_sort in ("stock_risk", "risk_level"):
            return risk_order.get(item.stockRisk, 5)
        if normalized_sort == "category":
            return (item.categoryName or "").lower()
        if normalized_sort == "brand":
            return (item.brand or "").lower()
        return risk_order.get(item.stockRisk, 5)

    items.sort(key=_sort_key, reverse=normalized_direction == "desc")

    if risk_filter and risk_filter.strip().lower() != "all":
        risk_value = risk_filter.strip().lower()
        items = [item for item in items if item.stockRisk == risk_value]

    if category_filter and category_filter.strip().lower() != "all":
        cat_value = category_filter.strip().lower()
        items = [item for item in items if (item.categoryName or "").lower() == cat_value]

    if brand_filter and brand_filter.strip().lower() != "all":
        brand_value = brand_filter.strip().lower()
        items = [item for item in items if (item.brand or "").lower() == brand_value]

    if reorder_required and reorder_required.strip().lower() != "all":
        want_reorder = reorder_required.strip().lower() in ("yes", "true", "1")
        if want_reorder:
            items = [item for item in items if item.recommendedReorderQty > 0]
        else:
            items = [item for item in items if item.recommendedReorderQty <= 0]

    critical_count = sum(1 for item in items if item.riskClassification == "out_of_stock")
    high_count = sum(1 for item in items if item.riskClassification == "stockout_risk")
    medium_count = sum(1 for item in items if item.riskClassification == "low_stock")
    low_count = sum(1 for item in items if item.riskClassification == "healthy")
    safe_count = sum(1 for item in items if item.riskClassification == "overstock")
    reorder_required_count = sum(1 for item in items if item.reorderRequired)
    total_reorder_qty = sum(item.recommendedReorderQty for item in items)

    notif_collector.flush()
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Inventory Forecast Viewed",
        ip_address="Unknown",
        browser="Unknown",
    )

    result = InventoryForecastSummaryResponse(
        totalProducts=len(items),
        reorderRequiredCount=reorder_required_count,
        outOfStockCount=critical_count,
        stockoutRiskCount=high_count,
        lowStockCount=medium_count,
        healthyCount=low_count,
        overstockCount=safe_count,
        totalReorderQty=total_reorder_qty,
        items=items,
    )
    set_cached_forecast(user.companyId, "inventory_forecast", result, ttl=120, **cache_params)
    return result


def get_risk_classification(
    db: DbDependency,
    authorization: str | None = None,
    forecast_period: str | None = None,
    q: str | None = None,
) -> list[InventoryForecastItemResponse]:
    summary = get_inventory_forecast(db, authorization, forecast_period, q=q)
    return summary.items


# ---------------------------------------------------------------------------
# Shared per-product forecast computation
# ---------------------------------------------------------------------------

def _compute_product_forecast(
    product: Product,
    transactions: list[SalesTransaction],
    lines_by_product: dict[int, list[SalesTransactionLine]],
    period_days: int,
    category_cache: dict[int, str],
    user,
    db: DbDependency,
    lead_time: int = 4,
) -> dict:
    current_stock = int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0)

    if product.categoryId not in category_cache:
        cat = db.query(Category).filter(Category.id == product.categoryId, Category.companyId == user.companyId).first()
        category_cache[product.categoryId] = cat.name if cat else "Uncategorized"
    category_name = category_cache[product.categoryId]

    product_lines = lines_by_product.get(product.id, [])

    daily_sales_map: dict[str, float] = defaultdict(float)
    for transaction in transactions:
        sale_date = transaction.saleDateTime
        if not sale_date:
            continue
        day_key = sale_date.strftime("%Y-%m-%d")
        matching_qty = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
        daily_sales_map[day_key] += float(matching_qty)

    all_daily_values = list(daily_sales_map.values())
    total_historical_sales = sum(all_daily_values)

    num_days_with_sales = len(daily_sales_map) if daily_sales_map else 1
    first_sale_date = transactions[0].saleDateTime if transactions else None
    last_sale_date = transactions[-1].saleDateTime if transactions else None
    if first_sale_date and last_sale_date:
        span_days = max(1, (last_sale_date - first_sale_date).days + 1)
    else:
        span_days = max(1, num_days_with_sales)

    average_daily_sales = total_historical_sales / span_days if span_days > 0 else 0.0

    monthly_history: dict[str, float] = defaultdict(float)
    for transaction in transactions:
        month = transaction.saleDateTime.strftime("%Y-%m") if transaction.saleDateTime else None
        if not month:
            continue
        matching_qty = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
        monthly_history[month] += float(matching_qty)

    ordered_months = [(m, monthly_history[m]) for m in sorted(monthly_history.keys())[-6:]]
    period_fraction = period_days / 30.0

    if len(ordered_months) >= 2:
        recent_values = [v for _, v in ordered_months[-3:]]
        trend = sum(recent_values[i + 1] - recent_values[i] for i in range(len(recent_values) - 1)) / max(1, len(recent_values) - 1)
        forecasted_demand = max(0.0, ordered_months[-1][1] + trend) * period_fraction
    elif ordered_months:
        forecasted_demand = ordered_months[-1][1] * period_fraction
    else:
        forecasted_demand = 0.0

    daily_demand_rate = forecasted_demand / period_days if period_days > 0 else average_daily_sales
    if daily_demand_rate <= 0 and average_daily_sales > 0:
        daily_demand_rate = average_daily_sales
    elif daily_demand_rate <= 0:
        daily_demand_rate = 0.001

    days_of_stock_remaining = current_stock / daily_demand_rate if daily_demand_rate > 0 else 9999.0

    safety_stock = math.ceil(1.65 * (sum((v - average_daily_sales) ** 2 for v in all_daily_values) / max(1, len(all_daily_values))) ** 0.5) if all_daily_values else 0
    safety_stock = max(0, safety_stock)

    reorder_point = math.ceil(daily_demand_rate * lead_time + safety_stock)

    max_stock_level = product.maxStockLevel if hasattr(product, 'maxStockLevel') and product.maxStockLevel else None

    if current_stock <= reorder_point:
        target_stock = forecasted_demand + safety_stock
        base_reorder_qty = math.ceil(target_stock - current_stock)
        if max_stock_level is not None:
            max_capacity_qty = max(0, max_stock_level - current_stock)
            recommended_reorder_qty = max(0, min(base_reorder_qty, max_capacity_qty))
        else:
            recommended_reorder_qty = max(0, base_reorder_qty)
    else:
        recommended_reorder_qty = 0

    risk_classification = _classify_inventory_risk(current_stock, days_of_stock_remaining, forecasted_demand, reorder_point, lead_time, max_stock_level)
    reorder_required = recommended_reorder_qty > 0

    if risk_classification == "out_of_stock":
        recommendation = "Immediate Reorder Required"
    elif risk_classification == "stockout_risk":
        recommendation = "Reorder Soon"
    elif risk_classification == "low_stock":
        recommendation = "Plan Reorder"
    elif risk_classification == "overstock":
        recommendation = "Reduce Stock Level"
    else:
        recommendation = "Stock Level Adequate"

    return {
        "productId": product.id,
        "productName": product.name,
        "sku": product.sku,
        "categoryId": product.categoryId,
        "categoryName": category_name,
        "brand": product.brand or "",
        "currentStock": current_stock,
        "averageDailySales": round(average_daily_sales, 2),
        "forecastedDemand": round(forecasted_demand, 2),
        "daysOfStockRemaining": round(days_of_stock_remaining, 1),
        "leadTime": lead_time,
        "reorderPoint": reorder_point,
        "safetyStock": safety_stock,
        "maxStockLevel": max_stock_level,
        "recommendedReorderQty": recommended_reorder_qty,
        "stockRisk": risk_classification,
        "riskClassification": risk_classification,
        "reorderRequired": reorder_required,
        "recommendation": recommendation,
        "costPrice": float(product.costPrice or 0),
        "unitPrice": float(product.unitPrice or 0),
        "monthlyHistory": [{"month": m, "sales": round(s, 2)} for m, s in ordered_months],
        "allDailyValues": all_daily_values,
        "averageDailySalesRaw": average_daily_sales,
        "dailySalesMap": dict(daily_sales_map),
    }


def _classify_action_severity(
    current_stock: int,
    safety_stock: int,
    reorder_point: int,
    forecasted_demand: float,
    average_daily_sales: float,
    recommended_reorder_qty: int,
) -> tuple[str, str]:
    if current_stock <= 0:
        return "critical", "Out of stock — immediate reorder required"
    if current_stock < safety_stock:
        return "critical", f"Below safety stock ({current_stock} < {safety_stock})"
    if current_stock <= reorder_point:
        return "critical", f"Reorder required — stock at or below reorder point ({current_stock} <= {reorder_point})"
    if recommended_reorder_qty > 0:
        return "warning", f"Reorder recommended — {recommended_reorder_qty} units suggested"

    demand_diff = forecasted_demand - average_daily_sales
    if average_daily_sales > 0 and demand_diff > average_daily_sales * 0.3:
        return "warning", f"Demand spike detected — forecasted {forecasted_demand:.0f} vs avg {average_daily_sales:.0f}"

    if current_stock > reorder_point * 3 and forecasted_demand > 0 and current_stock > forecasted_demand * 3:
        return "warning", "Overstock detected — stock exceeds 3x forecasted demand"

    return "ok", "Stock level healthy — no action needed"


def _load_company_sales_data(db, company_id: int) -> tuple[list[SalesTransaction], dict[int, list[SalesTransactionLine]]]:
    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == company_id)
        .order_by(SalesTransaction.saleDateTime.asc())
        .all()
    )
    transaction_ids = [tx.id for tx in transactions]
    sales_lines = (
        db.query(SalesTransactionLine)
        .filter(SalesTransactionLine.transactionId.in_(transaction_ids))
        .all()
        if transaction_ids
        else []
    )
    lines_by_product: dict[int, list[SalesTransactionLine]] = defaultdict(list)
    for line in sales_lines:
        lines_by_product[line.productId].append(line)
    return transactions, lines_by_product


# ---------------------------------------------------------------------------
# GET /inventory/recommendations
# ---------------------------------------------------------------------------

def get_inventory_recommendations(
    db: DbDependency,
    authorization: str | None = None,
    forecast_period: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    risk_filter: str | None = None,
    category_filter: str | None = None,
    brand_filter: str | None = None,
    reorder_required: str | None = None,
    q: str | None = None,
    lead_time: int = 4,
) -> InventoryRecommendationSummary:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    cache_params = {
        "forecast_period": forecast_period, "sort_by": sort_by,
        "sort_direction": sort_direction, "risk_filter": risk_filter,
        "category_filter": category_filter, "brand_filter": brand_filter,
        "reorder_required": reorder_required, "q": q,
    }
    cached = get_cached_forecast(user.companyId, "inventory_recommendations", **cache_params)
    if cached is not None:
        return cached

    _, period_days = _resolve_forecast_period(forecast_period)

    products = db.query(Product).filter(Product.companyId == user.companyId).all()
    if not products:
        return InventoryRecommendationSummary(
            totalProducts=0, actionRequiredCount=0, reviewNeededCount=0,
            optimalCount=0, totalReorderQty=0, estimatedReorderCost=0.0, items=[],
        )

    transactions, lines_by_product = _load_company_sales_data(db, user.companyId)
    category_cache: dict[int, str] = {}

    items: list[InventoryRecommendationItem] = []
    for product in products:
        if q:
            wildcard = q.lower().strip()
            if wildcard not in (product.name or "").lower() and wildcard not in (product.sku or "").lower():
                continue

        data = _compute_product_forecast(product, transactions, lines_by_product, period_days, category_cache, user, db, lead_time)
        severity, action_message = _classify_action_severity(
            data["currentStock"], data["safetyStock"], data["reorderPoint"],
            data["forecastedDemand"], data["averageDailySalesRaw"], data["recommendedReorderQty"],
        )

        items.append(InventoryRecommendationItem(
            productId=data["productId"],
            productName=data["productName"],
            sku=data["sku"],
            categoryId=data["categoryId"],
            categoryName=data["categoryName"],
            brand=data["brand"],
            currentStock=data["currentStock"],
            averageDailySales=data["averageDailySales"],
            forecastedDemand=data["forecastedDemand"],
            daysOfStockRemaining=data["daysOfStockRemaining"],
            leadTime=data["leadTime"],
            reorderPoint=data["reorderPoint"],
            safetyStock=data["safetyStock"],
            maxStockLevel=data["maxStockLevel"],
            recommendedReorderQty=data["recommendedReorderQty"],
            stockRisk=data["stockRisk"],
            riskClassification=data["riskClassification"],
            reorderRequired=data["reorderRequired"],
            recommendation=data["recommendation"],
            actionSeverity=severity,
            actionMessage=action_message,
        ))

    risk_order = {"out_of_stock": 0, "stockout_risk": 1, "low_stock": 2, "healthy": 3, "overstock": 4}
    severity_order = {"critical": 0, "warning": 1, "ok": 2}
    normalized_sort = (sort_by or "stock_risk").strip().lower()
    normalized_direction = (sort_direction or "asc").strip().lower()

    def _sort_key(item: InventoryRecommendationItem):
        if normalized_sort == "product_name":
            return item.productName.lower()
        if normalized_sort == "current_stock":
            return item.currentStock
        if normalized_sort == "forecasted_demand":
            return item.forecastedDemand
        if normalized_sort == "days_of_stock_remaining":
            return item.daysOfStockRemaining
        if normalized_sort == "recommended_reorder_qty":
            return item.recommendedReorderQty
        if normalized_sort == "action_severity":
            return severity_order.get(item.actionSeverity, 3)
        if normalized_sort in ("stock_risk", "risk_level"):
            return risk_order.get(item.stockRisk, 5)
        if normalized_sort == "category":
            return (item.categoryName or "").lower()
        if normalized_sort == "brand":
            return (item.brand or "").lower()
        return severity_order.get(item.actionSeverity, 3)

    items.sort(key=_sort_key, reverse=normalized_direction == "desc")

    if risk_filter and risk_filter.strip().lower() != "all":
        risk_value = risk_filter.strip().lower()
        items = [i for i in items if i.stockRisk == risk_value]
    if category_filter and category_filter.strip().lower() != "all":
        cat_value = category_filter.strip().lower()
        items = [i for i in items if (i.categoryName or "").lower() == cat_value]
    if brand_filter and brand_filter.strip().lower() != "all":
        brand_value = brand_filter.strip().lower()
        items = [i for i in items if (i.brand or "").lower() == brand_value]
    if reorder_required and reorder_required.strip().lower() != "all":
        want_reorder = reorder_required.strip().lower() in ("yes", "true", "1")
        if want_reorder:
            items = [i for i in items if i.recommendedReorderQty > 0]
        else:
            items = [i for i in items if i.recommendedReorderQty <= 0]

    action_required = sum(1 for i in items if i.actionSeverity == "critical")
    review_needed = sum(1 for i in items if i.actionSeverity == "warning")
    optimal = sum(1 for i in items if i.actionSeverity == "ok")
    reorder_required_count = sum(1 for i in items if i.reorderRequired)
    stockout_risk_count = sum(1 for i in items if i.riskClassification == "stockout_risk")
    overstock_count = sum(1 for i in items if i.riskClassification == "overstock")
    healthy_count = sum(1 for i in items if i.riskClassification == "healthy")
    total_reorder_qty = sum(i.recommendedReorderQty for i in items)

    estimated_cost = 0.0
    for item in items:
        if item.recommendedReorderQty > 0:
            product_obj = next((p for p in products if p.id == item.productId), None)
            if product_obj:
                estimated_cost += item.recommendedReorderQty * float(product_obj.costPrice or 0)

    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="Inventory Recommendations Viewed", ip_address="Unknown", browser="Unknown",
    )

    result = InventoryRecommendationSummary(
        totalProducts=len(items),
        reorderRequiredCount=reorder_required_count,
        actionRequiredCount=action_required,
        reviewNeededCount=review_needed,
        optimalCount=optimal,
        stockoutRiskCount=stockout_risk_count,
        overstockCount=overstock_count,
        healthyCount=healthy_count,
        totalReorderQty=total_reorder_qty,
        estimatedReorderCost=round(estimated_cost, 2),
        items=items,
    )
    set_cached_forecast(user.companyId, "inventory_recommendations", result, ttl=120, **cache_params)
    return result


# ---------------------------------------------------------------------------
# GET /inventory/recommendations/:productId
# ---------------------------------------------------------------------------

def get_product_recommendation(
    product_id: int,
    db: DbDependency,
    authorization: str | None = None,
    forecast_period: str | None = None,
    lead_time: int = 4,
) -> ProductRecommendationDetail:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    _, period_days = _resolve_forecast_period(forecast_period)
    transactions, lines_by_product = _load_company_sales_data(db, user.companyId)
    category_cache: dict[int, str] = {}

    data = _compute_product_forecast(product, transactions, lines_by_product, period_days, category_cache, user, db, lead_time)
    severity, action_message = _classify_action_severity(
        data["currentStock"], data["safetyStock"], data["reorderPoint"],
        data["forecastedDemand"], data["averageDailySalesRaw"], data["recommendedReorderQty"],
    )

    cost_price = float(product.costPrice or 0)
    unit_price = float(product.unitPrice or 0)
    estimated_reorder_cost = data["recommendedReorderQty"] * cost_price

    product_lines = lines_by_product.get(product.id, [])
    weekly_sales: dict[str, float] = defaultdict(float)
    for transaction in transactions:
        sale_date = transaction.saleDateTime
        if not sale_date:
            continue
        iso_week = sale_date.strftime("%Y-W%U")
        matching_qty = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
        weekly_sales[iso_week] += float(matching_qty)

    weekly_demand = [
        WeeklyDemandPoint(weekStart=week, sales=round(sales, 2))
        for week, sales in sorted(weekly_sales.items())[-12:]
    ]

    monthly_sales = data["monthlyHistory"]
    if len(monthly_sales) >= 2:
        recent = [m["sales"] for m in monthly_sales[-3:]]
        trend_values = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
        avg_trend = sum(trend_values) / len(trend_values) if trend_values else 0.0
        prev_avg = sum(recent[:-1]) / max(1, len(recent) - 1)
        pct_change = (avg_trend / prev_avg * 100) if prev_avg > 0 else 0.0
        if avg_trend > 1:
            direction = "increasing"
        elif avg_trend < -1:
            direction = "decreasing"
        else:
            direction = "stable"
        peak = max(monthly_sales, key=lambda m: m["sales"])
        avg_monthly = sum(m["sales"] for m in monthly_sales) / len(monthly_sales)
        trend_analysis = TrendAnalysis(
            direction=direction,
            percentageChange=round(pct_change, 1),
            averageMonthlySales=round(avg_monthly, 2),
            peakMonth=peak["month"],
            peakSales=peak["sales"],
        )
    else:
        trend_analysis = TrendAnalysis(
            direction="stable",
            percentageChange=0.0,
            averageMonthlySales=round(monthly_sales[0]["sales"], 2) if monthly_sales else 0.0,
            peakMonth=monthly_sales[0]["month"] if monthly_sales else None,
            peakSales=monthly_sales[0]["sales"] if monthly_sales else 0.0,
        )

    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action=f"Product Recommendation Viewed: {product.name}", ip_address="Unknown", browser="Unknown",
    )

    return ProductRecommendationDetail(
        productId=data["productId"],
        productName=data["productName"],
        sku=data["sku"],
        categoryId=data["categoryId"],
        categoryName=data["categoryName"],
        brand=data["brand"],
        currentStock=data["currentStock"],
        averageDailySales=data["averageDailySales"],
        forecastedDemand=data["forecastedDemand"],
        daysOfStockRemaining=data["daysOfStockRemaining"],
        leadTime=data["leadTime"],
        reorderPoint=data["reorderPoint"],
        safetyStock=data["safetyStock"],
        maxStockLevel=data["maxStockLevel"],
        recommendedReorderQty=data["recommendedReorderQty"],
        stockRisk=data["stockRisk"],
        riskClassification=data["riskClassification"],
        reorderRequired=data["reorderRequired"],
        recommendation=data["recommendation"],
        actionSeverity=severity,
        actionMessage=action_message,
        costPrice=cost_price,
        unitPrice=unit_price,
        estimatedReorderCost=round(estimated_reorder_cost, 2),
        weeklyDemand=weekly_demand,
        trendAnalysis=trend_analysis,
        monthlyHistory=monthly_sales,
    )


# ---------------------------------------------------------------------------
# GET /inventory/forecast/series/:productId
# ---------------------------------------------------------------------------

def get_forecast_series(
    product_id: int,
    db: DbDependency,
    authorization: str | None = None,
    forecast_period: str | None = None,
    lead_time: int = 4,
) -> ForecastSeriesResponse:
    from datetime import timedelta

    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    _, period_days = _resolve_forecast_period(forecast_period)
    transactions, lines_by_product = _load_company_sales_data(db, user.companyId)
    category_cache: dict[int, str] = {}

    data = _compute_product_forecast(product, transactions, lines_by_product, period_days, category_cache, user, db, lead_time)
    daily_sales_map = data.get("dailySalesMap", {})
    average_daily_sales = data["averageDailySales"]

    historical_days = 30
    today = datetime.now(timezone.utc).date()
    historical: list[dict] = []
    for i in range(historical_days, 0, -1):
        day = today - timedelta(days=i)
        day_key = day.strftime("%Y-%m-%d")
        demand = daily_sales_map.get(day_key, 0.0)
        historical.append({"date": day_key, "demand": round(demand, 2)})

    forecast_days = period_days
    forecast: list[dict] = []
    for i in range(1, forecast_days + 1):
        day = today + timedelta(days=i)
        day_key = day.strftime("%Y-%m-%d")
        forecast.append({"date": day_key, "demand": round(average_daily_sales, 2)})

    return ForecastSeriesResponse(
        productId=product.id,
        productName=product.name,
        historical=[ForecastSeriesPoint(**p) for p in historical],
        forecast=[ForecastSeriesPoint(**p) for p in forecast],
    )
