from fastapi import APIRouter, Header, Query

from backend.controllers.forecasting_controller import (
    export_category_forecast_report,
    export_demand_forecast_report,
    export_product_forecast_report,
    get_forecast_accuracy,
    get_forecast_categories,
    get_forecast_products,
    get_forecast_summary,
)
from backend.database import DbDependency
from backend.schemas import (
    ForecastAccuracyResponse,
    ForecastCategoryResponse,
    ForecastProductResponse,
    ForecastSummaryResponse,
)

router = APIRouter(tags=["forecasting"])


@router.get("/forecasting", response_model=ForecastSummaryResponse)
def get_forecast_summary_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    period: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
):
    return get_forecast_summary(db, authorization, period, start_date, end_date)


@router.get("/forecasting/products", response_model=list[ForecastProductResponse])
def get_forecast_products_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    period: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
):
    return get_forecast_products(db, authorization, period, start_date, end_date)


@router.get("/forecasting/categories", response_model=list[ForecastCategoryResponse])
def get_forecast_categories_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    period: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
):
    return get_forecast_categories(db, authorization, period, start_date, end_date)


@router.get("/forecasting/accuracy", response_model=ForecastAccuracyResponse)
def get_forecast_accuracy_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_forecast_accuracy(db, authorization)


@router.get("/forecasting/export/demand")
def export_demand_forecast_report_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_demand_forecast_report(db, authorization)


@router.get("/forecasting/export/products")
def export_product_forecast_report_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_product_forecast_report(db, authorization)


@router.get("/forecasting/export/categories")
def export_category_forecast_report_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_category_forecast_report(db, authorization)
