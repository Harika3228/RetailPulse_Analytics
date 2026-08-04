import csv
import io
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import asc, desc

from typing import Any

from backend.auth_utils import get_company_for_user, get_current_user
from backend.database import DbDependency
from backend.helpers import _ensure_admin, _ensure_sales_user, create_audit_log, create_notification
from backend.models import Customer, SalesTransaction, SalesTransactionLine
from backend.schemas import (
    CustomerAnalyticsResponse,
    CustomerPurchaseHistoryResponse,
    CustomerRequest,
    CustomerResponse,
    CustomerStatusRequest,
)


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def _normalize_customer_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_email(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _normalize_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _generate_customer_id(db: DbDependency, company_id: int) -> str:
    prefix = f"CUST-{company_id}-"
    existing_ids = {
        row[0]
        for row in db.query(Customer.customerId)
        .filter(Customer.companyId == company_id)
        .filter(Customer.customerId.isnot(None))
        .all()
    }
    counter = 1
    while True:
        candidate = f"{prefix}{counter:05d}"
        if candidate not in existing_ids:
            return candidate
        counter += 1


def _customer_reference(customer: Customer) -> str:
    return customer.customerId or f"CUST-{customer.companyId or 0}-{customer.id:05d}"


def _notify_customer_lifecycle_event(db: DbDependency, company_id: int, customer: Customer, event_type: str, message: str) -> None:
    create_notification(db, company_id=company_id, product_id=None, product_name=customer.name or "Customer", message=message, notification_type=event_type)


def _should_notify_inactive_customer(customer: Customer) -> bool:
    threshold_days = int(os.getenv("CUSTOMER_INACTIVE_NOTIFICATION_DAYS", "0"))
    if threshold_days <= 0:
        return True
    if not customer.updatedAt:
        return False
    delta = datetime.now(timezone.utc) - customer.updatedAt
    return delta.days >= threshold_days


def refresh_customer_metrics_for_company(db: DbDependency, company_id: int) -> None:
    customers = db.query(Customer).filter(Customer.companyId == company_id).all()
    transactions = db.query(SalesTransaction).filter(SalesTransaction.companyId == company_id).all()

    for customer in customers:
        customer_transactions = [
            transaction
            for transaction in transactions
            if _normalize_customer_name(transaction.customerName) == _normalize_customer_name(customer.name)
        ]
        total_orders = len(customer_transactions)
        total_revenue = sum(float(transaction.totalAmount or 0) for transaction in customer_transactions)
        total_quantity = sum(
            int(line.quantity or 0)
            for transaction in customer_transactions
            for line in db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == transaction.id).all()
        )
        avg_order_value = (total_revenue / total_orders) if total_orders else 0
        purchase_dates = [transaction.saleDateTime for transaction in customer_transactions if transaction.saleDateTime]
        first_purchase_date = min(purchase_dates) if purchase_dates else None
        last_purchase_date = max(purchase_dates) if purchase_dates else None

        product_counts: dict[str, int] = {}
        for transaction in customer_transactions:
            for line in db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == transaction.id).all():
                product_name = line.productNameSnapshot or "Unknown"
                product_counts[product_name] = product_counts.get(product_name, 0) + int(line.quantity or 0)

        customer.totalSpend = total_revenue
        customer.purchaseCount = total_orders
        customer.firstPurchaseDate = first_purchase_date
        customer.lastPurchaseDate = last_purchase_date
        new_segment = _classify_customer_segment(total_orders, total_revenue, avg_order_value)
        previous_segment = customer.segment or "new_customer"
        customer.segment = new_segment
        customer.updatedAt = datetime.now(timezone.utc)

        if total_orders > 0 and previous_segment != new_segment and new_segment == "vip_customer":
            _notify_customer_lifecycle_event(
                db,
                company_id,
                customer,
                "customer_vip",
                f"{customer.name or 'Customer'} reached VIP status.",
            )
        if total_orders == 1 and previous_segment != new_segment and customer.firstPurchaseDate:
            _notify_customer_lifecycle_event(
                db,
                company_id,
                customer,
                "customer_first_purchase",
                f"{customer.name or 'Customer'} completed their first purchase.",
            )

    db.commit()


def _classify_customer_segment(order_count: int, total_revenue: float, average_order_value: float) -> str:
    if order_count == 0:
        return "new_customer"
    if order_count >= 5 or total_revenue >= 5000 or average_order_value >= 1000:
        return "vip_customer"
    if order_count >= 3 or total_revenue >= 2500:
        return "loyal_customer"
    if order_count >= 1:
        return "regular_customer"
    return "new_customer"


def _get_customer_profile_context(db: DbDependency, company_id: int, customer: Customer) -> dict[str, object]:
    transactions = [
        transaction
        for transaction in db.query(SalesTransaction).filter(SalesTransaction.companyId == company_id).all()
        if _normalize_customer_name(transaction.customerName) == _normalize_customer_name(customer.name)
    ]
    transactions.sort(key=lambda item: item.saleDateTime or item.createdAt or datetime.now(timezone.utc), reverse=True)

    total_orders = len(transactions)
    total_revenue = sum(float(transaction.totalAmount or 0) for transaction in transactions)
    average_order_value = (total_revenue / total_orders) if total_orders else 0
    last_purchase_date = None
    if transactions:
        last_purchase_date = max(
            (transaction.saleDateTime or transaction.createdAt for transaction in transactions if (transaction.saleDateTime or transaction.createdAt)),
            default=None,
        )

    category_totals: dict[str, int] = {}
    product_totals: dict[str, int] = {}
    for transaction in transactions:
        lines = db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == transaction.id).all()
        for line in lines:
            category_name = line.categoryNameSnapshot or "Unknown"
            category_totals[category_name] = category_totals.get(category_name, 0) + int(line.quantity or 0)
            product_name = line.productNameSnapshot or "Unknown"
            product_totals[product_name] = product_totals.get(product_name, 0) + int(line.quantity or 0)

    favorite_category = max(category_totals.items(), key=lambda item: (item[1], item[0]))[0] if category_totals else None
    favorite_product = max(product_totals.items(), key=lambda item: (item[1], item[0]))[0] if product_totals else None

    if transactions and customer.firstPurchaseDate and customer.lastPurchaseDate:
        days_span = max((customer.lastPurchaseDate - customer.firstPurchaseDate).days, 1)
        monthly_frequency = (total_orders / (days_span / 30)) if days_span else total_orders
        purchase_frequency = f"{monthly_frequency:.1f} orders/month"
    else:
        purchase_frequency = f"{total_orders} orders" if total_orders else "No purchases"

    recent_orders = [
        {
            "id": transaction.id,
            "invoiceNumber": transaction.invoiceNumber,
            "date": (transaction.saleDateTime or transaction.createdAt).isoformat() if (transaction.saleDateTime or transaction.createdAt) else None,
            "totalAmount": float(transaction.totalAmount or 0),
            "paymentMethod": transaction.paymentMethod,
        }
        for transaction in transactions[:5]
    ]

    recent_purchases = []
    for transaction in transactions[:5]:
        lines = db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == transaction.id).all()
        for line in lines[:3]:
            recent_purchases.append(
                {
                    "product": line.productNameSnapshot or "Unknown",
                    "quantity": int(line.quantity or 0),
                    "amount": float(line.lineTotal or 0),
                    "date": (transaction.saleDateTime or transaction.createdAt).isoformat() if (transaction.saleDateTime or transaction.createdAt) else None,
                }
            )

    recent_payments = [
        {
            "date": (transaction.saleDateTime or transaction.createdAt).isoformat() if (transaction.saleDateTime or transaction.createdAt) else None,
            "invoiceNumber": transaction.invoiceNumber,
            "amount": float(transaction.totalAmount or 0),
            "paymentMethod": transaction.paymentMethod,
        }
        for transaction in transactions[:5]
    ]

    return {
        "lifetimeRevenue": total_revenue,
        "totalOrders": total_orders,
        "averageOrderValue": average_order_value,
        "lastPurchase": last_purchase_date.isoformat() if last_purchase_date else None,
        "favoriteCategory": favorite_category,
        "favoriteProduct": favorite_product,
        "purchaseFrequency": purchase_frequency,
        "recentOrders": recent_orders,
        "recentPurchases": recent_purchases,
        "recentPayments": recent_payments,
    }


def _build_customer_timeline(db: DbDependency | None, company_id: int, customer: Customer) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    if customer.createdAt:
        events.append({"title": "Customer registered", "date": customer.createdAt.isoformat(), "type": "registration"})
    if customer.updatedAt and customer.createdAt and customer.updatedAt > customer.createdAt:
        events.append({"title": "Profile updated", "date": customer.updatedAt.isoformat(), "type": "profile_update"})
    if customer.status and customer.status.lower() == "inactive":
        events.append({"title": "Customer deactivated", "date": (customer.updatedAt or customer.createdAt).isoformat() if (customer.updatedAt or customer.createdAt) else None, "type": "deactivation"})
    if customer.purchaseCount:
        if customer.firstPurchaseDate:
            events.append({"title": "First purchase", "date": customer.firstPurchaseDate.isoformat(), "type": "first_purchase"})
        if customer.lastPurchaseDate:
            events.append({"title": "Latest purchase", "date": customer.lastPurchaseDate.isoformat(), "type": "latest_purchase"})
    if customer.totalSpend and float(customer.totalSpend or 0) >= 2000:
        events.append({"title": "High-value customer milestone", "date": customer.lastPurchaseDate.isoformat() if customer.lastPurchaseDate else None, "type": "high_value"})
    return sorted(events, key=lambda item: str(item.get("date") or ""), reverse=True)


def _to_customer_response(customer: Customer, db: DbDependency | None = None) -> CustomerResponse:
    profile_context = _get_customer_profile_context(db, customer.companyId, customer) if db is not None else {
        "lifetimeRevenue": float(customer.totalSpend or 0),
        "totalOrders": int(customer.purchaseCount or 0),
        "averageOrderValue": (float(customer.totalSpend or 0) / int(customer.purchaseCount or 0)) if (customer.purchaseCount or 0) else 0,
        "lastPurchase": customer.lastPurchaseDate.isoformat() if customer.lastPurchaseDate else None,
        "favoriteCategory": None,
        "favoriteProduct": None,
        "purchaseFrequency": f"{int(customer.purchaseCount or 0)} orders" if (customer.purchaseCount or 0) else "No purchases",
        "recentOrders": [],
        "recentPurchases": [],
        "recentPayments": [],
    }
    timeline = _build_customer_timeline(db, customer.companyId, customer)
    return CustomerResponse(
        id=customer.id,
        customerId=_customer_reference(customer),
        name=customer.name or "",
        email=customer.email or "",
        phone=customer.phone,
        dateOfBirth=customer.dateOfBirth,
        gender=customer.gender,
        address=customer.address,
        city=customer.city,
        state=customer.state,
        country=customer.country,
        postalCode=customer.postalCode,
        customerType=customer.customerType,
        preferredSalesChannel=customer.preferredSalesChannel,
        status=customer.status or "active",
        segment=customer.segment or "new_customer",
        totalSpend=float(customer.totalSpend or 0),
        purchaseCount=int(customer.purchaseCount or 0),
        lifetimeRevenue=float(profile_context["lifetimeRevenue"] or 0),
        totalOrders=int(profile_context["totalOrders"] or 0),
        averageOrderValue=float(profile_context["averageOrderValue"] or 0),
        lastPurchase=profile_context["lastPurchase"],
        favoriteCategory=profile_context["favoriteCategory"],
        favoriteProduct=profile_context["favoriteProduct"],
        purchaseFrequency=profile_context["purchaseFrequency"],
        recentOrders=profile_context["recentOrders"],
        recentPurchases=profile_context["recentPurchases"],
        recentPayments=profile_context["recentPayments"],
        timeline=timeline,
        lastPurchaseDate=customer.lastPurchaseDate.isoformat() if customer.lastPurchaseDate else None,
        createdAt=customer.createdAt.isoformat() if customer.createdAt else None,
        updatedAt=customer.updatedAt.isoformat() if customer.updatedAt else None,
    )


def list_customers(
    db: DbDependency,
    q: str | None = None,
    status_filter: str | None = None,
    segment: str | None = None,
    customer_type: str | None = None,
    sales_channel: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    registeredFrom: str | None = None,
    registeredTo: str | None = None,
    sortBy: str | None = None,
    sortOrder: str | None = None,
    authorization: str | None = None,
) -> list[CustomerResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    query = db.query(Customer).filter(Customer.companyId == user.companyId, Customer.isDeleted != 1)
    if q:
        wildcard = f"%{q.strip()}%"
        query = query.filter(
            Customer.name.ilike(wildcard)
            | Customer.email.ilike(wildcard)
            | Customer.phone.ilike(wildcard)
            | Customer.city.ilike(wildcard)
        )
        if q.strip().isdigit():
            query = query.filter(Customer.id == int(q.strip()))
    if status_filter:
        query = query.filter(Customer.status == status_filter.lower())
    if segment:
        query = query.filter(Customer.segment == segment.lower())
    if customer_type:
        query = query.filter(Customer.customerType == customer_type.lower())
    if sales_channel:
        query = query.filter(Customer.preferredSalesChannel == sales_channel.lower())
    if city:
        query = query.filter(Customer.city.ilike(f"%{city.strip()}%"))
    if state:
        query = query.filter(Customer.state.ilike(f"%{state.strip()}%"))
    if country:
        query = query.filter(Customer.country.ilike(f"%{country.strip()}%"))
    if registeredFrom:
        try:
            start_date = datetime.strptime(registeredFrom, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(Customer.createdAt >= start_date)
        except ValueError:
            pass
    if registeredTo:
        try:
            end_date = datetime.strptime(registeredTo, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(Customer.createdAt <= end_date + timedelta(days=1))
        except ValueError:
            pass

    normalized_sort = (sortBy or "").strip().lower()
    normalized_order = (sortOrder or "").strip().lower()
    if normalized_sort in {"name", "customer"}:
        query = query.order_by(desc(Customer.name) if normalized_order == "desc" else asc(Customer.name))
    elif normalized_sort in {"spend", "totalspend"}:
        query = query.order_by(desc(Customer.totalSpend) if normalized_order == "desc" else asc(Customer.totalSpend))
    elif normalized_sort in {"totalorders", "orders", "purchasecount"}:
        query = query.order_by(desc(Customer.purchaseCount) if normalized_order == "desc" else asc(Customer.purchaseCount))
    elif normalized_sort in {"lastpurchase", "last-purchase"}:
        query = query.order_by(desc(Customer.lastPurchaseDate) if normalized_order == "desc" else asc(Customer.lastPurchaseDate))
    else:
        query = query.order_by(desc(Customer.createdAt) if normalized_order == "desc" else asc(Customer.createdAt))

    customers = query.all()
    create_audit_log(db, company=str(user.companyId), user=user.email, action="List Customers", ip_address="Unknown", browser="Unknown")
    return [_to_customer_response(item, db) for item in customers]


def _log_customer_audit(db: DbDependency, company_name: str, user_email: str, action: str, customer_name: str | None = None) -> None:
    create_audit_log(
        db,
        company=company_name,
        user=user_email,
        action=action,
        entity_name=customer_name,
        ip_address="Unknown",
        browser="Unknown",
    )


def create_customer(payload: CustomerRequest, db: DbDependency, authorization: str | None = None) -> CustomerResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="First Name is required.")
    if not payload.email or not payload.email.strip():
        raise HTTPException(status_code=400, detail="Email is required.")
    if not payload.phone or not payload.phone.strip():
        raise HTTPException(status_code=400, detail="Phone number is required.")

    normalized_email = _normalize_email(payload.email)
    normalized_phone = _normalize_phone(payload.phone)
    existing_customers = db.query(Customer).filter(Customer.companyId == user.companyId, Customer.isDeleted != 1).all()
    if any(_normalize_email(item.email) == normalized_email for item in existing_customers if item.email):
        raise HTTPException(status_code=409, detail="Email already exists.")
    if normalized_phone and any(_normalize_phone(item.phone) == normalized_phone for item in existing_customers if item.phone):
        raise HTTPException(status_code=409, detail="Phone number already exists.")

    customer = Customer(
        companyId=user.companyId,
        customerId=_generate_customer_id(db, user.companyId),
        name=payload.name.strip() if payload.name else "Unknown Customer",
        email=normalized_email,
        phone=payload.phone.strip() if payload.phone else None,
        dateOfBirth=payload.dateOfBirth,
        gender=payload.gender.strip() if payload.gender else None,
        address=payload.address.strip() if payload.address else None,
        city=payload.city.strip() if payload.city else None,
        state=payload.state.strip() if payload.state else None,
        country=payload.country.strip() if payload.country else None,
        postalCode=payload.postalCode.strip() if payload.postalCode else None,
        customerType=(payload.customerType or "retail").strip().lower(),
        preferredSalesChannel=(payload.preferredSalesChannel or "offline").strip().lower(),
        status=(payload.status or "active").strip().lower(),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    refresh_customer_metrics_for_company(db, user.companyId)
    _notify_customer_lifecycle_event(
        db,
        user.companyId,
        customer,
        "customer_registered",
        f"{customer.name or 'Customer'} was registered as a new customer.",
    )
    _log_customer_audit(db, company.name, user.email, "Customer Created", customer.name)
    return _to_customer_response(customer, db)


def get_customer(customer_id: int, db: DbDependency, authorization: str | None = None) -> CustomerResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.companyId == user.companyId, Customer.isDeleted != 1).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _to_customer_response(customer, db)


def update_customer(customer_id: int, payload: CustomerRequest, db: DbDependency, authorization: str | None = None) -> CustomerResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.companyId == user.companyId, Customer.isDeleted != 1).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="First Name is required.")
    if not payload.email or not payload.email.strip():
        raise HTTPException(status_code=400, detail="Email is required.")
    if not payload.phone or not payload.phone.strip():
        raise HTTPException(status_code=400, detail="Phone number is required.")

    normalized_email = _normalize_email(payload.email)
    normalized_phone = _normalize_phone(payload.phone)
    existing_customers = db.query(Customer).filter(Customer.companyId == user.companyId, Customer.isDeleted != 1).all()
    if any(item.id != customer_id and _normalize_email(item.email) == normalized_email for item in existing_customers if item.email):
        raise HTTPException(status_code=409, detail="Email already exists.")
    if normalized_phone and any(item.id != customer_id and _normalize_phone(item.phone) == normalized_phone for item in existing_customers if item.phone):
        raise HTTPException(status_code=409, detail="Phone number already exists.")

    customer.name = payload.name.strip() if payload.name else (customer.name or "Unknown Customer")
    customer.email = normalized_email
    customer.phone = payload.phone.strip() if payload.phone else None
    customer.dateOfBirth = payload.dateOfBirth
    customer.gender = payload.gender.strip() if payload.gender else None
    customer.address = payload.address.strip() if payload.address else None
    customer.city = payload.city.strip() if payload.city else None
    customer.state = payload.state.strip() if payload.state else None
    customer.country = payload.country.strip() if payload.country else None
    customer.postalCode = payload.postalCode.strip() if payload.postalCode else None
    customer.customerType = (payload.customerType or customer.customerType or "retail").strip().lower()
    customer.preferredSalesChannel = (payload.preferredSalesChannel or customer.preferredSalesChannel or "offline").strip().lower()
    customer.status = (payload.status or customer.status or "active").strip().lower()
    customer.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(customer)
    _log_customer_audit(db, company.name, user.email, "Customer Updated", customer.name)
    return _to_customer_response(customer, db)


def update_customer_status(customer_id: int, payload: CustomerStatusRequest, db: DbDependency, authorization: str | None = None) -> CustomerResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    normalized = payload.status.strip().lower()
    if normalized not in {"active", "inactive"}:
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")

    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.companyId == user.companyId, Customer.isDeleted != 1).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    previous_status = (customer.status or "active").strip().lower()
    customer.status = normalized
    customer.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(customer)
    if normalized == "inactive" and _should_notify_inactive_customer(customer):
        _notify_customer_lifecycle_event(
            db,
            user.companyId,
            customer,
            "customer_inactive",
            f"{customer.name or 'Customer'} became inactive.",
        )
    action = "Customer Activated" if normalized == "active" else "Customer Deactivated"
    if previous_status != normalized:
        _log_customer_audit(db, company.name, user.email, "Customer Status Changed", customer.name)
    _log_customer_audit(db, company.name, user.email, action, customer.name)
    return _to_customer_response(customer, db)


def get_customer_analytics(db: DbDependency, authorization: str | None = None) -> CustomerAnalyticsResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    customers = db.query(Customer).filter(Customer.companyId == user.companyId, Customer.isDeleted != 1).all()
    total_customers = len(customers)
    active_customers = sum(1 for item in customers if (item.status or "active").lower() == "active")
    inactive_customers = total_customers - active_customers

    customer_type_breakdown = {}
    preferred_sales_channel_breakdown = {}
    for customer in customers:
        customer_type = (customer.customerType or "retail").strip().lower() or "retail"
        customer_type_breakdown[customer_type] = customer_type_breakdown.get(customer_type, 0) + 1
        channel = (customer.preferredSalesChannel or "offline").strip().lower() or "offline"
        preferred_sales_channel_breakdown[channel] = preferred_sales_channel_breakdown.get(channel, 0) + 1

    average_spend = sum(float(customer.totalSpend or 0) for customer in customers) / total_customers if total_customers else 0
    customers_with_purchases = sum(1 for customer in customers if (customer.purchaseCount or 0) > 0)
    recent_customers = [
        {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "status": customer.status or "active",
            "purchaseCount": customer.purchaseCount or 0,
            "totalSpend": float(customer.totalSpend or 0),
        }
        for customer in sorted(customers, key=lambda item: item.createdAt or datetime.now(timezone.utc), reverse=True)[:5]
    ]

    now = datetime.now(timezone.utc)
    new_customers_this_month = sum(
        1 for customer in customers if customer.createdAt and customer.createdAt.year == now.year and customer.createdAt.month == now.month
    )
    returning_customers = sum(1 for customer in customers if (customer.purchaseCount or 0) > 1)
    total_revenue_generated = sum(float(customer.totalSpend or 0) for customer in customers)
    average_purchase_frequency = (sum(customer.purchaseCount or 0 for customer in customers) / total_customers) if total_customers else 0

    customer_growth = []
    for month_index in range(6):
        month_date = now.replace(day=1) - timedelta(days=30 * month_index)
        month_label = month_date.strftime("%b %Y")
        month_count = sum(1 for customer in customers if customer.createdAt and customer.createdAt.year == month_date.year and customer.createdAt.month == month_date.month)
        customer_growth.append({"month": month_label, "customers": month_count})
    customer_growth.reverse()

    revenue_by_type = [
        {"name": name, "value": value}
        for name, value in sorted(customer_type_breakdown.items(), key=lambda item: (-item[1], item[0]))
    ]
    top_revenue = [
        {"name": customer.name, "revenue": float(customer.totalSpend or 0), "orders": int(customer.purchaseCount or 0)}
        for customer in sorted(customers, key=lambda item: (item.totalSpend or 0), reverse=True)[:10]
    ]
    purchase_frequency = [
        {"label": "1 order", "value": sum(1 for customer in customers if (customer.purchaseCount or 0) == 1)},
        {"label": "2-3 orders", "value": sum(1 for customer in customers if 2 <= (customer.purchaseCount or 0) <= 3)},
        {"label": "4+ orders", "value": sum(1 for customer in customers if (customer.purchaseCount or 0) >= 4)},
    ]
    location_distribution = [
        {"location": (customer.city or "Unknown").strip() or "Unknown", "count": 1}
        for customer in customers
    ]
    summary_by_location: dict[str, int] = {}
    for entry in location_distribution:
        summary_by_location[entry["location"]] = summary_by_location.get(entry["location"], 0) + entry["count"]
    customer_distribution_by_location = [{"location": name, "count": count} for name, count in sorted(summary_by_location.items(), key=lambda item: (-item[1], item[0]))[:8]]
    spending_distribution = [
        {"range": "Under ₹1k", "count": sum(1 for customer in customers if (customer.totalSpend or 0) < 1000)},
        {"range": "₹1k - ₹5k", "count": sum(1 for customer in customers if 1000 <= (customer.totalSpend or 0) < 5000)},
        {"range": "₹5k - ₹10k", "count": sum(1 for customer in customers if 5000 <= (customer.totalSpend or 0) < 10000)},
        {"range": "₹10k+", "count": sum(1 for customer in customers if (customer.totalSpend or 0) >= 10000)},
    ]
    segmentation_summary = [
        {"segment": "New Customer", "count": sum(1 for customer in customers if (customer.segment or "new_customer") == "new_customer")},
        {"segment": "Regular Customer", "count": sum(1 for customer in customers if (customer.segment or "new_customer") == "regular_customer")},
        {"segment": "Loyal Customer", "count": sum(1 for customer in customers if (customer.segment or "new_customer") == "loyal_customer")},
        {"segment": "VIP Customer", "count": sum(1 for customer in customers if (customer.segment or "new_customer") == "vip_customer")},
    ]
    monthly_customer_acquisition = []
    for month_index in range(6):
        month_date = now.replace(day=1) - timedelta(days=30 * month_index)
        month_label = month_date.strftime("%b %Y")
        month_count = sum(1 for customer in customers if customer.createdAt and customer.createdAt.year == month_date.year and customer.createdAt.month == month_date.month)
        monthly_customer_acquisition.append({"month": month_label, "count": month_count})
    monthly_customer_acquisition.reverse()

    _log_customer_audit(db, str(user.companyId), user.email, "Customer Analytics Viewed")
    return CustomerAnalyticsResponse(
        totalCustomers=total_customers,
        activeCustomers=active_customers,
        inactiveCustomers=inactive_customers,
        newCustomersThisMonth=new_customers_this_month,
        returningCustomers=returning_customers,
        averageCustomerSpend=average_spend,
        totalRevenueGenerated=total_revenue_generated,
        averagePurchaseFrequency=average_purchase_frequency,
        customerTypeBreakdown=customer_type_breakdown,
        preferredSalesChannelBreakdown=preferred_sales_channel_breakdown,
        customerGrowthTrend=customer_growth,
        newVsReturningCustomers=[
            {"name": "New", "value": total_customers - customers_with_purchases},
            {"name": "Returning", "value": returning_customers},
        ],
        revenueByCustomerType=revenue_by_type,
        topCustomersByRevenue=top_revenue,
        customerPurchaseFrequency=purchase_frequency,
        customerDistributionByLocation=customer_distribution_by_location,
        monthlyCustomerAcquisition=monthly_customer_acquisition,
        customerSpendingDistribution=spending_distribution,
        segmentationSummary=segmentation_summary,
        customersWithPurchases=customers_with_purchases,
        recentCustomers=recent_customers,
    )


def export_customers(
    db: DbDependency,
    authorization: str | None = None,
    report: str = "list",
    export_format: str = "csv",
) -> Response:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    customers = db.query(Customer).filter(Customer.companyId == user.companyId, Customer.isDeleted != 1).order_by(desc(Customer.createdAt), desc(Customer.id)).all()
    analytics = get_customer_analytics(db, authorization)
    _log_customer_audit(db, str(user.companyId), user.email, "Customer Exported")

    report_key = (report or "list").strip().lower()
    export_key = (export_format or "csv").strip().lower()

    if report_key == "analytics":
        if export_key == "pdf":
            pdf_payload = "\n".join([
                "%PDF-1.4",
                "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj",
                "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj",
                "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj",
                "4 0 obj<< /Length 0 >>stream",
                f"BT /F1 12 Tf 72 720 Td (Customer Analytics Report) Tj ET",
                "endstream",
                "endobj",
                "5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj",
                "xref",
                "0 6",
                "0000000000 65535 f ",
                "0000000010 00000 n ",
                "0000000062 00000 n ",
                "0000000119 00000 n ",
                "0000000207 00000 n ",
                "0000000306 00000 n ",
                "trailer<< /Size 6 /Root 1 0 R >>",
                "startxref",
                "0",
                "%%EOF",
            ])
            return Response(pdf_payload.encode("latin-1"), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=customer-analytics-report.pdf"})

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["metric", "value"])
        writer.writerow(["totalCustomers", analytics.totalCustomers])
        writer.writerow(["activeCustomers", analytics.activeCustomers])
        writer.writerow(["inactiveCustomers", analytics.inactiveCustomers])
        writer.writerow(["newCustomersThisMonth", analytics.newCustomersThisMonth])
        writer.writerow(["returningCustomers", analytics.returningCustomers])
        writer.writerow(["averageCustomerSpend", analytics.averageCustomerSpend])
        writer.writerow(["totalRevenueGenerated", analytics.totalRevenueGenerated])
        writer.writerow(["averagePurchaseFrequency", analytics.averagePurchaseFrequency])
        return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=customer-analytics-report.csv"})

    if report_key == "top":
        top_customers = sorted(customers, key=lambda item: (item.totalSpend or 0), reverse=True)[:10]
        if export_key == "pdf":
            pdf_payload = "\n".join([
                "%PDF-1.4",
                "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj",
                "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj",
                "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj",
                "4 0 obj<< /Length 0 >>stream",
                f"BT /F1 12 Tf 72 720 Td (Top Customers Report) Tj ET",
                "endstream",
                "endobj",
                "5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj",
                "xref",
                "0 6",
                "0000000000 65535 f ",
                "0000000010 00000 n ",
                "0000000062 00000 n ",
                "0000000119 00000 n ",
                "0000000207 00000 n ",
                "0000000306 00000 n ",
                "trailer<< /Size 6 /Root 1 0 R >>",
                "startxref",
                "0",
                "%%EOF",
            ])
            return Response(pdf_payload.encode("latin-1"), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=top-customers-report.pdf"})

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["customerId", "name", "email", "phone", "totalSpend", "purchaseCount"])
        for customer in top_customers:
            writer.writerow([_customer_reference(customer), customer.name or "", customer.email or "", customer.phone or "", customer.totalSpend or 0, customer.purchaseCount or 0])
        return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=top-customers-report.csv"})

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "customerId", "name", "email", "phone", "gender", "dateOfBirth", "address", "city", "state", "country", "customerType", "preferredSalesChannel", "status", "totalSpend", "purchaseCount", "createdAt", "updatedAt"])
    for customer in customers:
        writer.writerow([
            customer.id,
            _customer_reference(customer),
            customer.name or "",
            customer.email or "",
            customer.phone or "",
            customer.gender or "",
            customer.dateOfBirth or "",
            customer.address or "",
            customer.city or "",
            customer.state or "",
            customer.country or "",
            customer.customerType or "",
            customer.preferredSalesChannel or "",
            customer.status or "",
            customer.totalSpend or 0,
            customer.purchaseCount or 0,
            customer.createdAt.isoformat() if customer.createdAt else "",
            customer.updatedAt.isoformat() if customer.updatedAt else "",
        ])
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=customer-list.csv"})


def delete_customer(customer_id: int, db: DbDependency, authorization: str | None = None) -> dict[str, Any]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.companyId == user.companyId, Customer.isDeleted != 1).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer_name = customer.name or "Customer"
    customer.isDeleted = 1
    customer.updatedAt = datetime.now(timezone.utc)
    db.commit()
    _log_customer_audit(db, company.name, user.email, "Customer Deleted", customer_name)
    return {"message": "Customer deleted", "id": customer_id}


def get_customer_timeline(customer_id: int, db: DbDependency, authorization: str | None = None) -> list[dict[str, Any]]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.companyId == user.companyId, Customer.isDeleted != 1).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return _build_customer_timeline(db, user.companyId, customer)


def get_customer_purchase_history(customer_id: int, db: DbDependency, authorization: str | None = None) -> CustomerPurchaseHistoryResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.companyId == user.companyId, Customer.isDeleted != 1).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    transactions = [
        transaction
        for transaction in db.query(SalesTransaction).filter(SalesTransaction.companyId == user.companyId).all()
        if _normalize_customer_name(transaction.customerName) == _normalize_customer_name(customer.name)
    ]
    transactions.sort(key=lambda item: item.saleDateTime or item.createdAt or datetime.now(timezone.utc), reverse=True)

    total_orders = len(transactions)
    total_revenue = sum(float(transaction.totalAmount or 0) for transaction in transactions)
    total_quantity = sum(
        int(line.quantity or 0)
        for transaction in transactions
        for line in db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == transaction.id).all()
    )
    average_order_value = (total_revenue / total_orders) if total_orders else 0
    purchase_dates = [transaction.saleDateTime for transaction in transactions if transaction.saleDateTime]

    product_counts: dict[str, int] = {}
    for transaction in transactions:
        for line in db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == transaction.id).all():
            product_name = line.productNameSnapshot or "Unknown"
            product_counts[product_name] = product_counts.get(product_name, 0) + int(line.quantity or 0)

    most_frequent_products = [
        {"product": product_name, "quantity": quantity}
        for product_name, quantity in sorted(product_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    ]
    recent_transactions = [
        {
            "id": transaction.id,
            "invoiceNumber": transaction.invoiceNumber,
            "date": transaction.saleDateTime.isoformat() if transaction.saleDateTime else None,
            "totalAmount": float(transaction.totalAmount or 0),
            "paymentMethod": transaction.paymentMethod,
        }
        for transaction in transactions[:5]
    ]

    return CustomerPurchaseHistoryResponse(
        customerId=customer.id,
        totalOrders=total_orders,
        totalRevenueGenerated=total_revenue,
        totalQuantityPurchased=total_quantity,
        averageOrderValue=average_order_value,
        firstPurchaseDate=min(purchase_dates).isoformat() if purchase_dates else None,
        lastPurchaseDate=max(purchase_dates).isoformat() if purchase_dates else None,
        mostFrequentlyPurchasedProducts=most_frequent_products,
        recentTransactions=recent_transactions,
    )
