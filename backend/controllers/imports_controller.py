import csv
import io
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException, Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.auth_utils import get_company_for_user, get_current_user
from backend.cache import invalidate_forecast_cache
from backend.controllers.customers_controller import (
    _normalize_email,
    _normalize_phone,
    refresh_customer_metrics_for_company,
)
from backend.database import DbDependency
from backend.helpers import (
    _apply_sales_stock_delta,
    _ensure_admin,
    _next_company_invoice_number,
    _parse_sale_datetime,
    create_audit_log,
    create_notification,
)
from backend.models import (
    Category,
    Customer,
    ImportBatch,
    ImportRecord,
    Product,
    SalesTransaction,
    SalesTransactionLine,
)
from backend.schemas import (
    ImportBatchDetailResponse,
    ImportBatchResponse,
    ImportConfirmResponse,
    ImportErrorResponse,
    ImportErrorsResponse,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportRecordResponse,
)

# ---------------------------------------------------------------------------
# Data-integrity / transaction strategy
# ---------------------------------------------------------------------------
# Imports are staged as a preview (upload + validation) which persists an
# ImportBatch plus one ImportRecord per CSV row. Processing (confirm) then:
#
# Database transactions
#   1. The batch is moved to "processing" and committed.
#   2. Every valid record is written inside a SAVEPOINT (db.begin_nested()).
#      Products, customers, and invoice groups each get their own savepoint so a
#      rejected row never affects its neighbours.
#   3. On an UNEXPECTED exception the whole transaction is ROLLED BACK and the
#      batch is marked "failed". No products, sales, or stock deltas from the
#      failed batch are left behind.
#   4. On success the batch status/counts and all inserted rows commit together.
#
# Batch processing & partial success
#   Expected failures (validation errors, duplicates, per-group import issues)
#   are caught inside each savepoint and recorded on the ImportRecord, so those
#   rows are skipped while every other valid row still imports. The batch then
#   finishes as "completed_with_errors" and the row-level messages remain visible
#   in import history. This is deliberate partial-success processing: a bad row
#   never aborts the whole batch, and an unexpected crash never leaves the DB
#   half-committed.
#
# Derived data/near-time derivations
#   Fast-path writes (stock movements, notifications, audit logs) are emitted
#   with commit=False and flushed with the enclosing transaction. Recompute-heavy
#   customer metrics are refreshed only AFTER the batch has committed, so derived
#   counters are never persisted ahead of (or without) the sales they summarise.
# ---------------------------------------------------------------------------

MAX_IMPORT_ROWS = 2000
MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
SKU_PATTERN = r"[A-Z0-9-]+"

ENTITY_TYPES = {"products", "customers", "sales"}

FIELD_ALIASES = {
    "products": {
        "sku": {"sku", "skucode", "productcode", "itemcode"},
        "name": {"name", "productname", "product"},
        "categoryid": {"categoryid", "catid"},
        "categoryname": {"categoryname", "category", "catname"},
        "brand": {"brand", "brandname"},
        "description": {"description", "desc"},
        "unitprice": {"unitprice", "price", "sellingprice"},
        "costprice": {"costprice", "cost", "purchaseprice"},
        "stockquantity": {"stockquantity", "stock", "quantity", "qty", "openingstock"},
        "maxstocklevel": {"maxstocklevel", "maxstock"},
        "unitofmeasure": {"unitofmeasure", "uom", "unit", "units"},
        "status": {"status"},
    },
    "customers": {
        "name": {"name", "customername", "fullname"},
        "email": {"email", "emailaddress"},
        "phone": {"phone", "phonenumber", "mobile", "contact"},
        "dateofbirth": {"dateofbirth", "dob"},
        "gender": {"gender"},
        "address": {"address", "streetaddress"},
        "city": {"city"},
        "state": {"state"},
        "country": {"country"},
        "postalcode": {"postalcode", "zipcode", "zip", "pincode"},
        "customertype": {"customertype", "type"},
        "preferredsaleschannel": {"preferredsaleschannel", "channel", "saleschannel"},
        "status": {"status"},
    },
    "sales": {
        "invoicenumber": {"invoicenumber", "invoice", "invoiceno", "billnumber", "billno"},
        "sku": {"sku", "productsku", "productcode", "itemcode"},
        "productid": {"productid"},
        "quantity": {"quantity", "qty"},
        "unitprice": {"unitprice", "price", "rate"},
        "customeremail": {"customeremail", "email"},
        "customername": {"customername", "customer"},
        "saledatetime": {"saledatetime", "saledate", "date", "transactiondate"},
        "saleschannel": {"saleschannel", "channel"},
        "paymentmethod": {"paymentmethod", "payment", "paymenttype"},
        "paymentstatus": {"paymentstatus"},
        "discountamount": {"discountamount", "discount"},
        "taxamount": {"taxamount", "tax"},
    },
}

# Each entry is a list of column groups; every group must have at least one
# recognized column present in the uploaded file for the import to proceed.
REQUIRED_COLUMN_GROUPS = {
    "products": ({"sku"}, {"name"}, {"unitprice"}, {"stockquantity"}, {"categoryid", "categoryname"}),
    "customers": ({"name"}, {"email"}, {"phone"}),
    "sales": (
        {"sku", "productid"},
        {"quantity"},
        {"customername", "customeremail"},
        {"unitprice"},
        {"saledatetime"},
    ),
}

REQUIRED_COLUMN_LABELS = {
    "products": {
        "sku": "SKU",
        "name": "Product Name",
        "unitprice": "Unit Price",
        "stockquantity": "Stock Quantity",
        "categoryid": "CategoryId",
        "categoryname": "CategoryName",
    },
    "customers": {
        "name": "Customer Name",
        "email": "Email",
        "phone": "Phone",
    },
    "sales": {
        "sku": "Product SKU",
        "productid": "ProductId",
        "quantity": "Quantity",
        "customername": "Customer Name",
        "customeremail": "Customer Email",
        "unitprice": "Unit Price",
        "saledatetime": "Sale Date",
    },
}


# ---------------------------------------------------------------------------
# Token / access helpers
# ---------------------------------------------------------------------------

def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]


def _authorize_admin(db: DbDependency, authorization: str | None):
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)
    return user, company


def normalize_entity_type(entity_type: str | None) -> str:
    normalized = (entity_type or "").strip().lower()
    if normalized in ("product", "customer", "sale"):
        normalized += "s"
    if normalized not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="Entity type must be 'products', 'customers', or 'sales'")
    return normalized


# ---------------------------------------------------------------------------
# CSV parsing helpers
# ---------------------------------------------------------------------------

def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="Unable to read the uploaded file. Please upload a UTF-8 encoded CSV.")


def _normalize_header(header: str) -> str:
    return re.sub(r"[\s_-]+", "", header.strip().lower())


def _map_headers(fieldnames: list[str], entity_type: str) -> dict[str, str]:
    aliases = FIELD_ALIASES[entity_type]
    mapping: dict[str, str] = {}
    for raw in fieldnames or []:
        normalized = _normalize_header(raw)
        for canonical, alias_set in aliases.items():
            if normalized == canonical or normalized in alias_set:
                mapping[raw] = canonical
                break
    return mapping


def parse_csv_rows(raw: bytes, entity_type: str) -> tuple[list[dict[str, str]], list[str]]:
    text = _decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise HTTPException(status_code=400, detail="The CSV file appears to be empty")

    mapping = _map_headers(fieldnames, entity_type)
    recognized = set(mapping.values())
    missing_groups = [group for group in REQUIRED_COLUMN_GROUPS[entity_type] if not group.intersection(recognized)]
    if missing_groups:
        labels = REQUIRED_COLUMN_LABELS[entity_type]
        described = ", ".join(
            " or ".join(labels.get(column, column) for column in sorted(group))
            for group in missing_groups
        )
        raise HTTPException(status_code=400, detail=f"CSV is missing required column(s): {described}")

    rows: list[dict[str, str]] = []
    for line_number, raw_row in enumerate(reader, start=2):
        if raw_row is None:
            continue
        values = [value for value in raw_row.values() if value is not None]
        if all(str(value).strip() == "" for value in values):
            continue
        row_data = {
            mapping[key]: (str(value).strip() if value is not None else "")
            for key, value in raw_row.items()
            if key in mapping
        }
        row_data["__raw__"] = {
            str(key): (str(value) if value is not None else "")
            for key, value in raw_row.items()
            if key is not None
        }
        row_data["__line__"] = str(line_number)
        rows.append(row_data)
        if len(rows) >= MAX_IMPORT_ROWS:
            break

    if not rows:
        raise HTTPException(status_code=400, detail="The CSV file contains no data rows")
    return rows, fieldnames


def _cell(row: dict[str, str], key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) else ""


def _clean_numeric_string(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"

    text = text.replace(" ", "")
    text = re.sub(r"[\u00A0\t\r\n]", "", text)
    text = re.sub(r"(?i)[^0-9,\.\-+]", "", text)

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "")

    return text


def _to_float(value: str) -> float | None:
    cleaned = _clean_numeric_string(value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_int(value: str) -> int | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _parse_date_cell(value: str) -> datetime | None:
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return _parse_sale_datetime(value)
    except (ValueError, TypeError):
        return None


def _normalize_sku_cell(value: str) -> str:
    return value.strip().upper()


def _normalize_category_key(value: str) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    normalized = re.sub(r"[_\-\s]+", "", normalized)
    return normalized


# ---------------------------------------------------------------------------
# Per-entity row validation
# ---------------------------------------------------------------------------

def _validate_product_row(
    row: dict[str, str],
    category_index: dict[str, int],
    existing_skus: set[str],
    seen_skus: set[str],
) -> tuple[dict, list[str], bool]:
    messages: list[str] = []
    sku = _normalize_sku_cell(_cell(row, "sku"))
    name = _cell(row, "name")

    if not sku:
        messages.append("SKU is required")
    elif not re.fullmatch(SKU_PATTERN, sku):
        messages.append("SKU must contain only letters, numbers, and hyphens")
    if not name:
        messages.append("Product name is required")

    unit_price = _to_float(_cell(row, "unitprice"))
    if unit_price is None:
        messages.append("Unit price is required and must be numeric")
    elif unit_price <= 0:
        messages.append("Unit price must be greater than zero")

    cost_price = _to_float(_cell(row, "costprice")) if _cell(row, "costprice") else unit_price
    if cost_price is None:
        messages.append("Cost price must be numeric")
    elif cost_price < 0:
        messages.append("Cost price cannot be negative")
    elif unit_price is not None and cost_price > unit_price:
        messages.append("Cost price cannot exceed unit price")

    stock_quantity = _to_int(_cell(row, "stockquantity"))
    if stock_quantity is None:
        stock_quantity = 0
    elif stock_quantity < 0:
        messages.append("Stock quantity cannot be negative")

    max_stock_level = None
    if _cell(row, "maxstocklevel"):
        max_stock_level = _to_int(_cell(row, "maxstocklevel"))
        if max_stock_level is None or max_stock_level < 0:
            messages.append("Max stock level must be a non-negative number")

    status = (_cell(row, "status") or "active").lower()
    if status not in ("active", "inactive"):
        messages.append("Status must be 'active' or 'inactive'")

    category_reference = _cell(row, "categoryid") or _cell(row, "categoryname")
    resolved_category_id = None
    if category_reference:
        category_key = _normalize_category_key(category_reference)
        resolved_category_id = category_index.get(category_key) if category_key else None
        if resolved_category_id is None:
            category_reference_raw = _cell(row, "categoryid") or _cell(row, "categoryname")
            direct_id = _to_int(category_reference_raw)
            if direct_id is not None:
                resolved_category_id = category_index.get(str(direct_id))
            if resolved_category_id is None:
                messages.append(f"Category not found: {category_reference}")
    else:
        messages.append("Category is required (provide categoryId or categoryName)")

    duplicate = False
    if sku:
        if sku in existing_skus:
            duplicate = True
            messages.append(f"Duplicate SKU already exists in system: {sku}")
        elif sku in seen_skus:
            duplicate = True
            messages.append(f"Duplicate SKU within file: {sku}")
        seen_skus.add(sku)

    resolved = {
        "sku": sku,
        "name": name,
        "categoryId": resolved_category_id,
        "brand": _cell(row, "brand"),
        "description": _cell(row, "description"),
        "unitPrice": unit_price,
        "costPrice": cost_price,
        "stockQuantity": stock_quantity,
        "maxStockLevel": max_stock_level,
        "unitOfMeasure": _cell(row, "unitofmeasure") or "piece",
        "status": status,
    }
    return resolved, messages, duplicate


def _validate_customer_row(
    row: dict[str, str],
    existing_emails: set[str],
    existing_phones: set[str],
    seen_emails: set[str],
    seen_phones: set[str],
) -> tuple[dict, list[str], bool]:
    messages: list[str] = []
    name = _cell(row, "name")
    email = _normalize_email(_cell(row, "email"))
    phone_digits = _normalize_phone(_cell(row, "phone"))

    if not name:
        messages.append("Customer name is required")
    if not email:
        messages.append("Email is required")
    elif not re.match(EMAIL_PATTERN, email):
        messages.append("Invalid email format")
    if not phone_digits:
        messages.append("Phone number is required")
    elif len(phone_digits) < 10:
        messages.append("Phone number must have at least 10 digits")

    duplicate = False
    if email and (email in existing_emails or email in seen_emails):
        duplicate = True
        messages.append(f"Duplicate email already exists: {email}")
    elif phone_digits and (phone_digits in existing_phones or phone_digits in seen_phones):
        duplicate = True
        messages.append("Duplicate phone number already exists")

    status = (_cell(row, "status") or "active").lower()
    if status not in ("active", "inactive"):
        messages.append("Status must be 'active' or 'inactive'")

    if email:
        seen_emails.add(email)
    if phone_digits:
        seen_phones.add(phone_digits)

    resolved = {
        "name": name,
        "email": email,
        "phone": _cell(row, "phone"),
        "dateOfBirth": _cell(row, "dateofbirth"),
        "gender": _cell(row, "gender"),
        "address": _cell(row, "address"),
        "city": _cell(row, "city"),
        "state": _cell(row, "state"),
        "country": _cell(row, "country"),
        "postalCode": _cell(row, "postalcode"),
        "customerType": (_cell(row, "customertype") or "retail").lower(),
        "preferredSalesChannel": (_cell(row, "preferredsaleschannel") or "offline").lower(),
        "status": status,
    }
    return resolved, messages, duplicate


def _validate_sales_row(
    row: dict[str, str],
    product_index: dict[str, tuple[int, float, int]],
    customer_index: tuple[set[str], set[str]],
    existing_invoices: set[str],
    allocated_stock: dict[str, int],
) -> tuple[dict, list[str], bool]:
    messages: list[str] = []
    sku = _normalize_sku_cell(_cell(row, "sku"))
    product_id = _to_int(_cell(row, "productid"))

    product_key: str | None = None
    product_info = None
    if sku:
        product_key = f"sku:{sku}"
        product_info = product_index.get(product_key)
        if product_info is None:
            messages.append(f"Product not found by SKU: {sku}")
    elif product_id is not None:
        product_key = f"id:{product_id}"
        product_info = product_index.get(product_key)
        if product_info is None:
            messages.append(f"Product not found by productId: {product_id}")
    else:
        messages.append("Either 'sku' or 'productId' is required")

    customer_name = _cell(row, "customername")
    customer_email = _normalize_email(_cell(row, "customeremail"))
    if not customer_name and not customer_email:
        messages.append("Customer is required (provide customerName or customerEmail)")
    else:
        existing_emails, existing_names = customer_index
        if customer_email:
            if customer_email not in existing_emails:
                messages.append(f"No customer found with email: {customer_email}")
        elif customer_name.lower() not in existing_names:
            messages.append(f"No customer found with name: {customer_name}")

    quantity = _to_int(_cell(row, "quantity"))
    if quantity is None:
        messages.append("Quantity is required and must be a whole number")
    elif quantity <= 0:
        messages.append("Quantity must be greater than zero")

    unit_price_override = None
    if _cell(row, "unitprice"):
        unit_price_override = _to_float(_cell(row, "unitprice"))
        if unit_price_override is None or unit_price_override <= 0:
            messages.append("Unit price must be a positive number")
    else:
        messages.append("Unit price is required and must be numeric")

    if product_key and product_info is not None and quantity is not None and quantity > 0:
        _, default_price, available = product_info
        already_allocated = allocated_stock.get(product_key, 0)
        remaining = available - already_allocated
        if quantity > remaining:
            messages.append(f"Insufficient stock for this product: requested {quantity}, available {max(remaining, 0)}")
        else:
            allocated_stock[product_key] = already_allocated + quantity

    invoice_number = _cell(row, "invoicenumber")
    duplicate = False
    if invoice_number and invoice_number in existing_invoices:
        duplicate = True
        messages.insert(0, f"Duplicate invoice number already exists: {invoice_number}")

    sale_iso = None
    if _cell(row, "saledatetime"):
        parsed = _parse_date_cell(_cell(row, "saledatetime"))
        if parsed is None:
            messages.append("Invalid sale date format (use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")
        else:
            sale_iso = parsed.isoformat()
    else:
        messages.append("Sale date is required (use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")

    discount_amount = _to_float(_cell(row, "discountamount")) or 0
    tax_amount = _to_float(_cell(row, "taxamount")) or 0
    if discount_amount < 0 or tax_amount < 0:
        messages.append("Discount and tax amounts cannot be negative")

    resolved = {
        "invoiceNumber": invoice_number,
        "sku": sku,
        "productId": product_id,
        "quantity": quantity,
        "unitPrice": unit_price_override,
        "defaultUnitPrice": product_info[1] if product_info else None,
        "productKey": product_key,
        "customerEmail": customer_email,
        "customerName": customer_name,
        "saleDateTime": sale_iso,
        "salesChannel": _cell(row, "saleschannel") or "In-Store",
        "paymentMethod": _cell(row, "paymentmethod") or "Cash",
        "paymentStatus": _cell(row, "paymentstatus") or "Paid",
        "discountAmount": discount_amount,
        "taxAmount": tax_amount,
    }
    return resolved, messages, duplicate


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------

def _build_category_index(db: DbDependency, company_id: int) -> dict[str, int]:
    categories = db.query(Category).filter(Category.companyId == company_id).all()
    index: dict[str, int] = {}
    for category in categories:
        if category.name:
            name_key = _normalize_category_key(category.name)
            if name_key:
                index.setdefault(name_key, category.id)
            index.setdefault(category.name.strip().lower(), category.id)
        index[str(category.id)] = category.id
    return index


def _build_product_index(db: DbDependency, company_id: int) -> dict[str, tuple[int, float, int]]:
    products = db.query(Product).filter(Product.companyId == company_id).all()
    index: dict[str, tuple[int, float, int]] = {}
    for product in products:
        available = int(product.stockQuantity if product.stockQuantity is not None else product.initialStockQuantity or 0)
        info = (product.id, float(product.unitPrice or 0), available)
        if product.sku:
            index[f"sku:{product.sku.strip().upper()}"] = info
        index[f"id:{product.id}"] = info
    return index


def _existing_customer_keys(db: DbDependency, company_id: int) -> tuple[set[str], set[str]]:
    customers = (
        db.query(Customer)
        .filter(Customer.companyId == company_id, Customer.isDeleted != 1)
        .all()
    )
    emails = {_normalize_email(item.email) for item in customers if item.email}
    phones = {_normalize_phone(item.phone) for item in customers if item.phone}
    phones.discard("")
    return emails, phones


def _build_sales_customer_index(db: DbDependency, company_id: int) -> tuple[set[str], set[str]]:
    customers = (
        db.query(Customer)
        .filter(Customer.companyId == company_id, Customer.isDeleted != 1)
        .all()
    )
    emails = {_normalize_email(item.email) for item in customers if item.email}
    names = {item.name.strip().lower() for item in customers if item.name}
    return emails, names


# ---------------------------------------------------------------------------
# Preview (upload -> validation -> preview)
# ---------------------------------------------------------------------------

def _row_payload(row: dict[str, str], resolved: dict) -> str:
    display = {key: value for key, value in row.items() if not key.startswith("__")}
    return json.dumps({"row": display, "resolved": resolved}, default=str)


def create_import_preview(
    raw: bytes,
    entity_type_raw: str,
    file_name: str,
    db: DbDependency,
    authorization: str | None = None,
) -> ImportPreviewResponse:
    user, _company = _authorize_admin(db, authorization)
    entity_type = normalize_entity_type(entity_type_raw)

    if len(raw or b"") > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large. Maximum allowed size is {MAX_IMPORT_FILE_BYTES // (1024 * 1024)} MB.",
        )

    rows, columns = parse_csv_rows(raw, entity_type)

    preview_rows: list[ImportPreviewRow] = []
    valid_count = 0
    invalid_count = 0
    duplicate_count = 0

    if entity_type == "products":
        category_index = _build_category_index(db, user.companyId)
        existing_skus = {
            row[0].strip().upper()
            for row in db.query(Product.sku).filter(Product.companyId == user.companyId).all()
            if row[0]
        }
        seen_skus: set[str] = set()
        for row in rows:
            resolved, messages, duplicate = _validate_product_row(row, category_index, existing_skus, seen_skus)
            status = "duplicate" if duplicate else ("invalid" if messages else "valid")
            valid_count += status == "valid"
            invalid_count += status == "invalid"
            duplicate_count += status == "duplicate"
            preview_rows.append(
                ImportPreviewRow(
                    rowNumber=int(row.get("__line__") or 0),
                    status=status,
                    messages=messages,
                    data=resolved,
                    rawData=dict(row.get("__raw__") or {}),
                )
            )
    elif entity_type == "customers":
        existing_emails, existing_phones = _existing_customer_keys(db, user.companyId)
        seen_emails: set[str] = set()
        seen_phones: set[str] = set()
        for row in rows:
            resolved, messages, duplicate = _validate_customer_row(row, existing_emails, existing_phones, seen_emails, seen_phones)
            status = "duplicate" if duplicate else ("invalid" if messages else "valid")
            valid_count += status == "valid"
            invalid_count += status == "invalid"
            duplicate_count += status == "duplicate"
            preview_rows.append(
                ImportPreviewRow(
                    rowNumber=int(row.get("__line__") or 0),
                    status=status,
                    messages=messages,
                    data=resolved,
                    rawData=dict(row.get("__raw__") or {}),
                )
            )
    else:
        product_index = _build_product_index(db, user.companyId)
        customer_index = _build_sales_customer_index(db, user.companyId)
        existing_invoices = {
            row[0]
            for row in db.query(SalesTransaction.invoiceNumber)
            .filter(SalesTransaction.companyId == user.companyId)
            .all()
            if row[0]
        }
        allocated_stock: dict[str, int] = {}
        for row in rows:
            resolved, messages, duplicate = _validate_sales_row(row, product_index, customer_index, existing_invoices, allocated_stock)
            status = "duplicate" if duplicate else ("invalid" if messages else "valid")
            valid_count += status == "valid"
            invalid_count += status == "invalid"
            duplicate_count += status == "duplicate"
            preview_rows.append(
                ImportPreviewRow(
                    rowNumber=int(row.get("__line__") or 0),
                    status=status,
                    messages=messages,
                    data=resolved,
                    rawData=dict(row.get("__raw__") or {}),
                )
            )

    batch = ImportBatch(
        companyId=user.companyId,
        entityType=entity_type,
        fileName=file_name or f"{entity_type}.csv",
        totalRows=len(rows),
        validCount=valid_count,
        invalidCount=invalid_count,
        duplicateCount=duplicate_count,
        insertedCount=0,
        updatedCount=0,
        failedCount=0,
        status="pending",
        importedBy=user.email,
        createdAt=datetime.now(timezone.utc),
    )
    db.add(batch)
    db.flush()

    records = [
        ImportRecord(
            batchId=batch.id,
            companyId=user.companyId,
            rowNumber=preview_row.rowNumber,
            status=preview_row.status,
            message="; ".join(preview_row.messages) if preview_row.messages else None,
            rowData=_row_payload(rows[index], preview_row.data),
            createdAt=datetime.now(timezone.utc),
        )
        for index, preview_row in enumerate(preview_rows)
    ]
    db.add_all(records)
    db.commit()

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action=f"Data Import Preview:{entity_type}",
        entity_name=batch.fileName,
        ip_address="Unknown",
        browser="Unknown",
    )
    return ImportPreviewResponse(
        batchId=batch.id,
        entityType=entity_type,
        fileName=batch.fileName,
        totalRows=batch.totalRows,
        validRows=valid_count,
        invalidRows=invalid_count,
        duplicateRows=duplicate_count,
        columns=list(columns),
        columnMapping=_map_headers(list(columns), entity_type),
        rows=preview_rows,
    )


# ---------------------------------------------------------------------------
# Confirm (preview -> import processing -> database)
# ---------------------------------------------------------------------------

def _load_pending_batch(db: DbDependency, user, batch_id: int) -> ImportBatch:
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id, ImportBatch.companyId == user.companyId).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    if batch.status != "pending":
        raise HTTPException(status_code=400, detail=f"Import batch has already been {batch.status}")
    return batch


def _process_product_records(db: DbDependency, user, records: list[ImportRecord]) -> tuple[int, int]:
    inserted = 0
    failed = 0
    for record in records:
        resolved = json.loads(record.rowData).get("resolved", {})
        product = Product(
            companyId=user.companyId,
            categoryId=resolved.get("categoryId"),
            sku=resolved.get("sku"),
            name=resolved.get("name"),
            brand=resolved.get("brand") or "",
            description=resolved.get("description") or "",
            unitPrice=resolved.get("unitPrice"),
            costPrice=resolved.get("costPrice"),
            stockQuantity=resolved.get("stockQuantity") or 0,
            initialStockQuantity=resolved.get("stockQuantity") or 0,
            maxStockLevel=resolved.get("maxStockLevel"),
            unitOfMeasure=resolved.get("unitOfMeasure") or "piece",
            price=str(resolved.get("unitPrice")),
            status=resolved.get("status") or "active",
            createdAt=datetime.now(timezone.utc),
            updatedAt=datetime.now(timezone.utc),
        )
        try:
            with db.begin_nested():
                db.add(product)
                db.flush()
            record.status = "imported"
            record.message = None
            inserted += 1
        except IntegrityError:
            record.status = "failed"
            record.message = "SKU already exists"
            failed += 1
    return inserted, failed


def _process_customer_records(db: DbDependency, user, records: list[ImportRecord]) -> tuple[int, int]:
    inserted = 0
    failed = 0
    used_ids = {
        row[0]
        for row in db.query(Customer.customerId)
        .filter(Customer.companyId == user.companyId, Customer.customerId.isnot(None))
        .all()
    }
    now = datetime.now(timezone.utc)
    for record in records:
        resolved = json.loads(record.rowData).get("resolved", {})
        customer = Customer(
            companyId=user.companyId,
            name=resolved.get("name") or "Unknown Customer",
            email=resolved.get("email"),
            phone=resolved.get("phone"),
            dateOfBirth=resolved.get("dateOfBirth"),
            gender=resolved.get("gender"),
            address=resolved.get("address"),
            city=resolved.get("city"),
            state=resolved.get("state"),
            country=resolved.get("country"),
            postalCode=resolved.get("postalCode"),
            customerType=resolved.get("customerType") or "retail",
            preferredSalesChannel=resolved.get("preferredSalesChannel") or "offline",
            status=resolved.get("status") or "active",
            createdAt=now,
            updatedAt=now,
        )
        try:
            with db.begin_nested():
                db.add(customer)
                db.flush()
                prefix = f"CUST-{user.companyId}-"
                counter = 1
                while f"{prefix}{counter:05d}" in used_ids:
                    counter += 1
                customer.customerId = f"{prefix}{counter:05d}"
                used_ids.add(customer.customerId)
            record.status = "imported"
            record.message = None
            inserted += 1
        except IntegrityError:
            record.status = "failed"
            record.message = "Customer could not be imported"
            failed += 1
    return inserted, failed


def _resolve_import_customer(db: DbDependency, user, resolved: dict) -> tuple[str, int | None]:
    customer_email = resolved.get("customerEmail") or ""
    customer_id_value = resolved.get("customerId")
    if customer_id_value:
        customer = (
            db.query(Customer)
            .filter(Customer.id == int(customer_id_value), Customer.companyId == user.companyId, Customer.isDeleted != 1)
            .first()
        )
        if not customer:
            raise ValueError(f"Customer not found: {customer_id_value}")
        return customer.name or "Unknown Customer", customer.id
    if customer_email:
        customer = (
            db.query(Customer)
            .filter(Customer.email == customer_email, Customer.companyId == user.companyId, Customer.isDeleted != 1)
            .first()
        )
        if not customer:
            raise ValueError(f"No customer found with email: {customer_email}")
        return customer.name or "Unknown Customer", customer.id
    customer_name = (resolved.get("customerName") or "").strip()
    if customer_name:
        customer = (
            db.query(Customer)
            .filter(
                func.lower(Customer.name) == customer_name.lower(),
                Customer.companyId == user.companyId,
                Customer.isDeleted != 1,
            )
            .first()
        )
        if not customer:
            raise ValueError(f"No customer found with name: {customer_name}")
        return customer.name or "Unknown Customer", customer.id
    return "Walk-in Customer", None


def _build_sale_line_payloads(product_index: dict[str, tuple[int, float, int]], records: list[ImportRecord]) -> list[dict]:
    lines: list[dict] = []
    for record in records:
        resolved = json.loads(record.rowData).get("resolved", {})
        unit_price = float(
            resolved.get("unitPrice") if resolved.get("unitPrice") is not None else resolved.get("defaultUnitPrice") or 0
        )
        quantity = int(resolved.get("quantity") or 0)
        product_key = resolved.get("productKey")
        info = product_index.get(product_key) if isinstance(product_key, str) else None
        lines.append(
            {
                "record": record,
                "resolved": resolved,
                "productKey": product_key,
                "productId": info[0] if info else None,
                "quantity": quantity,
                "unitPrice": unit_price,
                "lineTotal": round(unit_price * quantity, 2),
            }
        )
    return lines


def _allocate_amount(total: float, lines: list[dict]) -> list[float]:
    if total <= 0 or not lines:
        return [0.0] * len(lines)
    subtotal_sum = sum(line["lineTotal"] for line in lines)
    if subtotal_sum <= 0:
        return [0.0] * len(lines)
    allocated = [round(total * (line["lineTotal"] / subtotal_sum), 2) for line in lines[:-1]]
    allocated.append(round(total - sum(allocated), 2))
    return allocated


def _process_sales_records(db: DbDependency, user, company, records: list[ImportRecord]) -> tuple[int, int]:
    product_index = _build_product_index(db, user.companyId)
    products_by_id = {
        product.id: product
        for product in db.query(Product).filter(Product.companyId == user.companyId).all()
    }
    category_names = {
        category.id: category.name
        for category in db.query(Category).filter(Category.companyId == user.companyId).all()
    }

    valid_records = [record for record in records if record.status == "valid"]
    groups: dict[str, list[ImportRecord]] = {}
    for record in valid_records:
        resolved = json.loads(record.rowData).get("resolved", {})
        invoice = (resolved.get("invoiceNumber") or "").strip()
        key = invoice or f"__auto__{record.id}"
        groups.setdefault(key, []).append(record)

    inserted = 0
    failed = 0
    for group_key, group_records in groups.items():
        lines = _build_sale_line_payloads(product_index, group_records)
        first_resolved = json.loads(group_records[0].rowData).get("resolved", {})

        if any(line["productId"] is None for line in lines):
            for record in group_records:
                record.status = "failed"
                record.message = "Product no longer exists"
            failed += len(group_records)
            continue

        subtotal_amount = round(sum(line["lineTotal"] for line in lines), 2)
        discount_amount = float(first_resolved.get("discountAmount") or 0)
        tax_amount = float(first_resolved.get("taxAmount") or 0)
        if discount_amount > subtotal_amount:
            for record in group_records:
                record.status = "failed"
                record.message = "Discount cannot exceed total product value"
            failed += len(group_records)
            continue
        total_amount = round(subtotal_amount - discount_amount + tax_amount, 2)

        try:
            customer_name, customer_id = _resolve_import_customer(
                db, user, {"customerEmail": first_resolved.get("customerEmail"), "customerName": first_resolved.get("customerName")}
            )
        except ValueError as exc:
            for record in group_records:
                record.status = "failed"
                record.message = str(exc)
            failed += len(group_records)
            continue

        sale_datetime = (
            _parse_sale_datetime(first_resolved["saleDateTime"])
            if first_resolved.get("saleDateTime")
            else datetime.now(timezone.utc)
        )
        transaction = SalesTransaction(
            companyId=user.companyId,
            createdBy=user.id,
            customerId=customer_id,
            customerName=customer_name,
            saleDateTime=sale_datetime,
            status="completed",
            salesChannel=first_resolved.get("salesChannel") or "In-Store",
            paymentMethod=first_resolved.get("paymentMethod") or "Cash",
            paymentStatus=first_resolved.get("paymentStatus") or "Paid",
            subtotalAmount=subtotal_amount,
            discountAmount=discount_amount,
            taxAmount=tax_amount,
            totalAmount=total_amount,
            createdAt=datetime.now(timezone.utc),
            updatedAt=datetime.now(timezone.utc),
        )
        try:
            with db.begin_nested():
                db.add(transaction)
                db.flush()
                invoice_number = (group_key if not group_key.startswith("__auto__") else "").strip()
                if invoice_number:
                    duplicate_invoice = (
                        db.query(SalesTransaction)
                        .filter(
                            SalesTransaction.companyId == user.companyId,
                            SalesTransaction.invoiceNumber == invoice_number,
                            SalesTransaction.id != transaction.id,
                        )
                        .first()
                    )
                    if duplicate_invoice:
                        raise ValueError(f"Duplicate invoice number already exists: {invoice_number}")
                    transaction.invoiceNumber = invoice_number
                else:
                    transaction.invoiceNumber = _next_company_invoice_number(db, user.companyId, sale_datetime)

                line_discounts = _allocate_amount(discount_amount, lines)
                line_taxes = _allocate_amount(tax_amount, lines)
                deltas: dict[int, int] = {}
                for line, line_discount, line_tax in zip(lines, line_discounts, line_taxes):
                    product = products_by_id.get(line["productId"])
                    category_id = product.categoryId if product else None
                    db.add(
                        SalesTransactionLine(
                            transactionId=transaction.id,
                            productId=line["productId"],
                            categoryIdSnapshot=category_id,
                            categoryNameSnapshot=category_names.get(category_id or 0),
                            quantity=line["quantity"],
                            unitPrice=line["unitPrice"],
                            discountAmount=line_discount,
                            taxAmount=line_tax,
                            lineTotal=round(line["lineTotal"] - line_discount + line_tax, 2),
                            productNameSnapshot=product.name if product else "",
                            skuSnapshot=product.sku if product else "",
                        )
                    )
                    deltas[line["productId"]] = deltas.get(line["productId"], 0) - line["quantity"]
                _apply_sales_stock_delta(
                    db,
                    user.companyId,
                    deltas,
                    company_name=company.name,
                    actor_email=user.email,
                    invoice_number=transaction.invoiceNumber,
                    movement_type="Sale",
                    sale_id=transaction.id,
                    actor_user_id=user.id,
                )
            for record in group_records:
                record.status = "imported"
                record.message = None
            inserted += 1
        except (HTTPException, ValueError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            for record in group_records:
                record.status = "failed"
                record.message = f"Could not import transaction: {detail}"
            failed += len(group_records)

    return inserted, failed


def confirm_import(batch_id: int, db: DbDependency, authorization: str | None = None) -> ImportConfirmResponse:
    user, company = _authorize_admin(db, authorization)
    batch = _load_pending_batch(db, user, batch_id)

    records = (
        db.query(ImportRecord)
        .filter(ImportRecord.batchId == batch.id)
        .order_by(ImportRecord.rowNumber.asc(), ImportRecord.id.asc())
        .all()
    )
    valid_records = [record for record in records if record.status == "valid"]

    batch.status = "processing"
    db.commit()

    try:
        inserted = 0
        failed = 0
        if batch.entityType == "products":
            inserted, failed = _process_product_records(db, user, valid_records)
            invalidate_forecast_cache(user.companyId)
        elif batch.entityType == "customers":
            inserted, failed = _process_customer_records(db, user, valid_records)
        else:
            inserted, failed = _process_sales_records(db, user, company, valid_records)
            invalidate_forecast_cache(user.companyId)
    except Exception:
        # Roll back every record/group inserted so far so an unexpected failure
        # never leaves a half-imported batch (no orphaned products, sales, or
        # stock deltas). The batch is then marked failed and that status is
        # committed. Its records remain as they were at validation time.
        db.rollback()
        batch.status = "failed"
        batch.completedAt = datetime.now(timezone.utc)
        db.commit()
        create_notification(
            db, user.companyId, message=f"Import failed for {batch.fileName}.",
            notification_type="import_failed", severity="error", target_role="admin",
        )
        db.commit()
        raise

    batch.status = "completed_with_errors" if failed > 0 else "completed"
    batch.insertedCount = inserted
    batch.failedCount = failed
    batch.completedAt = datetime.now(timezone.utc)
    db.commit()

    if batch.entityType == "sales":
        # Recompute derived customer metrics only after the batch is committed so
        # the derived counters are never persisted ahead of (or without) the sales.
        refresh_customer_metrics_for_company(db, user.companyId)

    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action=f"Data Import Completed:{batch.entityType}",
        entity_name=batch.fileName,
        ip_address="Unknown",
        browser="Unknown",
    )
    create_notification(
        db,
        user.companyId,
        message=f"Import completed for {batch.fileName}: {inserted} rows imported, {failed} failed.",
        notification_type="import_completed" if failed == 0 else "import_completed_with_errors",
        severity="warning" if failed else "success",
        target_role="admin",
    )
    db.commit()

    skipped = batch.invalidCount + batch.duplicateCount
    return ImportConfirmResponse(
        batchId=batch.id,
        entityType=batch.entityType,
        fileName=batch.fileName,
        status=batch.status,
        totalRows=batch.totalRows,
        insertedCount=inserted,
        updatedCount=0,
        failedCount=failed,
        invalidCount=batch.invalidCount,
        duplicateCount=batch.duplicateCount,
        skippedCount=skipped,
    )


# ---------------------------------------------------------------------------
# Import history
# ---------------------------------------------------------------------------

def _to_batch_response(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse(
        id=batch.id,
        entityType=batch.entityType or "",
        fileName=batch.fileName or "",
        totalRows=int(batch.totalRows or 0),
        validCount=int(batch.validCount or 0),
        invalidCount=int(batch.invalidCount or 0),
        duplicateCount=int(batch.duplicateCount or 0),
        insertedCount=int(batch.insertedCount or 0),
        updatedCount=int(batch.updatedCount or 0),
        failedCount=int(batch.failedCount or 0),
        status=batch.status or "pending",
        importedBy=batch.importedBy,
        createdAt=batch.createdAt.isoformat() if batch.createdAt else None,
        completedAt=batch.completedAt.isoformat() if batch.completedAt else None,
    )


def list_import_batches(db: DbDependency, authorization: str | None = None) -> list[ImportBatchResponse]:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    batches = (
        db.query(ImportBatch)
        .filter(ImportBatch.companyId == user.companyId)
        .order_by(ImportBatch.createdAt.desc(), ImportBatch.id.desc())
        .limit(100)
        .all()
    )
    return [_to_batch_response(batch) for batch in batches]


def get_import_batch_detail(batch_id: int, db: DbDependency, authorization: str | None = None) -> ImportBatchDetailResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    _ensure_admin(user)

    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id, ImportBatch.companyId == user.companyId).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    records = (
        db.query(ImportRecord)
        .filter(ImportRecord.batchId == batch.id)
        .order_by(ImportRecord.rowNumber.asc(), ImportRecord.id.asc())
        .all()
    )
    detail = ImportBatchDetailResponse(
        **_to_batch_response(batch).model_dump(),
        rows=[
            ImportRecordResponse(
                id=record.id,
                rowNumber=int(record.rowNumber or 0),
                status=record.status or "",
                message=record.message,
                rowData=json.loads(record.rowData) if record.rowData else {},
            )
            for record in records
        ],
    )
    return detail


# Best-effort mapping from a human-readable validation message to the CSV
# column it refers to. Used by the per-error endpoint to expose a structured
# { row, field, message } payload (mirrors the frontend validation response).
_FIELD_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("duplicate sku",), "sku"),
    (("sku", "product code", "item code"), "SKU"),
    (("product name",), "Product Name"),
    (("product", "not found by sku"), "SKU"),
    (("category",), "Category"),
    (("unit price", "price"), "Unit Price"),
    (("cost price",), "Cost Price"),
    (("stock quantity", "stock"), "Stock Quantity"),
    (("max stock",), "Max Stock Level"),
    (("status",), "Status"),
    (("name", "full name"), "Customer Name"),
    (("email",), "Email"),
    (("phone",), "Phone"),
    (("quantity", "qty"), "Quantity"),
    (("invoice",), "Invoice Number"),
    (("sale date", "date"), "Sale Date"),
    (("sales channel",), "Sales Channel"),
    (("payment",), "Payment"),
    (("discount",), "Discount Amount"),
    (("tax",), "Tax Amount"),
]


def _derive_error_field(message: str, resolved: dict) -> str | None:
    lowered = message.lower()
    for needles, field in _FIELD_HINTS:
        if any(needle in lowered for needle in needles):
            return field
    for key in ("sku", "name", "email", "phone", "categoryId", "quantity", "unitPrice", "saleDateTime", "invoiceNumber"):
        if key in resolved:
            return key
    return None


def get_import_errors(batch_id: int, db: DbDependency, authorization: str | None = None) -> ImportErrorsResponse:
    user, _company = _authorize_admin(db, authorization)
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id, ImportBatch.companyId == user.companyId).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    records = (
        db.query(ImportRecord)
        .filter(
            ImportRecord.batchId == batch.id,
            ImportRecord.status.in_(("invalid", "duplicate", "failed")),
        )
        .order_by(ImportRecord.rowNumber.asc(), ImportRecord.id.asc())
        .all()
    )

    errors: list[ImportErrorResponse] = []
    for record in records:
        resolved: dict = {}
        if record.rowData:
            try:
                resolved = (json.loads(record.rowData) or {}).get("resolved", {})
            except (json.JSONDecodeError, TypeError):
                resolved = {}
        message = record.message or "Row could not be imported"
        # Split multi-message fields so each validation failure is surfaced
        # individually, mirroring the per-row error messages.
        for part in message.split("; "):
            if not part:
                continue
            errors.append(
                ImportErrorResponse(
                    rowNumber=int(record.rowNumber or 0),
                    field=_derive_error_field(part, resolved),
                    message=part,
                    status=record.status or "",
                )
            )

    return ImportErrorsResponse(batchId=batch.id, totalErrors=len(errors), errors=errors)


def export_failed_records(batch_id: int, db: DbDependency, authorization: str | None = None) -> Response:
    user, _company = _authorize_admin(db, authorization)
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id, ImportBatch.companyId == user.companyId).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    records = (
        db.query(ImportRecord)
        .filter(
            ImportRecord.batchId == batch.id,
            ImportRecord.status.in_(("invalid", "duplicate", "failed")),
        )
        .order_by(ImportRecord.rowNumber.asc(), ImportRecord.id.asc())
        .all()
    )

    extra_headers: list[str] = []
    parsed_rows: list[tuple[dict[str, str], dict[str, object]]] = []
    for record in records:
        try:
            payload = json.loads(record.rowData) if record.rowData else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}
        raw_row = {str(key): str(value) for key, value in (payload.get("row") or {}).items()}
        for header in raw_row:
            if header not in extra_headers:
                extra_headers.append(header)
        parsed_rows.append(
            (
                raw_row,
                {
                    "RowNumber": int(record.rowNumber or 0),
                    "Status": record.status or "",
                    "Errors": record.message or "",
                },
            )
        )

    output = io.StringIO()
    fieldnames = ["RowNumber", "Status", "Errors", *extra_headers]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for raw_row, base_fields in parsed_rows:
        writer.writerow({**base_fields, **raw_row})

    file_name = f"import-{batch.id}-{batch.entityType}-issues.csv"
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


def delete_import_batch(batch_id: int, db: DbDependency, authorization: str | None = None) -> dict:
    user, company = _authorize_admin(db, authorization)

    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id, ImportBatch.companyId == user.companyId).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    file_name = batch.fileName
    db.query(ImportRecord).filter(ImportRecord.batchId == batch.id).delete()
    db.delete(batch)
    db.commit()
    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Data Import Deleted",
        entity_name=file_name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return {"message": "Import batch deleted"}
