from fastapi import APIRouter, Header

from backend.controllers.inventory_controller import (
    create_stock_adjustment,
    list_inventory,
    list_inventory_movements,
    list_stock_adjustments,
)
from backend.database import DbDependency
from backend.schemas import InventoryMovementResponse, InventoryResponse, StockAdjustmentRequest, StockAdjustmentResponse

router = APIRouter(tags=["inventory"])


@router.get("/inventory", response_model=list[InventoryResponse])
def list_inventory_route(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    brand: str | None = None,
    status_filter: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_inventory(db, q, categoryId, brand, status_filter, authorization, sort_by, sort_direction)


@router.get("/inventory/{product_id}/movements", response_model=list[InventoryMovementResponse])
def list_inventory_movements_route(
    product_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_inventory_movements(product_id, db, authorization)


@router.post("/inventory/{product_id}/adjustments", response_model=StockAdjustmentResponse)
def create_stock_adjustment_route(
    product_id: int,
    payload: StockAdjustmentRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return create_stock_adjustment(product_id, payload, db, authorization)


@router.get("/inventory/{product_id}/adjustments", response_model=list[StockAdjustmentResponse])
def list_stock_adjustments_route(
    product_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_stock_adjustments(product_id, db, authorization)
