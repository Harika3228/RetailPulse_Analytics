from fastapi import APIRouter, Header, Query

from backend.controllers.inventory_controller import (
    create_stock_adjustment,
    get_forecast_series,
    get_inventory_forecast,
    get_inventory_recommendations,
    get_product_recommendation,
    get_risk_classification,
    list_inventory,
    list_inventory_movements,
    list_stock_adjustments,
)
from backend.database import DbDependency
from backend.schemas import (
    ForecastSeriesResponse,
    InventoryForecastItemResponse,
    InventoryForecastSummaryResponse,
    InventoryMovementResponse,
    InventoryRecommendationSummary,
    InventoryResponse,
    ProductRecommendationDetail,
    StockAdjustmentRequest,
    StockAdjustmentResponse,
)

router = APIRouter(tags=["inventory"])


@router.get("/inventory/risk-classification", response_model=list[InventoryForecastItemResponse])
def get_risk_classification_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    forecast_period: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    return get_risk_classification(db, authorization, forecast_period, q)


@router.get("/inventory/forecast", response_model=InventoryForecastSummaryResponse)
def get_inventory_forecast_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    forecast_period: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_direction: str | None = Query(default=None),
    risk_filter: str | None = Query(default=None),
    category_filter: str | None = Query(default=None),
    brand_filter: str | None = Query(default=None),
    reorder_required: str | None = Query(default=None),
    q: str | None = Query(default=None),
    lead_time: int = Query(default=4, ge=1, le=30),
):
    return get_inventory_forecast(
        db, authorization, forecast_period, sort_by, sort_direction,
        risk_filter, category_filter, brand_filter, reorder_required, q, lead_time,
    )


@router.get("/inventory/recommendations", response_model=InventoryRecommendationSummary)
def get_inventory_recommendations_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    forecast_period: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_direction: str | None = Query(default=None),
    risk_filter: str | None = Query(default=None),
    category_filter: str | None = Query(default=None),
    brand_filter: str | None = Query(default=None),
    reorder_required: str | None = Query(default=None),
    q: str | None = Query(default=None),
    lead_time: int = Query(default=4, ge=1, le=30),
):
    return get_inventory_recommendations(
        db, authorization, forecast_period, sort_by, sort_direction,
        risk_filter, category_filter, brand_filter, reorder_required, q, lead_time,
    )


@router.get("/inventory/recommendations/{product_id}", response_model=ProductRecommendationDetail)
def get_product_recommendation_route(
    product_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    forecast_period: str | None = Query(default=None),
    lead_time: int = Query(default=4, ge=1, le=30),
):
    return get_product_recommendation(product_id, db, authorization, forecast_period, lead_time)


@router.get("/inventory", response_model=list[InventoryResponse])
def list_inventory_route(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    brand: str | None = None,
    status_filter: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    product: str | None = None,
    forecast_period: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = Query(default=None),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_inventory(db, q, categoryId, brand, status_filter, authorization, sort_by, sort_direction, product, forecast_period, offset, limit, category)


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


@router.get("/inventory/forecast/series/{product_id}", response_model=ForecastSeriesResponse)
def get_forecast_series_route(
    product_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    forecast_period: str | None = Query(default=None),
    lead_time: int = Query(default=4, ge=1, le=30),
):
    return get_forecast_series(product_id, db, authorization, forecast_period, lead_time)
