from fastapi import APIRouter, Header, HTTPException

from backend.controllers.categories_controller import (
    create_category,
    delete_category,
    get_category,
    list_categories,
    update_category,
)
from backend.database import DbDependency
from backend.schemas import CategoryRequest, CategoryResponse

router = APIRouter(tags=["categories"])


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories_route(
    db: DbDependency,
    q: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_categories(db, q, authorization)


@router.post("/categories", response_model=CategoryResponse)
def create_category_route(
    payload: CategoryRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return create_category(payload, db, authorization)


@router.get("/categories/{category_id}", response_model=CategoryResponse)
def get_category_route(
    category_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_category(category_id, db, authorization)


@router.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category_route(
    category_id: int,
    payload: CategoryRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_category(category_id, payload, db, authorization)


@router.delete("/categories/{category_id}")
def delete_category_route(
    category_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return delete_category(category_id, db, authorization)
