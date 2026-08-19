from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import asc, desc, func

from backend.auth_utils import get_company_for_user, get_current_user
from backend.cache import invalidate_forecast_cache
from backend.controllers.customers_controller import refresh_customer_metrics_for_company
from backend.database import DbDependency
from backend.helpers import (
    _apply_sales_stock_delta,
    _build_sales_line_payloads,
    _ensure_sales_user,
    _save_sales_transaction,
    _sales_transaction_delta_map,
    _transaction_response,
    create_audit_log,
)
from backend.models import Category, Customer, Product, SalesTransaction, SalesTransactionLine, StockMovement
from backend.schemas import (
    SalesSelectableCustomerResponse,
    SalesSelectableProductResponse,
    SalesTransactionRequest,
    SalesTransactionResponse,
    StockMovementResponse,
)


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def list_selectable_products_for_sales(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    authorization: str | None = None,
) -> list[SalesSelectableProductResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    query = db.query(Product).filter(Product.companyId == user.companyId, Product.status == "active")
    if q:
        wildcard = f"%{q}%"
        query = query.filter(
            Product.name.ilike(wildcard)
            | Product.sku.ilike(wildcard)
            | Product.brand.ilike(wildcard)
            | Product.description.ilike(wildcard)
        )
    if categoryId:
        query = query.filter(Product.categoryId == categoryId)

    products = query.all()
    category_ids = {p.categoryId for p in products if p.categoryId}
    category_names = {
        cat.id: cat.name
        for cat in db.query(Category).filter(
            Category.companyId == user.companyId, Category.id.in_(category_ids)
        ).all()
    }
    create_audit_log(db, company=str(user.companyId), user=user.email,
                     action="List Sales Selectable Products", ip_address="Unknown", browser="Unknown")
    return [
        SalesSelectableProductResponse(
            id=p.id,
            name=p.name,
            sku=p.sku,
            categoryId=p.categoryId,
            categoryName=category_names.get(p.categoryId, ""),
            brand=p.brand or "",
            unitPrice=float(p.unitPrice or 0),
            stockQuantity=int(p.stockQuantity if p.stockQuantity is not None else p.initialStockQuantity or 0),
            status=p.status or "active",
        )
        for p in products
    ]


def list_selectable_customers_for_sales(
    db: DbDependency,
    q: str | None = None,
    authorization: str | None = None,
) -> list[SalesSelectableCustomerResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    query = db.query(Customer).filter(
        Customer.companyId == user.companyId,
        Customer.isDeleted != 1,
    )
    if q:
        wildcard = f"%{q.strip()}%"
        query = query.filter(
            Customer.name.ilike(wildcard)
            | Customer.email.ilike(wildcard)
            | Customer.phone.ilike(wildcard)
        )
    customers = query.order_by(Customer.name.asc()).all()
    create_audit_log(db, company=str(user.companyId), user=user.email,
                     action="List Sales Selectable Customers", ip_address="Unknown", browser="Unknown")
    return [
        SalesSelectableCustomerResponse(
            id=c.id,
            name=c.name or "",
            email=c.email or "",
            phone=c.phone,
        )
        for c in customers
    ]


def list_sales_transactions(
    db: DbDependency,
    q: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    categoryId: int | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    paymentStatus: str | None = None,
    product: str | None = None,
    customer: str | None = None,
    sortBy: str | None = None,
    sortOrder: str | None = None,
    authorization: str | None = None,
) -> list[SalesTransactionResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    query = db.query(SalesTransaction).filter(SalesTransaction.companyId == user.companyId)

    if q:
        wildcard = f"%{q}%"
        query = (
            query.outerjoin(
                SalesTransactionLine,
                SalesTransactionLine.transactionId == SalesTransaction.id,
            )
            .filter(
                SalesTransaction.invoiceNumber.ilike(wildcard)
                | SalesTransaction.customerName.ilike(wildcard)
                | SalesTransaction.salesChannel.ilike(wildcard)
                | SalesTransaction.paymentMethod.ilike(wildcard)
                | SalesTransactionLine.productNameSnapshot.ilike(wildcard)
            )
            .distinct()
        )

    if dateFrom:
        try:
            dt_from = datetime.fromisoformat(dateFrom.replace("Z", "+00:00"))
            if dt_from.tzinfo is None:
                dt_from = dt_from.replace(tzinfo=timezone.utc)
            query = query.filter(SalesTransaction.saleDateTime >= dt_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid dateFrom format (use ISO 8601)")

    if dateTo:
        try:
            dt_to = datetime.fromisoformat(dateTo.replace("Z", "+00:00"))
            if dt_to.tzinfo is None:
                dt_to = dt_to.replace(tzinfo=timezone.utc)
            query = query.filter(SalesTransaction.saleDateTime <= dt_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid dateTo format (use ISO 8601)")

    if categoryId:
        query = (
            query.join(
                SalesTransactionLine,
                SalesTransactionLine.transactionId == SalesTransaction.id,
            )
            .filter(SalesTransactionLine.categoryIdSnapshot == categoryId)
            .distinct()
        )

    if salesChannel:
        query = query.filter(SalesTransaction.salesChannel.ilike(salesChannel))
    if paymentMethod:
        query = query.filter(SalesTransaction.paymentMethod.ilike(paymentMethod))
    if paymentStatus:
        query = query.filter(SalesTransaction.paymentStatus.ilike(paymentStatus))
    if customer:
        query = query.filter(SalesTransaction.customerName.ilike(f"%{customer}%"))
    if product:
        product_wildcard = f"%{product}%"
        matching_transaction_ids = (
            db.query(SalesTransactionLine.transactionId)
            .filter(SalesTransactionLine.productNameSnapshot.ilike(product_wildcard))
            .distinct()
        )
        query = query.filter(SalesTransaction.id.in_(matching_transaction_ids))

    normalized_sort = (sortBy or "date").strip().lower()
    normalized_order = (sortOrder or "desc").strip().lower()
    order_fn = asc if normalized_order == "asc" else desc

    if normalized_sort == "invoice":
        query = query.order_by(order_fn(SalesTransaction.invoiceNumber))
    elif normalized_sort == "total":
        query = query.order_by(order_fn(SalesTransaction.totalAmount))
    elif normalized_sort == "customer":
        customer_col = func.lower(SalesTransaction.customerName)
        if normalized_order == "asc":
            query = query.order_by(customer_col.asc().nullslast(), SalesTransaction.id.asc())
        else:
            query = query.order_by(customer_col.desc().nullslast(), SalesTransaction.id.desc())
    else:
        query = query.order_by(order_fn(SalesTransaction.saleDateTime), desc(SalesTransaction.id))

    transactions = query.all()
    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="List Sales Transactions", ip_address="Unknown", browser="Unknown",
    )
    return [_transaction_response(db, tx) for tx in transactions]


def get_sales_transaction(transaction_id: int, db: DbDependency, authorization: str | None = None) -> SalesTransactionResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    tx = db.query(SalesTransaction).filter(
        SalesTransaction.id == transaction_id, SalesTransaction.companyId == user.companyId
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Sales transaction not found")
    create_audit_log(db, company=str(user.companyId), user=user.email,
                     action=f"View Sales Transaction:{tx.id}", ip_address="Unknown", browser="Unknown")
    return _transaction_response(db, tx)


def create_sales_transaction(payload: SalesTransactionRequest, db: DbDependency, authorization: str | None = None) -> SalesTransactionResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)
    company = get_company_for_user(db, user)

    line_payloads = _build_sales_line_payloads(db, user, payload)

    tx = SalesTransaction(companyId=user.companyId, createdBy=user.id)
    db.add(tx)
    db.flush()

    _apply_sales_stock_delta(
        db,
        user.companyId,
        _sales_transaction_delta_map(line_payloads, -1),
        company_name=company.name,
        actor_email=user.email,
        actor_user_id=user.id,
        movement_type="Sale",
        sale_id=tx.id,
    )

    tx = _save_sales_transaction(db, tx, line_payloads, payload, user)
    db.query(StockMovement).filter(
        StockMovement.saleId == tx.id, StockMovement.reference.is_(None)
    ).update({"reference": tx.invoiceNumber}, synchronize_session=False)
    db.commit()
    refresh_customer_metrics_for_company(db, user.companyId)
    invalidate_forecast_cache(user.companyId)

    create_audit_log(db, company=company.name, user=user.email,
                     action="Sale Created", entity_name=tx.invoiceNumber, invoice_number=tx.invoiceNumber,
                     product_name=line_payloads[0]["product"].name if line_payloads else None,
                     ip_address="Unknown", browser="Unknown")
    return _transaction_response(db, tx)


def update_sales_transaction(transaction_id: int, payload: SalesTransactionRequest, db: DbDependency, authorization: str | None = None) -> SalesTransactionResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)
    company = get_company_for_user(db, user)

    tx = db.query(SalesTransaction).filter(
        SalesTransaction.id == transaction_id, SalesTransaction.companyId == user.companyId
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Sales transaction not found")

    old_lines = db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == tx.id).all()
    old_line_payloads = [{"productId": line.productId, "quantity": line.quantity or 0} for line in old_lines]
    new_line_payloads = _build_sales_line_payloads(db, user, payload)

    _apply_sales_stock_delta(
        db,
        user.companyId,
        _sales_transaction_delta_map(old_line_payloads, +1),
        company_name=company.name,
        actor_email=user.email,
        actor_user_id=user.id,
        invoice_number=tx.invoiceNumber,
        movement_type="Sale Return",
        sale_id=tx.id,
    )
    try:
        _apply_sales_stock_delta(
            db,
            user.companyId,
            _sales_transaction_delta_map(new_line_payloads, -1),
            company_name=company.name,
            actor_email=user.email,
            actor_user_id=user.id,
            invoice_number=tx.invoiceNumber,
            movement_type="Sale",
            sale_id=tx.id,
        )
        tx = _save_sales_transaction(db, tx, new_line_payloads, payload, user)
        refresh_customer_metrics_for_company(db, user.companyId)
    except Exception:
        db.rollback()
        raise

    invalidate_forecast_cache(user.companyId)
    create_audit_log(db, company=company.name, user=user.email,
                     action="Sale Updated", entity_name=tx.invoiceNumber, invoice_number=tx.invoiceNumber,
                     product_name=new_line_payloads[0]["product"].name if new_line_payloads else None,
                     ip_address="Unknown", browser="Unknown")
    return _transaction_response(db, tx)


def delete_sales_transaction(transaction_id: int, db: DbDependency, authorization: str | None = None) -> dict:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)
    company = get_company_for_user(db, user)

    tx = db.query(SalesTransaction).filter(
        SalesTransaction.id == transaction_id, SalesTransaction.companyId == user.companyId
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Sales transaction not found")

    old_lines = db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == tx.id).all()
    _apply_sales_stock_delta(
        db,
        user.companyId,
        _sales_transaction_delta_map([{"productId": line.productId, "quantity": line.quantity or 0} for line in old_lines], +1),
        company_name=company.name,
        actor_email=user.email,
        actor_user_id=user.id,
        invoice_number=tx.invoiceNumber,
        movement_type="Sale Return",
        sale_id=tx.id,
    )

    db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == tx.id).delete()
    db.delete(tx)
    db.commit()
    refresh_customer_metrics_for_company(db, user.companyId)
    invalidate_forecast_cache(user.companyId)

    create_audit_log(db, company=company.name, user=user.email,
                     action="Sale Deleted", entity_name=tx.invoiceNumber, invoice_number=tx.invoiceNumber,
                     product_name=old_lines[0].productNameSnapshot if old_lines else None,
                     ip_address="Unknown", browser="Unknown")
    return {"message": "Sales transaction deleted"}


def sales_history_report(db: DbDependency, authorization: str | None = None) -> list[SalesTransactionResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.id.desc())
        .all()
    )
    create_audit_log(db, company=str(user.companyId), user=user.email,
                     action="View Sales History Report", ip_address="Unknown", browser="Unknown")
    return [_transaction_response(db, tx) for tx in transactions]


def list_sale_stock_movements(
    transaction_id: int,
    db: DbDependency,
    authorization: str | None = None,
) -> list[StockMovementResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    tx = db.query(SalesTransaction).filter(
        SalesTransaction.id == transaction_id, SalesTransaction.companyId == user.companyId
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Sales transaction not found")

    movements = (
        db.query(StockMovement)
        .filter(StockMovement.saleId == tx.id, StockMovement.companyId == user.companyId)
        .order_by(StockMovement.id.asc())
        .all()
    )
    create_audit_log(db, company=str(user.companyId), user=user.email,
                     action=f"View Stock Movements for Sale:{tx.id}", ip_address="Unknown", browser="Unknown")
    return [
        StockMovementResponse(
            id=movement.id,
            productId=movement.productId,
            productName=movement.productName or "",
            sku=movement.sku or "",
            movementType=movement.movementType or "",
            previousQuantity=int(movement.previousQuantity or 0),
            updatedQuantity=int(movement.updatedQuantity or 0),
            quantityChanged=int(movement.quantityChanged or 0),
            reference=movement.reference,
            saleId=movement.saleId,
            actor=movement.actor,
            timestamp=movement.createdAt.isoformat() if movement.createdAt else None,
        )
        for movement in movements
    ]
