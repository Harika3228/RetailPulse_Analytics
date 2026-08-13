from fastapi import APIRouter, Header

from backend.controllers.analytics_controller import (
    analytics_sales_customers,
    analytics_sales_export,
    analytics_sales_payment_methods,
    analytics_sales_products,
    analytics_sales_summary,
    analytics_sales_trend,
)
from backend.database import DbDependency
from backend.schemas import (
    SalesAnalyticsPaymentMethodResponse,
    SalesAnalyticsSummaryResponse,
    SalesAnalyticsTrendResponse,
    TopCustomerResponse,
    TopProductResponse,
)

router = APIRouter(tags=["analytics"])


@router.get("/analytics/sales/summary", response_model=SalesAnalyticsSummaryResponse)
@router.get("/api/analytics/sales/summary", response_model=SalesAnalyticsSummaryResponse)
def analytics_sales_summary_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
):
    return analytics_sales_summary(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
    )


@router.get("/analytics/sales/trend", response_model=SalesAnalyticsTrendResponse)
@router.get("/api/analytics/sales/trend", response_model=SalesAnalyticsTrendResponse)
def analytics_sales_trend_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
):
    return analytics_sales_trend(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
    )


@router.get("/analytics/sales/products", response_model=list[TopProductResponse])
@router.get("/api/analytics/sales/products", response_model=list[TopProductResponse])
def analytics_sales_products_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 50,
):
    return analytics_sales_products(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
        limit=limit,
    )


@router.get("/analytics/sales/customers", response_model=list[TopCustomerResponse])
@router.get("/api/analytics/sales/customers", response_model=list[TopCustomerResponse])
def analytics_sales_customers_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 20,
):
    return analytics_sales_customers(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
        limit=limit,
    )


@router.get("/analytics/sales/payment-methods", response_model=SalesAnalyticsPaymentMethodResponse)
@router.get("/api/analytics/sales/payment-methods", response_model=SalesAnalyticsPaymentMethodResponse)
def analytics_sales_payment_methods_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
):
    return analytics_sales_payment_methods(
        db,
        authorization,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
    )


@router.get("/analytics/sales/export")
@router.get("/api/analytics/sales/export")
def analytics_sales_export_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
    format: str = "csv",
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
):
    return analytics_sales_export(
        db,
        authorization,
        export_format=format,
        dateFrom=dateFrom,
        dateTo=dateTo,
        product=product,
        category=category,
        brand=brand,
        salesChannel=salesChannel,
        paymentMethod=paymentMethod,
        customer=customer,
    )
