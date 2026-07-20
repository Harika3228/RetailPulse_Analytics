from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import asc, desc
from sqlalchemy.exc import IntegrityError

from backend.auth_utils import get_company_for_user, get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, _normalize_sku, _to_product_response, create_audit_log
from backend.models import Category, Product
from backend.schemas import ProductRequest, ProductResponse, ProductStatusRequest


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def list_products(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    brand: str | None = None,
    status_filter: str | None = None,
    sortBy: str | None = None,
    sortOrder: str | None = None,
    authorization: str | None = None,
) -> list[ProductResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    query = db.query(Product).filter(Product.companyId == user.companyId)
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
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if status_filter:
        query = query.filter(Product.status == status_filter.lower())

    normalized_sort = (sortBy or "").strip().lower()
    normalized_order = (sortOrder or "").strip().lower()
    if normalized_sort == "name":
        query = query.order_by(desc(Product.name) if normalized_order == "desc" else asc(Product.name))
    elif normalized_sort == "price":
        query = query.order_by(desc(Product.unitPrice) if normalized_order == "desc" else asc(Product.unitPrice))
    elif normalized_sort in ("recently_added", "recently-added", "recent"):
        query = query.order_by(asc(Product.createdAt) if normalized_order == "asc" else desc(Product.createdAt))

    prods = query.all()
    create_audit_log(db, company=str(user.companyId), user=user.email, action="List Products",
                     ip_address="Unknown", browser="Unknown")
    return [_to_product_response(p) for p in prods]


def create_product(
    payload: ProductRequest,
    db: DbDependency,
    authorization: str | None = None,
) -> ProductResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    cat = db.query(Category).filter(Category.id == payload.categoryId, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category")

    if db.query(Product).filter(
        Product.companyId == user.companyId,
        Product.categoryId == payload.categoryId,
        Product.name.ilike(payload.name.strip()),
    ).first():
        raise HTTPException(status_code=400, detail="Product name already exists in this category")

    normalized_sku = _normalize_sku(payload.sku)
    if db.query(Product).filter(Product.companyId == user.companyId, Product.sku == normalized_sku).first():
        raise HTTPException(status_code=400, detail="SKU already exists")

    p = Product(
        companyId=user.companyId,
        categoryId=payload.categoryId,
        sku=normalized_sku,
        name=payload.name.strip(),
        brand=payload.brand.strip(),
        description=payload.description or "",
        unitPrice=payload.unitPrice,
        costPrice=payload.costPrice,
        stockQuantity=payload.stockQuantity,
        initialStockQuantity=payload.stockQuantity,
        unitOfMeasure=payload.unitOfMeasure.strip(),
        price=str(payload.unitPrice),
        status=(payload.status or "active").lower(),
        updatedAt=datetime.now(timezone.utc),
    )
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="SKU already exists")
    db.refresh(p)
    create_audit_log(db, company=company.name, user=user.email, action="Product Created",
                     entity_name=p.name, ip_address="Unknown", browser="Unknown")
    return _to_product_response(p)


def get_product(product_id: int, db: DbDependency, authorization: str | None = None) -> ProductResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    create_audit_log(db, company=str(user.companyId), user=user.email, action=f"Get Product:{product.name}",
                     ip_address="Unknown", browser="Unknown")
    return _to_product_response(product)


def update_product(
    product_id: int,
    payload: ProductRequest,
    db: DbDependency,
    authorization: str | None = None,
) -> ProductResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    p = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    cat = db.query(Category).filter(Category.id == payload.categoryId, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category")

    normalized_sku = _normalize_sku(payload.sku)
    if db.query(Product).filter(
        Product.companyId == user.companyId, Product.sku == normalized_sku, Product.id != product_id
    ).first():
        raise HTTPException(status_code=400, detail="SKU already exists")

    if db.query(Product).filter(
        Product.companyId == user.companyId,
        Product.categoryId == payload.categoryId,
        Product.name.ilike(payload.name.strip()),
        Product.id != product_id,
    ).first():
        raise HTTPException(status_code=400, detail="Product name already exists in this category")

    p.name = payload.name.strip()
    p.sku = normalized_sku
    p.categoryId = payload.categoryId
    p.brand = payload.brand.strip()
    p.description = payload.description or ""
    p.unitPrice = payload.unitPrice
    p.costPrice = payload.costPrice
    p.stockQuantity = payload.stockQuantity
    p.initialStockQuantity = payload.stockQuantity
    p.unitOfMeasure = payload.unitOfMeasure.strip()
    p.price = str(payload.unitPrice)
    p.status = (payload.status or p.status or "active").lower()
    p.updatedAt = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="SKU already exists")
    db.refresh(p)
    create_audit_log(db, company=company.name, user=user.email, action="Product Updated",
                     entity_name=p.name, ip_address="Unknown", browser="Unknown")
    return _to_product_response(p)


def delete_product(product_id: int, db: DbDependency, authorization: str | None = None) -> dict:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    p = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    product_name = p.name
    db.delete(p)
    db.commit()
    create_audit_log(db, company=company.name, user=user.email, action="Product Deleted",
                     entity_name=product_name, ip_address="Unknown", browser="Unknown")
    return {"message": "Product deleted"}


def update_product_status(
    product_id: int,
    payload: ProductStatusRequest,
    db: DbDependency,
    authorization: str | None = None,
) -> ProductResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    normalized = payload.status.lower().strip()
    if normalized not in ("active", "inactive"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.status = normalized
    product.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(product)

    action = "Product Activated" if normalized == "active" else "Product Deactivated"
    create_audit_log(db, company=company.name, user=user.email, action=action,
                     entity_name=product.name, ip_address="Unknown", browser="Unknown")
    return _to_product_response(product)
