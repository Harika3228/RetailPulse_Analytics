import csv
import io
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import Response

from backend.auth_utils import get_company_for_user, get_current_user
from backend.database import DbDependency
from backend.helpers import (
    _ensure_sales_user,
    _get_company_sales_analytics,
    _get_company_top_customers,
    _get_company_top_products,
    create_audit_log,
)
from backend.schemas import (
    SalesAnalyticsPaymentMethodResponse,
    SalesAnalyticsSummaryResponse,
    SalesAnalyticsTrendResponse,
    TopCustomerResponse,
    TopProductResponse,
)


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def _resolve_filters(
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
) -> dict[str, str | None]:
    return {
        "date_from": dateFrom,
        "date_to": dateTo,
        "product": product,
        "category": category,
        "brand": brand,
        "sales_channel": salesChannel,
        "payment_method": paymentMethod,
        "customer": customer,
    }


def analytics_sales_summary(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
) -> SalesAnalyticsSummaryResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    data = _get_company_sales_analytics(
        db, user.companyId, **_resolve_filters(
            dateFrom, dateTo, product, category, brand, salesChannel, paymentMethod, customer,
        )
    )
    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="Sales Analytics Summary Viewed", ip_address="Unknown", browser="Unknown",
    )
    return SalesAnalyticsSummaryResponse(
        totalRevenue=data["totalRevenue"],
        totalOrders=data["totalOrders"],
        totalProductsSold=data["totalProductsSold"],
        averageOrderValue=data["averageOrderValue"],
        totalDiscount=data["totalDiscount"],
        totalTax=data["totalTax"],
    )


def analytics_sales_trend(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
) -> SalesAnalyticsTrendResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    data = _get_company_sales_analytics(
        db, user.companyId, **_resolve_filters(
            dateFrom, dateTo, product, category, brand, salesChannel, paymentMethod, customer,
        )
    )
    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="Sales Analytics Trend Viewed", ip_address="Unknown", browser="Unknown",
    )
    return SalesAnalyticsTrendResponse(
        revenueTrend=data["revenueTrend"],
        salesTrend=data["salesTrend"],
        orderTrend=data["orderTrend"],
    )


def analytics_sales_products(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 50,
) -> list[TopProductResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    rows = _get_company_top_products(
        db,
        user.companyId,
        date_from=dateFrom,
        date_to=dateTo,
        product=product,
        category=category,
        brand=brand,
        sales_channel=salesChannel,
        payment_method=paymentMethod,
        customer=customer,
        limit=limit,
    )
    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="Sales Analytics Products Viewed", ip_address="Unknown", browser="Unknown",
    )
    return [TopProductResponse(**row) for row in rows]


def analytics_sales_customers(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
    limit: int | None = 20,
) -> list[TopCustomerResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    rows = _get_company_top_customers(
        db,
        user.companyId,
        date_from=dateFrom,
        date_to=dateTo,
        sales_channel=salesChannel,
        payment_method=paymentMethod,
        customer=customer,
        limit=limit,
    )
    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="Sales Analytics Customers Viewed", ip_address="Unknown", browser="Unknown",
    )
    return [TopCustomerResponse(**row) for row in rows]


def analytics_sales_payment_methods(
    db: DbDependency,
    authorization: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
) -> SalesAnalyticsPaymentMethodResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    data = _get_company_sales_analytics(
        db, user.companyId, **_resolve_filters(
            dateFrom, dateTo, product, category, brand, salesChannel, paymentMethod, customer,
        )
    )
    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="Sales Analytics Payment Methods Viewed", ip_address="Unknown", browser="Unknown",
    )
    return SalesAnalyticsPaymentMethodResponse(
        paymentMethods=data["paymentMethods"],
        totalRevenue=data["totalRevenue"],
        totalOrders=data["totalOrders"],
    )


def _format_money(value) -> str:
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _filter_labels(filters: dict[str, str | None]) -> str:
    parts = []
    for label, key in (
        ("Date From", "date_from"),
        ("Date To", "date_to"),
        ("Product", "product"),
        ("Category", "category"),
        ("Brand", "brand"),
        ("Sales Channel", "sales_channel"),
        ("Payment Method", "payment_method"),
        ("Customer", "customer"),
    ):
        value = filters.get(key)
        if value:
            parts.append(f"{label}: {value}")
    return ", ".join(parts) if parts else "All data"


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf_report(company_name: str, lines: list[str]) -> bytes:
    """Build a minimal, valid single-page PDF with the given text lines."""
    content_lines = [f"BT /F1 14 Tf 72 738 Td ({_pdf_escape(company_name or 'Sales Analytics Report')}) Tj ET"]
    content_lines.append(
        f"BT /F1 9 Tf 72 722 Td (Generated: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M')} UTC) Tj ET"
    )
    y = 700
    for line in lines:
        content_lines.append(f"BT /F1 9 Tf 72 {y} Td ({_pdf_escape(line)}) Tj ET")
        y -= 12
        if y < 40:
            break

    stream_content = "\n".join(content_lines).encode("latin-1", errors="replace")
    object_4 = (
        b"4 0 obj\n<< /Length "
        + str(len(stream_content)).encode("ascii")
        + b" >>\nstream\n"
        + stream_content
        + b"\nendstream\nendobj\n"
    )
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        object_4,
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0] * (len(objects) + 1)
    for index, obj in enumerate(objects, start=1):
        offsets[index] = len(output)
        output.extend(obj)

    xref_offset = len(output)
    output.extend(b"xref\n0 " + str(len(objects) + 1).encode("ascii") + b"\n")
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF"
    )
    return bytes(output)


def _analytics_report_sections(data: dict[str, object], products: list[dict], customers: list[dict]) -> dict[str, list[list[str]]]:
    """Build the report rows (section header + rows) shared by CSV and PDF exports."""
    sections: dict[str, list[list[str]]] = {}
    sections["KPIs"] = [
        ["Metric", "Value"],
        ["Total Revenue", _format_money(data["totalRevenue"])],
        ["Total Orders", str(data["totalOrders"])],
        ["Total Products Sold", str(data["totalProductsSold"])],
        ["Average Order Value", _format_money(data["averageOrderValue"])],
        ["Total Discount", _format_money(data["totalDiscount"])],
        ["Total Tax", _format_money(data["totalTax"])],
    ]
    monthly_trend = data.get("revenueTrend", {})
    trend_rows = monthly_trend.get("monthly", []) if isinstance(monthly_trend, dict) else []
    sections["Revenue Trend (Monthly)"] = [["Period", "Revenue"], *[
        [str(point.get("label", "")), _format_money(point.get("value"))] for point in trend_rows
    ]]
    sections["Top Products"] = [
        ["#", "Product Name", "SKU", "Units Sold", "Revenue"],
        *[
            [str(index), str(product.get("name", "")), str(product.get("sku", "")),
             str(product.get("quantity", 0)), _format_money(product.get("revenue"))]
            for index, product in enumerate(products, start=1)
        ],
    ]
    sections["Top Customers"] = [
        ["#", "Customer Name", "Orders", "Total Spend", "Average Order Value"],
        *[
            [str(index), str(customer.get("name", "")), str(customer.get("orders", 0)),
             _format_money(customer.get("totalSpend")), _format_money(customer.get("averageOrderValue"))]
            for index, customer in enumerate(customers, start=1)
        ],
    ]
    payment_methods = data.get("paymentMethods", [])
    sections["Payment Methods"] = [
        ["Payment Method", "Orders", "Revenue"],
        *[
            [str(entry.get("paymentMethod", "")), str(entry.get("orders", 0)),
             _format_money(entry.get("revenue"))]
            for entry in payment_methods
        ],
    ]
    return sections


def analytics_sales_export(
    db: DbDependency,
    authorization: str | None = None,
    export_format: str = "csv",
    dateFrom: str | None = None,
    dateTo: str | None = None,
    product: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    salesChannel: str | None = None,
    paymentMethod: str | None = None,
    customer: str | None = None,
) -> Response:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_sales_user(user)

    filters = _resolve_filters(
        dateFrom, dateTo, product, category, brand, salesChannel, paymentMethod, customer,
    )
    data = _get_company_sales_analytics(db, user.companyId, **filters)
    top_products = _get_company_top_products(db, user.companyId, **filters, limit=50)
    customer_filters = {
        key: filters[key]
        for key in ("date_from", "date_to", "sales_channel", "payment_method", "customer")
    }
    top_customers = _get_company_top_customers(db, user.companyId, **customer_filters, limit=20)
    company = get_company_for_user(db, user)
    company_name = company.name or ""

    create_audit_log(
        db, company=str(user.companyId), user=user.email,
        action="Sales Analytics Exported", entity_name="Sales Analytics Export",
        invoice_number=export_format.upper(), ip_address="Unknown", browser="Unknown",
    )

    generated_at = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    if export_format.lower() == "pdf":
        sections = _analytics_report_sections(data, top_products[:10], top_customers[:10])
        lines = [f"Filters: {_filter_labels(filters)}", f"Generated: {generated_at}", ""]
        for section_title, rows in sections.items():
            lines.append(f"{section_title}")
            for row in rows[1:]:
                lines.append("  " + "  |  ".join(row))
            lines.append("")
        return Response(
            _build_pdf_report(company_name, lines),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=sales-analytics-report.pdf"},
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Sales Analytics Report", company_name])
    writer.writerow(["Generated At", generated_at])
    writer.writerow(["Filters", _filter_labels(filters)])
    writer.writerow([])
    sections = _analytics_report_sections(data, top_products, top_customers)
    for section_title, rows in sections.items():
        writer.writerow([f"[{section_title}]"])
        writer.writerows(rows)
        writer.writerow([])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales-analytics-report.csv"},
    )
