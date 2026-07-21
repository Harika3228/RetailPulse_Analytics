import re

from pydantic import BaseModel, EmailStr, field_validator, model_validator


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: dict


class TokenData(BaseModel):
    email: str | None = None
    company_id: int | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str
    confirmPassword: str


class RegisterRequest(BaseModel):
    companyName: str
    industry: str
    companyEmail: EmailStr
    companyAddress: str
    companyPhone: str
    ownerName: str
    ownerEmail: EmailStr
    password: str
    confirmPassword: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return value

    @field_validator("companyName", "ownerName")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field is required")
        return value


# ---------------------------------------------------------------------------
# User / dashboard schemas
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    company: str
    lastLogin: str
    accountStatus: str


class DashboardResponse(BaseModel):
    companyName: str
    metrics: dict
    visibility: list[str]


class ProductSummaryResponse(BaseModel):
    totalProducts: int
    activeProducts: int
    inactiveProducts: int
    totalCategories: int


class SalesDashboardSummaryResponse(BaseModel):
    totalSales: int
    totalRevenue: float
    totalOrders: int
    averageOrderValue: float


class InventoryDashboardSummaryResponse(BaseModel):
    totalProducts: int
    totalInventoryQuantity: int
    lowStockProducts: int
    outOfStockProducts: int


class AuditLogResponse(BaseModel):
    id: int
    company: str
    entity: str | None = None
    invoiceNumber: str | None = None
    productName: str | None = None
    action: str
    performedBy: str
    time: str


class NotificationResponse(BaseModel):
    id: int
    productId: int
    productName: str
    message: str
    type: str
    createdAt: str


# ---------------------------------------------------------------------------
# Category schemas
# ---------------------------------------------------------------------------

class CategoryRequest(BaseModel):
    name: str
    description: str | None = None
    status: str | None = "active"


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    status: str
    productCount: int


# ---------------------------------------------------------------------------
# Product schemas
# ---------------------------------------------------------------------------

class ProductRequest(BaseModel):
    name: str
    sku: str
    categoryId: int
    brand: str
    description: str | None = None
    unitPrice: float
    costPrice: float
    stockQuantity: int | None = None
    initialStockQuantity: int | None = None
    unitOfMeasure: str
    status: str | None = "active"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Product name is required")
        return normalized

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("SKU is required")
        if not re.fullmatch(r"[A-Z0-9-]+", normalized):
            raise ValueError("SKU must contain only letters, numbers, and hyphens")
        return normalized

    @field_validator("categoryId")
    @classmethod
    def validate_category_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Category is required")
        return value

    @field_validator("unitPrice")
    @classmethod
    def validate_unit_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Unit price must be greater than zero")
        return value

    @field_validator("stockQuantity", "initialStockQuantity")
    @classmethod
    def validate_stock_quantity(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("Stock quantity cannot be negative")
        return value

    @model_validator(mode="after")
    def validate_cost_not_greater_than_unit(self):
        if self.costPrice > self.unitPrice:
            raise ValueError("Cost price cannot exceed unit price")
        resolved_stock = self.stockQuantity if self.stockQuantity is not None else self.initialStockQuantity
        if resolved_stock is None:
            raise ValueError("Stock quantity is required")
        self.stockQuantity = resolved_stock
        self.initialStockQuantity = resolved_stock
        return self


class ProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    categoryId: int
    brand: str
    description: str | None = None
    unitPrice: float
    costPrice: float
    stockQuantity: int
    initialStockQuantity: int
    unitOfMeasure: str
    status: str
    createdAt: str | None = None
    updatedAt: str | None = None


class ProductStatusRequest(BaseModel):
    status: str


class InventoryResponse(BaseModel):
    productId: int
    productName: str
    sku: str
    categoryId: int | None = None
    categoryName: str | None = None
    brand: str
    currentStock: int
    reservedStock: int
    availableStock: int
    reorderLevel: int
    stockStatus: str
    status: str
    updatedAt: str | None = None


class InventoryMovementResponse(BaseModel):
    id: str
    productId: int
    productName: str
    sku: str
    movementType: str
    previousQuantity: int | None = None
    updatedQuantity: int | None = None
    quantityChanged: int | None = None
    reason: str | None = None
    user: str | None = None
    reference: str | None = None
    timestamp: str | None = None


class StockAdjustmentRequest(BaseModel):
    adjustmentType: str
    quantity: int
    reason: str
    remarks: str | None = None

    @field_validator("adjustmentType")
    @classmethod
    def validate_adjustment_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"stock_in", "stock_out", "manual_adjustment"}:
            raise ValueError("Adjustment type must be stock_in, stock_out, or manual_adjustment")
        return normalized

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Quantity must be greater than zero")
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Reason is required")
        return normalized


class StockAdjustmentResponse(BaseModel):
    id: int
    productId: int
    productName: str
    sku: str
    adjustmentType: str
    quantity: int
    reason: str
    remarks: str | None = None
    adjustedBy: str
    adjustmentDate: str | None = None


# ---------------------------------------------------------------------------
# Sales schemas
# ---------------------------------------------------------------------------

class SalesLineRequest(BaseModel):
    productId: int
    quantity: int
    unitPrice: float | None = None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Quantity must be greater than 0")
        return value

    @field_validator("unitPrice")
    @classmethod
    def validate_unit_price(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("Unit price must be greater than zero")
        return value


class SalesTransactionRequest(BaseModel):
    lines: list[SalesLineRequest] | None = None
    productId: int | None = None
    quantity: int | None = None
    unitPrice: float | None = None
    customerName: str | None = None
    saleDateTime: str | None = None
    salesChannel: str | None = None
    paymentMethod: str | None = None
    discountAmount: float | None = 0
    taxAmount: float | None = 0

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Quantity must be greater than 0")
        return value

    @field_validator("discountAmount", "taxAmount")
    @classmethod
    def validate_non_negative_amounts(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Amounts cannot be negative")
        return value


class SalesSelectableProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    categoryId: int
    categoryName: str
    brand: str
    unitPrice: float
    stockQuantity: int
    status: str


class SalesLineResponse(BaseModel):
    productId: int
    productName: str
    sku: str
    categoryId: int
    categoryName: str
    quantity: int
    unitPrice: float
    lineTotal: float
    remainingStock: int | None = None


class SalesTransactionResponse(BaseModel):
    transactionId: int
    invoiceNumber: str
    companyId: int
    createdBy: int
    customerName: str | None = None
    saleDateTime: str
    salesChannel: str | None = None
    paymentMethod: str | None = None
    subtotalAmount: float
    discountAmount: float
    taxAmount: float
    totalAmount: float
    createdAt: str
    updatedAt: str | None = None
    lines: list[SalesLineResponse]
