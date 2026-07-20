from fastapi import APIRouter, Header, HTTPException

from backend.controllers.products_controller import (
    create_product,
    delete_product,
    get_product,
    list_products,
    update_product,
    update_product_status,
)
from backend.database import DbDependency
from backend.schemas import ProductRequest, ProductResponse, ProductStatusRequest

router = APIRouter(tags=["products"])


@router.get("/products", response_model=list[ProductResponse])
def list_products_route(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    brand: str | None = None,
    status_filter: str | None = None,
    sortBy: str | None = None,
    sortOrder: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_products(db, q, categoryId, brand, status_filter, sortBy, sortOrder, authorization)


@router.post("/products", response_model=ProductResponse)
def create_product_route(
    payload: ProductRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return create_product(payload, db, authorization)


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product_route(
    product_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_product(product_id, db, authorization)


@router.put("/products/{product_id}", response_model=ProductResponse)
def update_product_route(
    product_id: int,
    payload: ProductRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_product(product_id, payload, db, authorization)


@router.delete("/products/{product_id}")
def delete_product_route(
    product_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return delete_product(product_id, db, authorization)


@router.patch("/products/{product_id}/status", response_model=ProductResponse)
def update_product_status_route(
    product_id: int,
    payload: ProductStatusRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_product_status(product_id, payload, db, authorization)
