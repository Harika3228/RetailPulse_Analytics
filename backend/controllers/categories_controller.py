from datetime import datetime, timezone

from fastapi import HTTPException

from backend.auth_utils import get_company_for_user, get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, create_audit_log
from backend.models import Category, Product
from backend.schemas import CategoryRequest, CategoryResponse


def list_categories(db: DbDependency, q: str | None = None, authorization: str | None = None) -> list[CategoryResponse]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)

    query = db.query(Category).filter(Category.companyId == user.companyId)
    if q:
        query = query.filter(Category.name.ilike(f"%{q}%"))
    categories = query.all()

    result = []
    for c in categories:
        count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == c.id).count()
        result.append(CategoryResponse(id=c.id, name=c.name, description=c.description,
                                       status=c.status or "active", productCount=count))
    create_audit_log(db, company=str(user.companyId), user=user.email, action="List Categories",
                     ip_address="Unknown", browser="Unknown")
    return result


def create_category(payload: CategoryRequest, db: DbDependency, authorization: str | None = None) -> CategoryResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    existing = db.query(Category).filter(Category.companyId == user.companyId, Category.name.ilike(payload.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category name already exists")

    cat = Category(
        companyId=user.companyId,
        name=payload.name.strip(),
        description=payload.description or "",
        status=payload.status or "active",
        updatedAt=datetime.now(timezone.utc),
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    create_audit_log(db, company=company.name, user=user.email, action="Category Created",
                     entity_name=cat.name, ip_address="Unknown", browser="Unknown")
    return CategoryResponse(id=cat.id, name=cat.name, description=cat.description,
                            status=cat.status or "active", productCount=0)


def get_category(category_id: int, db: DbDependency, authorization: str | None = None) -> CategoryResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)

    cat = db.query(Category).filter(Category.id == category_id, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == cat.id).count()
    create_audit_log(db, company=str(user.companyId), user=user.email, action=f"Get Category:{cat.name}",
                     ip_address="Unknown", browser="Unknown")
    return CategoryResponse(id=cat.id, name=cat.name, description=cat.description,
                            status=cat.status or "active", productCount=count)


def update_category(category_id: int, payload: CategoryRequest, db: DbDependency, authorization: str | None = None) -> CategoryResponse:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    cat = db.query(Category).filter(Category.id == category_id, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    existing = db.query(Category).filter(
        Category.companyId == user.companyId,
        Category.name.ilike(payload.name),
        Category.id != category_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category name already exists")

    cat.name = payload.name.strip()
    cat.description = payload.description or ""
    cat.status = payload.status or cat.status
    cat.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cat)

    count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == cat.id).count()
    create_audit_log(db, company=company.name, user=user.email, action="Category Updated",
                     entity_name=cat.name, ip_address="Unknown", browser="Unknown")
    return CategoryResponse(id=cat.id, name=cat.name, description=cat.description,
                            status=cat.status or "active", productCount=count)


def delete_category(category_id: int, db: DbDependency, authorization: str | None = None) -> dict:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    cat = db.query(Category).filter(Category.id == category_id, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    prod_count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == cat.id).count()
    if prod_count > 0:
        raise HTTPException(status_code=400, detail="Category has products; deactivate instead of deleting")

    db.delete(cat)
    db.commit()
    create_audit_log(db, company=company.name, user=user.email, action="Category Deleted",
                     entity_name=cat.name, ip_address="Unknown", browser="Unknown")
    return {"message": "Category deleted"}
