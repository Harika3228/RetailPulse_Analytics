from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint, inspect, text

from backend.database import Base, engine


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    industry = Column(String)
    email = Column(String, unique=True, index=True)
    address = Column(String)
    phone = Column(String)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String)
    status = Column(String, default="active")
    lastLogin = Column(DateTime, default=datetime.now(timezone.utc))
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    customerId = Column(String, index=True)
    name = Column(String, index=True)
    email = Column(String, index=True)
    phone = Column(String)
    dateOfBirth = Column(String)
    gender = Column(String)
    address = Column(String)
    city = Column(String)
    state = Column(String)
    country = Column(String)
    postalCode = Column(String)
    customerType = Column(String, default="retail")
    preferredSalesChannel = Column(String, default="offline")
    status = Column(String, default="active")
    segment = Column(String, default="new_customer")
    totalSpend = Column(Float, default=0)
    purchaseCount = Column(Integer, default=0)
    firstPurchaseDate = Column(DateTime)
    lastPurchaseDate = Column(DateTime)
    isDeleted = Column(Integer, default=0)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer)
    token = Column(String, unique=True, index=True)
    expiresAt = Column(DateTime)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    userId = Column(Integer, index=True)
    resourceType = Column(String)
    resourceId = Column(String)
    description = Column(String)
    userAgent = Column(String)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc), index=True)
    status = Column(String, default="success")
    company = Column(String)
    entityName = Column(String)
    invoiceNumber = Column(String, index=True)
    productName = Column(String)
    categoryName = Column(String)
    forecastPeriod = Column(String)
    user = Column(String)
    action = Column(String)
    ipAddress = Column(String)
    browser = Column(String)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    name = Column(String, index=True)
    description = Column(String)
    status = Column(String, default="active")
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    categoryId = Column(Integer, index=True)
    sku = Column(String, index=True)
    name = Column(String, index=True)
    brand = Column(String, index=True)
    description = Column(String)
    unitPrice = Column(Float)
    costPrice = Column(Float)
    stockQuantity = Column(Integer)
    initialStockQuantity = Column(Integer)
    maxStockLevel = Column(Integer, nullable=True)
    unitOfMeasure = Column(String)
    price = Column(String)  # legacy compatibility
    status = Column(String, default="active")
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    userId = Column(Integer, index=True)
    productId = Column(Integer, index=True)
    productName = Column(String)
    title = Column(String)
    message = Column(String)
    type = Column(String, index=True)
    resourceType = Column(String)
    resourceId = Column(String)
    targetRole = Column(String, index=True)
    severity = Column(String, default="info")
    priority = Column(String, default="low", index=True)
    alertKey = Column(String, index=True)
    resolvedAt = Column(DateTime)
    isRead = Column(Integer, default=0)
    readAt = Column(DateTime)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class DemandForecast(Base):
    __tablename__ = "demand_forecasts"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    productId = Column(Integer, index=True)
    categoryId = Column(Integer, index=True)
    forecastPeriod = Column(String, index=True)
    predictedDemand = Column(Float, default=0)
    confidenceScore = Column(Float, default=0)
    generatedAt = Column(DateTime, default=datetime.now(timezone.utc))


class ForecastHistory(Base):
    __tablename__ = "forecast_history"
    id = Column(Integer, primary_key=True, index=True)
    forecastId = Column(Integer, index=True)
    historicalSales = Column(Float, default=0)
    prediction = Column(Float, default=0)
    accuracy = Column(Float, default=0)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class SalesTransaction(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    createdBy = Column(Integer, index=True)
    invoiceNumber = Column(String, index=True)
    customerId = Column(Integer, index=True, nullable=True)
    customerName = Column(String)
    saleDateTime = Column("saleDate", DateTime, default=datetime.now(timezone.utc))
    status = Column(String, default="completed")
    salesChannel = Column(String)
    paymentMethod = Column(String)
    paymentStatus = Column(String, default="Paid")
    notes = Column(String)
    subtotalAmount = Column(Float, default=0)
    discountAmount = Column(Float, default=0)
    taxAmount = Column(Float, default=0)
    totalAmount = Column(Float, default=0)
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class SalesTransactionLine(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True)
    transactionId = Column("saleId", Integer, index=True)
    productId = Column(Integer, index=True)
    categoryIdSnapshot = Column("categoryId", Integer, index=True)
    categoryNameSnapshot = Column(String)
    quantity = Column(Integer)
    unitPrice = Column(Float)
    discountAmount = Column("discount", Float, default=0)
    taxAmount = Column("tax", Float, default=0)
    lineTotal = Column("total", Float)
    productNameSnapshot = Column(String)
    skuSnapshot = Column(String, index=True)
    remainingStockSnapshot = Column(Integer)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    productId = Column(Integer, index=True)
    adjustmentType = Column(String, index=True)
    quantity = Column(Integer)
    reason = Column(String)
    remarks = Column(String)
    adjustedBy = Column(String)
    adjustedByUserId = Column(Integer, nullable=True)
    adjustmentDate = Column(DateTime, default=datetime.now(timezone.utc))
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    productId = Column(Integer, index=True)
    productName = Column(String)
    sku = Column(String, index=True)
    movementType = Column(String, index=True)
    previousQuantity = Column(Integer)
    updatedQuantity = Column(Integer)
    quantityChanged = Column(Integer)
    reference = Column(String)
    saleId = Column(Integer, index=True, nullable=True)
    actor = Column(String)
    actorUserId = Column(Integer, nullable=True)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    entityType = Column(String, index=True)
    fileName = Column(String)
    totalRows = Column(Integer, default=0)
    validCount = Column(Integer, default=0)
    invalidCount = Column(Integer, default=0)
    duplicateCount = Column(Integer, default=0)
    insertedCount = Column(Integer, default=0)
    updatedCount = Column(Integer, default=0)
    failedCount = Column(Integer, default=0)
    processedCount = Column(Integer, default=0)
    cancelRequested = Column(Integer, default=0)
    failureMessage = Column(String)
    status = Column(String, default="uploaded", index=True)
    importedBy = Column(String)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))
    startedAt = Column(DateTime)
    completedAt = Column(DateTime)
    durationSeconds = Column(Float)


class ImportRecord(Base):
    __tablename__ = "import_records"
    id = Column(Integer, primary_key=True, index=True)
    batchId = Column(Integer, index=True)
    companyId = Column(Integer, index=True)
    rowNumber = Column(Integer)
    status = Column(String, index=True)  # valid / invalid / duplicate / imported / failed
    message = Column(String)
    rowData = Column(String)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    createdByUserId = Column(Integer, index=True)
    name = Column(String)
    reportType = Column(String, index=True)
    filters = Column(String, default="{}")
    frequency = Column(String, index=True)
    executionTime = Column(String)
    recipients = Column(String, default="[]")
    exportFormat = Column(String, default="csv")
    isActive = Column(Integer, default=1, index=True)
    lastGeneratedAt = Column(DateTime)
    lastStatus = Column(String, default="not_run")
    lastError = Column(String)
    nextRunAt = Column(DateTime)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ReportHistory(Base):
    __tablename__ = "report_history"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    generatedByUserId = Column(Integer, index=True)
    reportType = Column(String, index=True)
    filters = Column(String, default="{}")
    exportFormat = Column(String, default="table")
    status = Column(String, default="completed", index=True)
    rowCount = Column(Integer, default=0)
    errorMessage = Column(String)
    generatedAt = Column(DateTime, default=datetime.now(timezone.utc), index=True)


class QualityIssue(Base):
    __tablename__ = "quality_issues"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    issueKey = Column(String, index=True)
    issueType = Column(String, index=True)
    severity = Column(String, index=True)
    affectedModule = Column(String, index=True)
    affectedRecordType = Column(String)
    affectedRecordId = Column(String)
    description = Column(String)
    detectedAt = Column(DateTime, default=datetime.now(timezone.utc), index=True)
    status = Column(String, default="open", index=True)
    resolution = Column(String)
    resolvedAt = Column(DateTime)
    resolvedByUserId = Column(Integer, index=True)
    previousStatus = Column(String)
    statusUpdatedAt = Column(DateTime)


class ReconciliationExecution(Base):
    __tablename__ = "reconciliation_executions"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    startedAt = Column(DateTime, default=datetime.now(timezone.utc), index=True)
    completedAt = Column(DateTime)
    triggeredByUserId = Column(Integer, index=True)
    recordsChecked = Column(Integer, default=0)
    issuesDetected = Column(Integer, default=0)
    issuesResolved = Column(Integer, default=0)
    failedChecks = Column(Integer, default=0)
    status = Column(String, default="running", index=True)
    errorMessage = Column(String)


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    forecastType = Column(String, index=True)
    period = Column(String, default="30d")
    generatedAt = Column(DateTime, default=datetime.now(timezone.utc))
    payload = Column(String)


class ApprovalRequestRecord(Base):
    __tablename__ = "approval_requests"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    requesterId = Column(Integer, index=True)
    requestType = Column(String, index=True)
    title = Column(String)
    description = Column(String)
    reason = Column(String)
    relatedRecord = Column(String)
    requestedChanges = Column(String, default="{}")
    currentValues = Column(String, default="{}")
    assignedApproverRole = Column(String, default="admin", index=True)
    details = Column(String, default="{}")
    status = Column(String, default="pending_approval", index=True)
    reviewerId = Column(Integer, nullable=True, index=True)
    reviewerComment = Column(String)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc), index=True)
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc))


class WorkflowConfiguration(Base):
    __tablename__ = "workflow_configurations"
    __table_args__ = (UniqueConstraint("companyId", "requestType", name="uq_workflow_configuration_company_type"),)
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    requestType = Column(String, index=True)
    approverRole = Column(String, default="admin")
    approvalRequired = Column(Integer, default=1)
    isActive = Column(Integer, default=1)
    allowSelfApproval = Column(Integer, default=0)
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ApprovalHistoryRecord(Base):
    __tablename__ = "approval_history"
    id = Column(Integer, primary_key=True, index=True)
    requestId = Column(Integer, index=True)
    companyId = Column(Integer, index=True)
    actorId = Column(Integer, index=True)
    action = Column(String, index=True)
    comment = Column(String)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc), index=True)


Base.metadata.create_all(bind=engine)


def ensure_customer_schema() -> None:
    inspector = inspect(engine)
    if "customers" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "customerId" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE customers ADD COLUMN customerId VARCHAR"))

    with engine.begin() as connection:
        connection.execute(text("UPDATE customers SET customerId = 'CUST-' || id WHERE customerId IS NULL OR customerId = ''"))


ensure_customer_schema()
