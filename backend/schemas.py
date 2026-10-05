import re
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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


class AnalyticsDashboardResponse(BaseModel):
    totalRevenue: float
    totalOrders: int
    totalProductsSold: int
    averageOrderValue: float
    totalDiscount: float
    totalTax: float
    totalInventoryValue: float
    lowStockProducts: int
    outOfStockProducts: int
    totalCategories: int
    revenueTrend: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    salesTrend: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    orderTrend: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    topSellingProducts: list[dict[str, Any]] = Field(default_factory=list)
    topPerformingCategories: list[dict[str, Any]] = Field(default_factory=list)
    salesByPaymentMethod: list[dict[str, Any]] = Field(default_factory=list)
    salesBySalesChannel: list[dict[str, Any]] = Field(default_factory=list)
    salesByPaymentStatus: list[dict[str, Any]] = Field(default_factory=list)
    ordersBySalesChannel: list[dict[str, Any]] = Field(default_factory=list)
    ordersByPaymentMethod: list[dict[str, Any]] = Field(default_factory=list)
    inventoryDistributionByCategory: list[dict[str, Any]] = Field(default_factory=list)
    stockStatusSummary: dict[str, int] = Field(default_factory=dict)
    topLowStockProducts: list[dict[str, Any]] = Field(default_factory=list)
    outOfStockProductDetails: list[dict[str, Any]] = Field(default_factory=list)
    inventoryValueByCategory: list[dict[str, Any]] = Field(default_factory=list)
    topCustomersByRevenue: list[dict[str, Any]] = Field(default_factory=list)
    recentCustomers: list[dict[str, Any]] = Field(default_factory=list)
    customerGrowthTrend: list[dict[str, Any]] = Field(default_factory=list)
    customerRevenueContribution: list[dict[str, Any]] = Field(default_factory=list)


class AuditLogResponse(BaseModel):
    id: int
    companyId: int | None = None
    userId: int | None = None
    resourceType: str | None = None
    resourceId: str | None = None
    description: str
    ipAddress: str
    userAgent: str
    createdAt: str
    status: str
    company: str
    entity: str | None = None
    invoiceNumber: str | None = None
    productName: str | None = None
    action: str
    performedBy: str
    time: str


class TopProductResponse(BaseModel):
    name: str
    sku: str = ""
    quantity: int
    revenue: float


class TopCustomerResponse(BaseModel):
    name: str
    orders: int
    totalSpend: float
    averageOrderValue: float


class SalesAnalyticsSummaryResponse(BaseModel):
    totalRevenue: float
    totalOrders: int
    totalProductsSold: int
    averageOrderValue: float
    totalDiscount: float
    totalTax: float


class SalesAnalyticsTrendResponse(BaseModel):
    revenueTrend: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    salesTrend: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    orderTrend: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class SalesAnalyticsPaymentMethodResponse(BaseModel):
    paymentMethods: list[dict[str, Any]] = Field(default_factory=list)
    totalRevenue: float
    totalOrders: int


class NotificationResponse(BaseModel):
    id: int
    title: str
    productId: int
    productName: str
    message: str
    type: str
    severity: str = "info"
    priority: str = "low"
    resourceType: str | None = None
    resourceId: str | None = None
    isRead: bool = False
    readAt: str | None = None
    targetRole: str | None = None
    createdAt: str


class ScheduledReportRequest(BaseModel):
    name: str
    reportType: str
    filters: dict[str, Any] = Field(default_factory=dict)
    frequency: str
    executionTime: str
    recipients: list[EmailStr] = Field(default_factory=list)
    exportFormat: str = "csv"
    isActive: bool = True


class ScheduledReportResponse(BaseModel):
    id: int
    name: str
    reportType: str
    filters: dict[str, Any]
    frequency: str
    executionTime: str
    recipients: list[str]
    exportFormat: str
    isActive: bool
    lastGeneratedAt: str | None = None
    lastStatus: str
    lastError: str | None = None
    nextRunAt: str | None = None
    createdAt: str


class ReportHistoryRequest(BaseModel):
    reportType: str
    filters: dict[str, Any] = Field(default_factory=dict)
    exportFormat: str = "table"
    rowCount: int = 0
    status: str = "completed"
    errorMessage: str | None = None


class ReportHistoryResponse(BaseModel):
    id: int
    reportType: str
    filters: dict[str, Any]
    exportFormat: str
    status: str
    rowCount: int
    errorMessage: str | None = None
    generatedAt: str
    generatedByUserId: int
    generatedBy: str


class DataQualityIssue(BaseModel):
    id: str
    severity: str
    domain: str
    message: str
    resourceType: str
    resourceId: str
    status: str = "unresolved"
    issueType: str
    detectedAt: str
    resolution: str | None = None
    resolvedByUserId: int | None = None
    resolvedAt: str | None = None
    previousStatus: str | None = None
    statusUpdatedAt: str | None = None


class DataQualityResponse(BaseModel):
    totalRecordsChecked: int
    validRecords: int
    warningRecords: int
    errorRecords: int
    unresolvedIssues: int
    lastReconciliationAt: str
    issues: list[DataQualityIssue] = Field(default_factory=list)


class DataQualityIssueUpdate(BaseModel):
    status: str
    resolution: str | None = None


class ReconciliationHistoryResponse(BaseModel):
    id: int
    startedAt: str
    completedAt: str | None = None
    triggeredBy: str
    recordsChecked: int
    issuesDetected: int
    issuesResolved: int
    failedChecks: int
    status: str
    errorMessage: str | None = None


class CustomerRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    dateOfBirth: str | None = None
    gender: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postalCode: str | None = None
    customerType: str | None = None
    preferredSalesChannel: str | None = None
    status: str | None = "active"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', stripped):
            raise ValueError("Invalid email format")
        return stripped

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        digits = re.sub(r"\D", "", stripped)
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return stripped


class CustomerResponse(BaseModel):
    id: int
    customerId: str | None = None
    name: str
    email: str
    phone: str | None = None
    dateOfBirth: str | None = None
    gender: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postalCode: str | None = None
    customerType: str | None = None
    preferredSalesChannel: str | None = None
    status: str
    segment: str | None = None
    totalSpend: float
    purchaseCount: int
    lifetimeRevenue: float
    totalOrders: int
    averageOrderValue: float
    lastPurchase: str | None = None
    favoriteCategory: str | None = None
    favoriteProduct: str | None = None
    purchaseFrequency: str | None = None
    recentOrders: list[dict[str, Any]] = Field(default_factory=list)
    recentPurchases: list[dict[str, Any]] = Field(default_factory=list)
    recentPayments: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    lastPurchaseDate: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class CustomerStatusRequest(BaseModel):
    status: str


class CustomerAnalyticsResponse(BaseModel):
    totalCustomers: int
    activeCustomers: int
    inactiveCustomers: int
    newCustomersThisMonth: int
    returningCustomers: int
    averageCustomerSpend: float
    totalRevenueGenerated: float
    averagePurchaseFrequency: float
    customerTypeBreakdown: dict[str, int] = Field(default_factory=dict)
    preferredSalesChannelBreakdown: dict[str, int] = Field(default_factory=dict)
    customerGrowthTrend: list[dict[str, Any]] = Field(default_factory=list)
    newVsReturningCustomers: list[dict[str, Any]] = Field(default_factory=list)
    revenueByCustomerType: list[dict[str, Any]] = Field(default_factory=list)
    topCustomersByRevenue: list[dict[str, Any]] = Field(default_factory=list)
    customerPurchaseFrequency: list[dict[str, Any]] = Field(default_factory=list)
    customerDistributionByLocation: list[dict[str, Any]] = Field(default_factory=list)
    monthlyCustomerAcquisition: list[dict[str, Any]] = Field(default_factory=list)
    customerSpendingDistribution: list[dict[str, Any]] = Field(default_factory=list)
    segmentationSummary: list[dict[str, Any]] = Field(default_factory=list)
    customersWithPurchases: int
    recentCustomers: list[dict[str, Any]] = Field(default_factory=list)


class CustomerPurchaseHistoryResponse(BaseModel):
    customerId: int
    totalOrders: int
    totalRevenueGenerated: float
    totalQuantityPurchased: int
    averageOrderValue: float
    firstPurchaseDate: str | None = None
    lastPurchaseDate: str | None = None
    mostFrequentlyPurchasedProducts: list[dict[str, Any]] = Field(default_factory=list)
    recentTransactions: list[dict[str, Any]] = Field(default_factory=list)


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
    maxStockLevel: int | None = None
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
    maxStockLevel: int | None = None
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
    riskClassification: str = "healthy"
    recommendation: str = "Stock Level Healthy"
    predictedDemand: float = 0.0
    growthRate: float = 0.0
    forecastAccuracy: float = 0.0
    forecastPeriod: str = "Next 30 Days"
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
    customerId: int | None = None
    customerName: str | None = None
    saleDateTime: str | None = None
    salesChannel: str | None = None
    paymentMethod: str | None = None
    paymentStatus: str | None = None
    notes: str | None = None
    discountAmount: float | None = 0
    taxAmount: float | None = 0

    @field_validator("customerId")
    @classmethod
    def validate_customer_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Customer is required")
        return value

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


class SalesSelectableCustomerResponse(BaseModel):
    id: int
    name: str
    email: str = ""
    phone: str | None = None


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
    customerId: int | None = None
    customerName: str | None = None
    saleDateTime: str
    status: str = "completed"
    salesChannel: str | None = None
    paymentMethod: str | None = None
    paymentStatus: str | None = None
    notes: str | None = None
    salesperson: str | None = None
    subtotalAmount: float
    discountAmount: float
    taxAmount: float
    totalAmount: float
    createdAt: str
    updatedAt: str | None = None
    lines: list[SalesLineResponse]


class StockMovementResponse(BaseModel):
    id: int
    productId: int
    productName: str
    sku: str
    movementType: str
    previousQuantity: int
    updatedQuantity: int
    quantityChanged: int
    reference: str | None = None
    saleId: int | None = None
    actor: str | None = None
    timestamp: str | None = None


class ForecastPoint(BaseModel):
    month: str
    historical: float
    forecast: float


class ForecastSummaryResponse(BaseModel):
    totalProducts: int
    forecastedDemand: float
    averageMonthlySales: float
    trendGrowth: float
    forecastPeriod: str = "Next 30 Days"
    forecastWindowDays: int = 30
    forecastPoints: list[ForecastPoint] = Field(default_factory=list)


class ForecastProductResponse(BaseModel):
    id: int
    name: str
    categoryName: str
    currentStock: int
    historicalDemand: float
    forecastedDemand: float
    forecastPeriod: str = "Next 30 Days"
    confidenceLevel: float
    forecastPoints: list[ForecastPoint] = Field(default_factory=list)
    movingAverage: float = 0.0
    weightedMovingAverage: float = 0.0
    averageDailyDemand: float = 0.0
    daysOfStockRemaining: float = 0.0
    stockGap: float = 0.0
    risk: str = "safe"
    recommendation: str = "Stock Level Adequate"


class ForecastCategoryResponse(BaseModel):
    name: str
    totalHistoricalSales: float
    predictedDemand: float
    expectedGrowthPercentage: float
    forecastPoints: list[ForecastPoint] = Field(default_factory=list)


class ForecastAccuracyResponse(BaseModel):
    accuracy: float
    totalObservations: int
    bias: float


class DemandForecastDetailResponse(BaseModel):
    productId: int
    productName: str
    sku: str
    categoryName: str
    currentStock: int
    movingAverage: float
    weightedMovingAverage: float
    averageDailyDemand: float
    forecastedDemand: float
    daysOfStockRemaining: float
    stockGap: float
    risk: str
    recommendation: str
    forecastPeriod: str
    forecastWindowDays: int


# ---------------------------------------------------------------------------
# Inventory forecast / smart replenishment schemas
# ---------------------------------------------------------------------------

class InventoryForecastItemResponse(BaseModel):
    productId: int
    productName: str
    sku: str
    categoryId: int | None = None
    categoryName: str | None = None
    brand: str
    currentStock: int
    averageDailySales: float
    forecastedDemand: float
    daysOfStockRemaining: float
    leadTime: int = 4
    reorderPoint: int
    safetyStock: int = 0
    maxStockLevel: int | None = None
    recommendedReorderQty: int
    stockRisk: str
    riskClassification: str = "healthy"
    reorderRequired: bool = False
    recommendation: str


class InventoryForecastSummaryResponse(BaseModel):
    totalProducts: int
    reorderRequiredCount: int = 0
    outOfStockCount: int
    stockoutRiskCount: int
    lowStockCount: int
    healthyCount: int
    overstockCount: int
    totalReorderQty: int
    items: list[InventoryForecastItemResponse]


class ForecastSeriesPoint(BaseModel):
    date: str
    demand: float


class ForecastSeriesResponse(BaseModel):
    productId: int
    productName: str
    historical: list[ForecastSeriesPoint] = Field(default_factory=list)
    forecast: list[ForecastSeriesPoint] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Inventory recommendation schemas
# ---------------------------------------------------------------------------

class InventoryRecommendationItem(BaseModel):
    productId: int
    productName: str
    sku: str
    categoryId: int | None = None
    categoryName: str | None = None
    brand: str
    currentStock: int
    averageDailySales: float
    forecastedDemand: float
    daysOfStockRemaining: float
    leadTime: int = 4
    reorderPoint: int
    safetyStock: int = 0
    maxStockLevel: int | None = None
    recommendedReorderQty: int
    stockRisk: str
    riskClassification: str = "healthy"
    reorderRequired: bool = False
    recommendation: str
    actionSeverity: str = "ok"
    actionMessage: str = ""


class InventoryRecommendationSummary(BaseModel):
    totalProducts: int
    reorderRequiredCount: int = 0
    actionRequiredCount: int
    reviewNeededCount: int
    optimalCount: int
    stockoutRiskCount: int = 0
    overstockCount: int = 0
    healthyCount: int = 0
    totalReorderQty: int
    estimatedReorderCost: float = 0.0
    items: list[InventoryRecommendationItem]


class WeeklyDemandPoint(BaseModel):
    weekStart: str
    sales: float


class TrendAnalysis(BaseModel):
    direction: str = "stable"
    percentageChange: float = 0.0
    averageMonthlySales: float = 0.0
    peakMonth: str | None = None
    peakSales: float = 0.0


class ProductRecommendationDetail(BaseModel):
    productId: int
    productName: str
    sku: str
    categoryId: int | None = None
    categoryName: str | None = None
    brand: str
    currentStock: int
    averageDailySales: float
    forecastedDemand: float
    daysOfStockRemaining: float
    leadTime: int = 4
    reorderPoint: int
    safetyStock: int = 0
    maxStockLevel: int | None = None
    recommendedReorderQty: int
    stockRisk: str
    riskClassification: str = "healthy"
    reorderRequired: bool = False
    recommendation: str
    actionSeverity: str = "ok"
    actionMessage: str = ""
    costPrice: float = 0.0
    unitPrice: float = 0.0
    estimatedReorderCost: float = 0.0
    weeklyDemand: list[WeeklyDemandPoint] = Field(default_factory=list)
    trendAnalysis: TrendAnalysis = Field(default_factory=TrendAnalysis)
    monthlyHistory: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Data import / integration schemas
# ---------------------------------------------------------------------------

class ImportPreviewRow(BaseModel):
    rowNumber: int
    status: str  # valid / invalid / duplicate
    messages: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    rawData: dict[str, Any] = Field(default_factory=dict)


class ImportPreviewResponse(BaseModel):
    batchId: int
    entityType: str
    fileName: str
    totalRows: int
    validRows: int
    invalidRows: int
    duplicateRows: int
    columns: list[str] = Field(default_factory=list)
    columnMapping: dict[str, str] = Field(default_factory=dict)
    rows: list[ImportPreviewRow] = Field(default_factory=list)


class ImportRecordResponse(BaseModel):
    id: int
    rowNumber: int
    status: str
    message: str | None = None
    rowData: dict[str, Any] = Field(default_factory=dict)


class ImportErrorResponse(BaseModel):
    rowNumber: int
    field: str | None = None
    recordData: dict[str, Any] = Field(default_factory=dict)
    errorType: str
    message: str
    status: str


class ImportErrorsResponse(BaseModel):
    batchId: int
    totalErrors: int
    errors: list[ImportErrorResponse] = Field(default_factory=list)


class ImportBatchResponse(BaseModel):
    id: int
    entityType: str
    fileName: str
    totalRows: int
    validCount: int
    invalidCount: int
    duplicateCount: int
    insertedCount: int
    updatedCount: int
    failedCount: int
    processedCount: int = 0
    progressPercent: int = 0
    cancelRequested: bool = False
    failureMessage: str | None = None
    status: str
    importedBy: str | None = None
    createdAt: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    durationSeconds: float | None = None


class ImportBatchDetailResponse(ImportBatchResponse):
    rows: list[ImportRecordResponse] = Field(default_factory=list)


class ImportConfirmResponse(BaseModel):
    batchId: int
    entityType: str
    fileName: str
    status: str
    totalRows: int
    insertedCount: int
    updatedCount: int
    failedCount: int
    invalidCount: int
    duplicateCount: int
    skippedCount: int
    processedCount: int = 0
    progressPercent: int = 0
    importedBy: str | None = None
    createdAt: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    durationSeconds: float | None = None
