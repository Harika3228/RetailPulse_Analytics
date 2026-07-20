from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import asc, desc

from backend.auth_utils import get_company_for_user, get_current_user
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
from backend.models import Category, Product, SalesTransaction, SalesTransactionLine
from backend.schemas import (
    SalesSelectableProductResponse,
    SalesTransactionRequest,
    SalesTransactionResponse,
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


def list_sales_transactions(
    db: DbDependency,
    q: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    categoryId: int | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
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

    normalized_sort = (sortBy or "date").strip().lower()
    normalized_order = (sortOrder or "desc").strip().lower()
    order_fn = asc if normalized_order == "asc" else desc

    if normalized_sort == "invoice":
        query = query.order_by(order_fn(SalesTransaction.invoiceNumber))
    elif normalized_sort == "total":
        query = query.order_by(order_fn(SalesTransaction.totalAmount))
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
    _apply_sales_stock_delta(
        db,
        user.companyId,
        _sales_transaction_delta_map(line_payloads, -1),
        company_name=company.name,
        actor_email=user.email,
        invoice_number=None,
    )

    tx = SalesTransaction(companyId=user.companyId, createdBy=user.id)
    db.add(tx)
    tx = _save_sales_transaction(db, tx, line_payloads, payload, user)

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
        invoice_number=tx.invoiceNumber,
    )
    try:
        _apply_sales_stock_delta(
            db,
            user.companyId,
            _sales_transaction_delta_map(new_line_payloads, -1),
            company_name=company.name,
            actor_email=user.email,
            invoice_number=tx.invoiceNumber,
        )
        tx = _save_sales_transaction(db, tx, new_line_payloads, payload, user)
    except Exception:
        db.rollback()
        raise

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
        invoice_number=tx.invoiceNumber,
    )

    db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == tx.id).delete()
    db.delete(tx)
    db.commit()

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
