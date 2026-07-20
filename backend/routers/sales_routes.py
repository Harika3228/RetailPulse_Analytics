from fastapi import APIRouter, Header

from backend.controllers.sales_controller import (
    create_sales_transaction,
    delete_sales_transaction,
    get_sales_transaction,
    list_sales_transactions,
    list_selectable_products_for_sales,
    sales_history_report,
    update_sales_transaction,
)
from backend.database import DbDependency
from backend.schemas import (
    SalesSelectableProductResponse,
    SalesTransactionRequest,
    SalesTransactionResponse,
)

router = APIRouter(tags=["sales"])


@router.get("/sales/products/selectable", response_model=list[SalesSelectableProductResponse])
def list_selectable_products_for_sales_route(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_selectable_products_for_sales(db, q, categoryId, authorization)


@router.get("/sales", response_model=list[SalesTransactionResponse])
@router.get("/sales/transactions", response_model=list[SalesTransactionResponse])
def list_sales_transactions_route(
    db: DbDependency,
    q: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    categoryId: int | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    sortBy: str | None = None,
    sortOrder: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_sales_transactions(db, q, dateFrom, dateTo, categoryId, salesChannel, paymentMethod, sortBy, sortOrder, authorization)


@router.get("/sales/{transaction_id}", response_model=SalesTransactionResponse)
@router.get("/sales/transactions/{transaction_id}", response_model=SalesTransactionResponse)
def get_sales_transaction_route(
    transaction_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_sales_transaction(transaction_id, db, authorization)


@router.post("/sales", response_model=SalesTransactionResponse)
@router.post("/sales/transactions", response_model=SalesTransactionResponse)
def create_sales_transaction_route(
    payload: SalesTransactionRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return create_sales_transaction(payload, db, authorization)


@router.put("/sales/{transaction_id}", response_model=SalesTransactionResponse)
@router.put("/sales/transactions/{transaction_id}", response_model=SalesTransactionResponse)
def update_sales_transaction_route(
    transaction_id: int,
    payload: SalesTransactionRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return update_sales_transaction(transaction_id, payload, db, authorization)


@router.delete("/sales/{transaction_id}")
@router.delete("/sales/transactions/{transaction_id}")
def delete_sales_transaction_route(
    transaction_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return delete_sales_transaction(transaction_id, db, authorization)


@router.get("/sales/reports/history", response_model=list[SalesTransactionResponse])
def sales_history_report_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return sales_history_report(db, authorization)
