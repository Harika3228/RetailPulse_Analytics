from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from fastapi.responses import PlainTextResponse, Response

from backend.auth_utils import get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_sales_user, create_audit_log, create_notification
from backend.models import Category, DemandForecast, ForecastHistory, ForecastSnapshot, Product, SalesTransaction, SalesTransactionLine
from backend.schemas import (
    ForecastAccuracyResponse,
    ForecastCategoryResponse,
    ForecastProductResponse,
    ForecastSummaryResponse,
)


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def _month_key(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m")


def _normalize_forecast_period(period: str | None) -> str:
    if period is None:
        return "30d"
    normalized = period.strip().lower()
    if normalized in {"7d", "next_7_days", "7-days"}:
        return "7d"
    if normalized in {"30d", "next_30_days", "30-days"}:
        return "30d"
    if normalized in {"90d", "next_90_days", "90-days"}:
        return "90d"
    if normalized == "custom":
        return "custom"
    return normalized


def _resolve_forecast_period(period: str | None, start_date: str | None = None, end_date: str | None = None) -> tuple[str, int]:
    if period in {"7d", "next_7_days", "7-days"}:
        return "Next 7 Days", 7
    if period in {"30d", "next_30_days", "30-days"}:
        return "Next 30 Days", 30
    if period in {"90d", "next_90_days", "90-days"}:
        return "Next 90 Days", 90
    if period == "custom" and start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            days = max(1, (end - start).days)
            return "Custom Date Range", days
        except ValueError:
            pass
    return "Next 30 Days", 30


def _build_forecast_from_history(history: list[tuple[str, float]], period_days: int = 30) -> tuple[list[dict[str, Any]], float, float]:
    if not history:
        return [], 0.0, 0.0

    history_values = [value for _, value in history]
    if len(history_values) < 2:
        forecast_value = float(history_values[-1])
        return [{"month": month, "historical": value, "forecast": value} for month, value in history], round(forecast_value, 2), round(forecast_value, 2)

    recent = history_values[-3:]
    trend = sum(recent[i + 1] - recent[i] for i in range(len(recent) - 1)) / max(1, len(recent) - 1)
    baseline = history_values[-1] + trend
    forecast_value = max(0.0, baseline)
    growth_trend = round(((forecast_value - history_values[-1]) / max(abs(history_values[-1]), 1.0)) * 100, 2) if history_values[-1] else 0.0

    forecast_points = []
    for month, value in history:
        forecast_points.append({"month": month, "historical": value, "forecast": round(forecast_value, 2)})
    return forecast_points, round(forecast_value, 2), growth_trend


def _persist_forecast_snapshot(db: DbDependency, company_id: int, forecast_type: str, period: str, payload: Any) -> None:
    snapshot = (
        db.query(ForecastSnapshot)
        .filter(ForecastSnapshot.companyId == company_id, ForecastSnapshot.forecastType == forecast_type, ForecastSnapshot.period == period)
        .first()
    )
    if snapshot is None:
        snapshot = ForecastSnapshot(companyId=company_id, forecastType=forecast_type, period=period, payload="")
        db.add(snapshot)
    snapshot.generatedAt = datetime.now(timezone.utc)
    snapshot.payload = str(payload)
    db.commit()


def _load_recent_sales_history(db: DbDependency, company_id: int) -> list[tuple[str, float]]:
    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == company_id)
        .order_by(SalesTransaction.saleDateTime.asc())
        .all()
    )
    monthly_sales: dict[str, float] = defaultdict(float)
    for transaction in transactions:
        month = _month_key(transaction.saleDateTime)
        if month:
            monthly_sales[month] += float(transaction.totalAmount or 0)
    return [(month, monthly_sales[month]) for month in sorted(monthly_sales.keys())[-6:]]


def _upsert_demand_forecast_record(
    db: DbDependency,
    company_id: int,
    product_id: int,
    category_id: int | None,
    forecast_period: str,
    predicted_demand: float,
    confidence_score: float,
    historical_sales: float,
    accuracy: float,
) -> DemandForecast:
    period_key = _normalize_forecast_period(forecast_period)
    existing = (
        db.query(DemandForecast)
        .filter(
            DemandForecast.companyId == company_id,
            DemandForecast.productId == product_id,
            DemandForecast.forecastPeriod == period_key,
        )
        .first()
    )
    if existing is None:
        existing = DemandForecast(
            companyId=company_id,
            productId=product_id,
            categoryId=category_id,
            forecastPeriod=period_key,
            predictedDemand=0.0,
            confidenceScore=0.0,
        )
        db.add(existing)
        db.flush()

    existing.categoryId = category_id
    existing.predictedDemand = round(predicted_demand, 2)
    existing.confidenceScore = round(confidence_score, 2)
    existing.generatedAt = datetime.now(timezone.utc)
    db.add(ForecastHistory(
        forecastId=existing.id,
        historicalSales=round(historical_sales, 2),
        prediction=round(predicted_demand, 2),
        accuracy=round(accuracy, 2),
        createdAt=datetime.now(timezone.utc),
    ))
    db.commit()
    db.refresh(existing)
    return existing


def get_forecast_summary(db: DbDependency, authorization: str | None = None, period: str | None = None, start_date: str | None = None, end_date: str | None = None) -> ForecastSummaryResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    history = _load_recent_sales_history(db, user.companyId)
    if not history:
        raise HTTPException(status_code=400, detail="Forecast generation requires historical sales data")

    period_label, period_days = _resolve_forecast_period(period, start_date, end_date)
    forecast_points, next_month_forecast, growth_rate = _build_forecast_from_history(history, period_days)

    avg_monthly_sales = round(sum(item[1] for item in history) / max(1, len(history)), 2) if history else 0.0
    growth_rate = round(((next_month_forecast - avg_monthly_sales) / avg_monthly_sales) * 100, 2) if avg_monthly_sales else growth_rate

    summary = ForecastSummaryResponse(
        totalProducts=len(db.query(Product).filter(Product.companyId == user.companyId).all()),
        forecastedDemand=round(next_month_forecast, 2),
        averageMonthlySales=avg_monthly_sales,
        trendGrowth=growth_rate,
        forecastPeriod=period_label,
        forecastWindowDays=period_days,
        forecastPoints=forecast_points,
    )
    _persist_forecast_snapshot(db, user.companyId, "demand", period or "30d", summary.model_dump())
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Forecast Generated",
        entity_name="Demand Forecast",
        product_name="Demand Forecast",
        category_name="Demand Forecast",
        forecast_period=period_label,
        ip_address="Unknown",
        browser="Unknown",
    )
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Forecast Refreshed",
        entity_name="Demand Forecast",
        product_name="Demand Forecast",
        category_name="Demand Forecast",
        forecast_period=period_label,
        ip_address="Unknown",
        browser="Unknown",
    )
    create_notification(
        db,
        user.companyId,
        None,
        None,
        f"Forecast generated for {period_label.lower()} with projected demand {summary.forecastedDemand:.2f}.",
        "forecast_generated",
    )
    return summary


def get_forecast_products(db: DbDependency, authorization: str | None = None, period: str | None = None, start_date: str | None = None, end_date: str | None = None) -> list[ForecastProductResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    products = (
        db.query(Product)
        .filter(Product.companyId == user.companyId)
        .filter((Product.status.is_(None)) | (Product.status == "active"))
        .all()
    )
    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.saleDateTime.asc())
        .all()
    )

    sales_lines = (
        db.query(SalesTransactionLine)
        .filter(SalesTransactionLine.transactionId.in_([tx.id for tx in transactions]))
        .all()
    )

    lines_by_product: dict[int, list[SalesTransactionLine]] = defaultdict(list)
    for line in sales_lines:
        lines_by_product[line.productId].append(line)

    forecasts: list[ForecastProductResponse] = []
    period_label, _ = _resolve_forecast_period(period, start_date, end_date)
    normalized_period = _normalize_forecast_period(period)
    for product in products:
        product_lines = lines_by_product.get(product.id, [])
        monthly_history: list[tuple[str, float]] = []
        for transaction in transactions:
            month = _month_key(transaction.saleDateTime)
            if not month:
                continue
            matching_quantity = sum(line.quantity or 0 for line in product_lines if line.transactionId == transaction.id)
            monthly_history.append((month, float(matching_quantity)))

        history_by_month: dict[str, float] = defaultdict(float)
        for month, value in monthly_history:
            history_by_month[month] += value

        ordered_history = [(month, history_by_month[month]) for month in sorted(history_by_month.keys())[-6:]]
        if not ordered_history:
            continue
        forecast_points, next_forecast, growth_rate = _build_forecast_from_history(ordered_history)
        current_stock = product.stockQuantity or 0
        confidence_level = round(min(99.0, max(55.0, 70.0 + (len(ordered_history) * 2.5))), 2)
        historical_sales = sum(item[1] for item in ordered_history)
        accuracy_score = round(max(0.0, min(100.0, 100.0 - abs(next_forecast - historical_sales) / max(abs(historical_sales), 1.0) * 100.0)), 2) if historical_sales else 100.0
        _upsert_demand_forecast_record(
            db,
            user.companyId,
            product.id,
            product.categoryId,
            normalized_period,
            next_forecast,
            confidence_level,
            historical_sales,
            accuracy_score,
        )
        if current_stock <= 0:
            create_notification(
                db,
                user.companyId,
                product.id,
                product.name,
                f"{product.name} is predicted to run out of stock.",
                "forecast_out_of_stock",
            )
        elif next_forecast > historical_sales * 1.2 and current_stock < max(1, int(product.initialStockQuantity or 0) // 4 if product.initialStockQuantity else 5) * 2:
            create_notification(
                db,
                user.companyId,
                product.id,
                product.name,
                f"{product.name} forecasted demand exceeds available inventory.",
                "forecast_demand_exceeds_inventory",
            )
        elif next_forecast > historical_sales * 1.1:
            create_notification(
                db,
                user.companyId,
                product.id,
                product.name,
                f"{product.name} shows significant demand growth.",
                "demand_growth_alert",
            )
        create_audit_log(
            db,
            company=str(user.companyId),
            user=user.email,
            action="Inventory Recommendation Generated",
            entity_name=product.name,
            product_name=product.name,
            category_name=(db.query(Category).filter(Category.id == product.categoryId).first().name if product.categoryId else "Uncategorized"),
            forecast_period=period_label,
            ip_address="Unknown",
            browser="Unknown",
        )
        forecasts.append(
            ForecastProductResponse(
                id=product.id,
                name=product.name or "Unknown",
                categoryName=(db.query(Category).filter(Category.id == product.categoryId).first().name if product.categoryId else "Uncategorized"),
                currentStock=current_stock,
                historicalDemand=sum(item[1] for item in ordered_history),
                forecastedDemand=round(next_forecast, 2),
                forecastPeriod=period_label,
                confidenceLevel=confidence_level,
                forecastPoints=forecast_points,
            )
        )

    _persist_forecast_snapshot(db, user.companyId, "products", period or "30d", [forecast.model_dump() for forecast in forecasts])
    if forecasts:
        top_product = max(forecasts, key=lambda item: item.forecastedDemand)
        create_notification(
            db,
            user.companyId,
            top_product.id,
            top_product.name,
            f"{top_product.name} shows significant demand growth in the forecast window.",
            "demand_growth_alert",
        )
    return sorted(forecasts, key=lambda item: (-item.forecastedDemand, item.name))


def get_forecast_categories(db: DbDependency, authorization: str | None = None, period: str | None = None, start_date: str | None = None, end_date: str | None = None) -> list[ForecastCategoryResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    categories = (
        db.query(Category)
        .filter(Category.companyId == user.companyId)
        .filter((Category.status.is_(None)) | (Category.status == "active"))
        .all()
    )
    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.saleDateTime.asc())
        .all()
    )

    sales_lines = (
        db.query(SalesTransactionLine)
        .filter(SalesTransactionLine.transactionId.in_([tx.id for tx in transactions]))
        .all()
    )

    lines_by_category: dict[int, list[SalesTransactionLine]] = defaultdict(list)
    for line in sales_lines:
        if line.categoryIdSnapshot:
            lines_by_category[line.categoryIdSnapshot].append(line)

    forecasts: list[ForecastCategoryResponse] = []
    period_label, _ = _resolve_forecast_period(period, start_date, end_date)
    for category in categories:
        category_lines = lines_by_category.get(category.id, [])
        monthly_history: list[tuple[str, float]] = []
        for transaction in transactions:
            month = _month_key(transaction.saleDateTime)
            if not month:
                continue
            matching_quantity = sum(line.quantity or 0 for line in category_lines if line.transactionId == transaction.id)
            monthly_history.append((month, float(matching_quantity)))

        history_by_month: dict[str, float] = defaultdict(float)
        for month, value in monthly_history:
            history_by_month[month] += value

        ordered_history = [(month, history_by_month[month]) for month in sorted(history_by_month.keys())[-6:]]
        if not ordered_history:
            continue
        forecast_points, next_forecast, growth_rate = _build_forecast_from_history(ordered_history)
        expected_growth = round(max(0.0, growth_rate), 2)
        forecasts.append(
            ForecastCategoryResponse(
                name=category.name or "Unknown",
                totalHistoricalSales=sum(item[1] for item in ordered_history),
                predictedDemand=round(next_forecast, 2),
                expectedGrowthPercentage=expected_growth,
                forecastPoints=forecast_points,
            )
        )

    _persist_forecast_snapshot(db, user.companyId, "categories", period or "30d", [forecast.model_dump() for forecast in forecasts])
    return sorted(forecasts, key=lambda item: (-item.predictedDemand, item.name))


def export_demand_forecast_report(db: DbDependency, authorization: str | None = None) -> Response:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)
    summary = get_forecast_summary(db, authorization, period="30d")
    rows = ["forecastPeriod,forecastedDemand,averageMonthlySales,trendGrowth", f"{summary.forecastPeriod},{summary.forecastedDemand},{summary.averageMonthlySales},{summary.trendGrowth}"]
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Forecast Exported",
        entity_name="Demand Forecast Export",
        product_name="Demand Forecast",
        category_name="Demand Forecast",
        forecast_period="30d",
        ip_address="Unknown",
        browser="Unknown",
    )
    create_notification(db, user.companyId, None, None, "Demand forecast export was generated for the company.", "forecast_exported")
    return PlainTextResponse(content="\n".join(rows), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=forecast-demand-report.csv"})


def export_product_forecast_report(db: DbDependency, authorization: str | None = None) -> Response:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)
    products = get_forecast_products(db, authorization, period="30d")
    payload = "\n".join([f"{item.name},{item.forecastedDemand},{item.currentStock},{item.confidenceLevel}" for item in products])
    pdf_payload = b"%PDF-1.4\n%EOF"
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Forecast Exported",
        entity_name="Product Forecast Export",
        product_name="Product Forecast",
        category_name="Product Forecast",
        forecast_period="30d",
        ip_address="Unknown",
        browser="Unknown",
    )
    return Response(content=pdf_payload, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=forecast-product-report.pdf"})


def export_category_forecast_report(db: DbDependency, authorization: str | None = None) -> Response:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)
    categories = get_forecast_categories(db, authorization, period="30d")
    rows = ["name,predictedDemand,expectedGrowthPercentage", *[f"{item.name},{item.predictedDemand},{item.expectedGrowthPercentage}" for item in categories]]
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="Forecast Exported",
        entity_name="Category Forecast Export",
        product_name="Category Forecast",
        category_name="Category Forecast",
        forecast_period="30d",
        ip_address="Unknown",
        browser="Unknown",
    )
    return PlainTextResponse(content="\n".join(rows), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=forecast-category-report.csv"})


def get_forecast_accuracy(db: DbDependency, authorization: str | None = None) -> ForecastAccuracyResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.saleDateTime.asc())
        .all()
    )

    monthly_sales: dict[str, float] = defaultdict(float)
    for transaction in transactions:
        month = _month_key(transaction.saleDateTime)
        if month:
            monthly_sales[month] += float(transaction.totalAmount or 0)

    ordered_months = sorted(monthly_sales.keys())
    if len(ordered_months) < 2:
        return ForecastAccuracyResponse(accuracy=100.0, totalObservations=0, bias=0.0)

    historical_points = [(month, monthly_sales[month]) for month in ordered_months[-6:]]
    if len(historical_points) < 2:
        return ForecastAccuracyResponse(accuracy=100.0, totalObservations=0, bias=0.0)

    actual = historical_points[-1][1]
    forecast = max(0.0, historical_points[-2][1])
    accuracy = round(100.0 - min(100.0, abs(actual - forecast) / max(actual, 1.0) * 100.0), 2) if actual else 100.0
    bias = round(forecast - actual, 2)
    accuracy_response = ForecastAccuracyResponse(accuracy=accuracy, totalObservations=len(historical_points), bias=bias)
    _persist_forecast_snapshot(db, user.companyId, "accuracy", "30d", accuracy_response.model_dump())
    return accuracy_response
