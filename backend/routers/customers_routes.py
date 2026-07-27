from fastapi import APIRouter, Header

from backend.controllers.customers_controller import (
    create_customer,
    delete_customer,
    export_customers,
    get_customer,
    get_customer_analytics,
    get_customer_purchase_history,
    get_customer_timeline,
    list_customers,
    update_customer,
    update_customer_status,
)
from backend.database import DbDependency
from backend.schemas import (
    CustomerAnalyticsResponse,
    CustomerPurchaseHistoryResponse,
    CustomerRequest,
    CustomerResponse,
    CustomerStatusRequest,
)

router = APIRouter(tags=["customers"])


@router.get("/customers", response_model=list[CustomerResponse])
def list_customers_route(
    db: DbDependency,
    q: str | None = None,
    status_filter: str | None = None,
    customer_type: str | None = None,
    sales_channel: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    registeredFrom: str | None = None,
    registeredTo: str | None = None,
    sortBy: str | None = None,
    sortOrder: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_customers(
        db,
        q,
        status_filter,
        customer_type,
        sales_channel,
        city,
        state,
        country,
        registeredFrom,
        registeredTo,
        sortBy,
        sortOrder,
        authorization,
    )


@router.post("/customers", response_model=CustomerResponse)
def create_customer_route(
    payload: CustomerRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return create_customer(payload, db, authorization)


@router.get("/customers/analytics", response_model=CustomerAnalyticsResponse)
def get_customer_analytics_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_customer_analytics(db, authorization)


@router.get("/customers/export")
def export_customers_route(
    db: DbDependency,
    report: str = "list",
    format: str = "csv",
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_customers(db, authorization, report=report, export_format=format)


@router.get("/customers/export/csv")
def export_customers_csv_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_customers(db, authorization, report="list", export_format="csv")


@router.get("/customers/export/pdf")
def export_customers_pdf_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_customers(db, authorization, report="list", export_format="pdf")


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer_route(
    customer_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_customer(customer_id, db, authorization)


@router.get("/customers/{customer_id}/purchase-history", response_model=CustomerPurchaseHistoryResponse)
def get_customer_purchase_history_route(
    customer_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_customer_purchase_history(customer_id, db, authorization)


@router.get("/customers/{customer_id}/timeline")
def get_customer_timeline_route(
    customer_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_customer_timeline(customer_id, db, authorization)


@router.put("/customers/{customer_id}", response_model=CustomerResponse)
def update_customer_route(
    customer_id: int,
    payload: CustomerRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_customer(customer_id, payload, db, authorization)


@router.delete("/customers/{customer_id}")
def delete_customer_route(
    customer_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return delete_customer(customer_id, db, authorization)


@router.patch("/customers/{customer_id}/status", response_model=CustomerResponse)
def update_customer_status_route(
    customer_id: int,
    payload: CustomerStatusRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_customer_status(customer_id, payload, db, authorization)
