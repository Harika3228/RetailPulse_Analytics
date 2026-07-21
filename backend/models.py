from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

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
    company = Column(String)
    entityName = Column(String)
    invoiceNumber = Column(String, index=True)
    productName = Column(String)
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
    unitOfMeasure = Column(String)
    price = Column(String)  # legacy compatibility
    status = Column(String, default="active")
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    productId = Column(Integer, index=True)
    productName = Column(String)
    message = Column(String)
    type = Column(String, index=True)
    isRead = Column(Integer, default=0)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class SalesTransaction(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    createdBy = Column(Integer, index=True)
    invoiceNumber = Column(String, index=True)
    customerName = Column(String)
    saleDateTime = Column("saleDate", DateTime, default=datetime.now(timezone.utc))
    salesChannel = Column(String)
    paymentMethod = Column(String)
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


Base.metadata.create_all(bind=engine)
