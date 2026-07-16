import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import bcrypt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from sqlalchemy import Column, Integer, String, DateTime, Float, asc, create_engine, desc, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

SECRET_KEY = os.environ.get("SECRET_KEY", "retailpulse-dev-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "retailpulse.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    # Expecting a full SQLAlchemy compatible URL (e.g. postgres://...)
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
    # legacy compatibility for earlier schema
    price = Column(String)
    status = Column(String, default="active")
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))
    updatedAt = Column(DateTime, default=datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SalesTransaction(Base):
    __tablename__ = "sales_transactions"
    id = Column(Integer, primary_key=True, index=True)
    companyId = Column(Integer, index=True)
    createdBy = Column(Integer, index=True)
    totalAmount = Column(Float, default=0)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))


class SalesTransactionLine(Base):
    __tablename__ = "sales_transaction_lines"
    id = Column(Integer, primary_key=True, index=True)
    transactionId = Column(Integer, index=True)
    productId = Column(Integer, index=True)
    quantity = Column(Integer)
    unitPrice = Column(Float)
    lineTotal = Column(Float)
    productNameSnapshot = Column(String)
    skuSnapshot = Column(String, index=True)
    createdAt = Column(DateTime, default=datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)


def migrate_products_table_for_company_sku_uniqueness(connection) -> None:
    """SQLite migration: remove legacy global UNIQUE(sku) and enforce UNIQUE(companyId, sku)."""
    if engine.dialect.name != "sqlite":
        return

    index_rows = connection.execute(text("PRAGMA index_list('products')")).fetchall()
    has_global_unique_sku = False
    for row in index_rows:
        # row format: (seq, name, unique, origin, partial)
        index_name = row[1]
        is_unique = row[2] == 1
        if not is_unique:
            continue
        index_cols_rows = connection.execute(text(f"PRAGMA index_info('{index_name}')")).fetchall()
        index_cols = [idx_col[2] for idx_col in index_cols_rows]
        if index_cols == ["sku"]:
            has_global_unique_sku = True
            break

    if not has_global_unique_sku:
        return

    connection.execute(text("""
        CREATE TABLE products_new (
            id INTEGER PRIMARY KEY,
            companyId INTEGER,
            categoryId INTEGER,
            sku VARCHAR,
            name VARCHAR,
            brand VARCHAR,
            description VARCHAR,
            unitPrice FLOAT,
            costPrice FLOAT,
            stockQuantity INTEGER,
            initialStockQuantity INTEGER,
            unitOfMeasure VARCHAR,
            price VARCHAR,
            status VARCHAR DEFAULT 'active',
            createdAt DATETIME,
            updatedAt DATETIME
        )
    """))

    connection.execute(text("""
        INSERT INTO products_new (
            id, companyId, categoryId, sku, name, brand, description,
            unitPrice, costPrice, stockQuantity, initialStockQuantity, unitOfMeasure,
            price, status, createdAt, updatedAt
        )
        SELECT
            id, companyId, categoryId, sku, name, brand, description,
            unitPrice, costPrice, initialStockQuantity, initialStockQuantity, unitOfMeasure,
            price, status, createdAt, createdAt
        FROM products
    """))

    connection.execute(text("DROP TABLE products"))
    connection.execute(text("ALTER TABLE products_new RENAME TO products"))

    # Recreate indexes, now with company-scoped SKU uniqueness.
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_companyId ON products(companyId)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_categoryId ON products(categoryId)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_name ON products(name)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_brand ON products(brand)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_sku ON products(sku)"))
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_products_company_sku ON products(companyId, sku)"))


def ensure_schema() -> None:
    inspector = inspect(engine)
    company_columns = {column["name"] for column in inspector.get_columns("companies")}
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    refresh_columns = {column["name"] for column in inspector.get_columns("refresh_tokens")}
    audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    category_columns = {column["name"] for column in inspector.get_columns("categories")}
    product_columns = {column["name"] for column in inspector.get_columns("products")}

    with engine.begin() as connection:
        migrate_products_table_for_company_sku_uniqueness(connection)

        if "industry" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN industry VARCHAR"))
        if "email" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN email VARCHAR"))
        if "address" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN address VARCHAR"))
        if "phone" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN phone VARCHAR"))
        if "createdAt" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN createdAt DATETIME"))
        if "companyId" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN companyId INTEGER"))
        if "name" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN name VARCHAR"))
        if "password" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password VARCHAR"))
        if "role" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR"))
        if "status" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR DEFAULT 'active'"))
        if "lastLogin" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN lastLogin DATETIME"))
        if "createdAt" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN createdAt DATETIME"))
        if "userId" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN userId INTEGER"))
        if "token" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN token VARCHAR"))
        if "expiresAt" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN expiresAt DATETIME"))
        if "createdAt" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN createdAt DATETIME"))
        if "company" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN company VARCHAR"))
        if "entityName" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN entityName VARCHAR"))
        if "user" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN user VARCHAR"))
        if "action" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN action VARCHAR"))
        if "ipAddress" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN ipAddress VARCHAR"))
        if "browser" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN browser VARCHAR"))
        if "timestamp" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN timestamp DATETIME"))
        if "companyId" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN companyId INTEGER"))
        if "name" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN name VARCHAR"))
        if "description" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN description VARCHAR"))
        if "status" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN status VARCHAR DEFAULT 'active'"))
        if "createdAt" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN createdAt DATETIME"))
        if "updatedAt" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN updatedAt DATETIME"))
        if "companyId" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN companyId INTEGER"))
        if "categoryId" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN categoryId INTEGER"))
        if "sku" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN sku VARCHAR"))
        if "name" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN name VARCHAR"))
        if "brand" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN brand VARCHAR"))
        if "description" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN description VARCHAR"))
        if "unitPrice" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN unitPrice FLOAT"))
        if "costPrice" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN costPrice FLOAT"))
        if "stockQuantity" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN stockQuantity INTEGER"))
        if "initialStockQuantity" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN initialStockQuantity INTEGER"))
        if "unitOfMeasure" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN unitOfMeasure VARCHAR"))
        if "price" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN price VARCHAR"))
        if "status" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN status VARCHAR DEFAULT 'active'"))
        if "createdAt" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN createdAt DATETIME"))
        if "updatedAt" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN updatedAt DATETIME"))

        # Normalize SKU values and enforce tenant-scoped uniqueness at DB level.
        connection.execute(text("UPDATE products SET sku = UPPER(TRIM(sku)) WHERE sku IS NOT NULL"))
        connection.execute(text("UPDATE products SET stockQuantity = initialStockQuantity WHERE stockQuantity IS NULL AND initialStockQuantity IS NOT NULL"))
        connection.execute(text("UPDATE products SET initialStockQuantity = stockQuantity WHERE initialStockQuantity IS NULL AND stockQuantity IS NOT NULL"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_products_company_sku ON products(companyId, sku)"))


ensure_schema()


def seed_demo_data() -> None:
    session = SessionLocal()
    try:
        retail_co = session.query(Company).first()
        if retail_co is None:
            retail_co = Company(
                name="RetailPulse North",
                industry="Retail",
                email="hello@retailpulse.com",
                address="123 Main Street",
                phone="555-0100",
            )
            session.add(retail_co)
            session.flush()

        admin_user = session.query(User).filter(User.email == "admin@retailpulse.com").first()
        analyst_user = session.query(User).filter(User.email == "analyst@retailpulse.com").first()

        if admin_user is None:
            admin_user = User(
                email="admin@retailpulse.com",
                password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                companyId=retail_co.id,
                role="super_admin",
                name="RetailPulse Admin",
            )
            session.add(admin_user)
        else:
            if not admin_user.password:
                admin_user.password = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
            if admin_user.companyId is None:
                admin_user.companyId = retail_co.id

        if analyst_user is None:
            analyst_user = User(
                email="analyst@retailpulse.com",
                password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                companyId=retail_co.id,
                role="analyst",
                name="RetailPulse Analyst",
            )
            session.add(analyst_user)
        else:
            if not analyst_user.password:
                analyst_user.password = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
            if analyst_user.companyId is None:
                analyst_user.companyId = retail_co.id
        session.commit()
    finally:
        session.close()


seed_demo_data()

app = FastAPI(title="RetailPulse Analytics API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return value

    @field_validator('companyName', 'ownerName')
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('This field is required')
        return value

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


class AuditLogResponse(BaseModel):
    id: int
    company: str
    entity: str | None = None
    action: str
    performedBy: str
    time: str


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


class SalesLineRequest(BaseModel):
    productId: int
    quantity: int

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Quantity must be greater than 0")
        return value


class SalesEntryRequest(BaseModel):
    lines: list[SalesLineRequest]

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, value: list[SalesLineRequest]) -> list[SalesLineRequest]:
        if not value:
            raise ValueError("At least one line item is required")
        return value


class SalesLineResponse(BaseModel):
    productId: int
    productName: str
    sku: str
    quantity: int
    unitPrice: float
    lineTotal: float


class SalesTransactionResponse(BaseModel):
    transactionId: int
    companyId: int
    createdBy: int
    totalAmount: float
    createdAt: str
    lines: list[SalesLineResponse]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

DbDependency = Annotated[object, Depends(get_db)]


def create_audit_log(db, company: str, user: str, action: str, entity_name: str | None = None, ip_address: str | None = None, browser: str | None = None) -> None:
    entry = AuditLog(
        company=company,
        entityName=entity_name,
        user=user,
        action=action,
        ipAddress=ip_address or "Unknown",
        browser=browser or "Unknown",
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "token_type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "token_type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def generate_and_store_refresh_token(db, user: User, expires_delta: timedelta | None = None) -> str:
    """Create a refresh JWT and persist it to DB for revocation/validation."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": user.email, "company_id": user.companyId, "exp": expire, "token_type": "refresh"}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    # store token
    try:
        rt = RefreshToken(userId=user.id, token=token, expiresAt=expire)
        db.add(rt)
        db.commit()
    except Exception:
        db.rollback()
    return token


def validate_refresh_token(db, token: str) -> User:
    """Validate that a refresh token exists in DB, hasn't expired, and return the associated user."""
    credentials_exception = HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type: str | None = payload.get("token_type")
        email: str | None = payload.get("sub")
        company_id: int | None = payload.get("company_id")
        if token_type != "refresh" or email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    stored = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if not stored:
        raise credentials_exception
    if stored.expiresAt:
        expires_at = stored.expiresAt
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            # expired - remove
            db.delete(stored)
            db.commit()
            raise credentials_exception

    user = get_user_by_email(db, email, company_id)
    if not user:
        raise credentials_exception
    return user


def revoke_refresh_token(db, token: str) -> None:
    stored = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if stored:
        db.delete(stored)
        db.commit()


def get_user_by_email(db, email: str, company_id: int | None = None):
    query = db.query(User).filter(User.email == email.lower())
    if company_id is not None:
        query = query.filter(User.companyId == company_id)
    return query.first()


def get_company_for_user(db, user: User):
    company = db.query(Company).filter(Company.id == user.companyId).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def generate_unique_company_name(db, base_name: str) -> str:
    name = base_name.strip()
    counter = 2
    candidate = name
    while db.query(Company).filter(Company.name.ilike(candidate)).first():
        candidate = f"{name} {counter}"
        counter += 1
    return candidate


def generate_unique_email(db, base_email: str, model_cls) -> str:
    candidate = base_email.lower()
    counter = 2
    while db.query(model_cls).filter(model_cls.email == candidate).first():
        local_part, domain = candidate.split("@", 1)
        candidate = f"{local_part}+{counter}@{domain}"
        counter += 1
    return candidate


def format_user_profile(user: User, company: Company) -> dict:
    return {
        "id": user.id,
        "name": user.name or user.email,
        "email": user.email,
        "role": user.role or 'viewer',
        "company": company.name,
        "lastLogin": user.lastLogin.strftime('%Y-%m-%d %H:%M:%S') if user.lastLogin else 'Never',
        "accountStatus": user.status or 'active',
    }


def get_current_user(db: DbDependency, token: str, expected_type: str = "access"):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        company_id: int | None = payload.get("company_id")
        token_type: str | None = payload.get("token_type")
        if email is None or token_type != expected_type:
            raise credentials_exception
        token_data = TokenData(email=email, company_id=company_id)
    except JWTError as exc:
        raise credentials_exception from exc

    user = get_user_by_email(db, token_data.email, company_id=token_data.company_id)
    if user is None:
        raise credentials_exception
    return user


@app.post("/auth/register", response_model=Token)
def register(payload: RegisterRequest, db: DbDependency):
    if payload.password != payload.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    normalized_company_name = payload.companyName.strip()
    normalized_owner_email = str(payload.ownerEmail).lower()
    normalized_company_email = str(payload.companyEmail).lower()

    if not normalized_company_name:
        raise HTTPException(status_code=400, detail="Company name is required")

    company_name = generate_unique_company_name(db, normalized_company_name)
    owner_email = generate_unique_email(db, normalized_owner_email, User)
    company_email = generate_unique_email(db, normalized_company_email, Company)

    company = Company(
        name=company_name,
        industry=payload.industry.strip(),
        email=company_email,
        address=payload.companyAddress,
        phone=payload.companyPhone,
    )
    db.add(company)
    db.flush()

    user = User(
        email=owner_email,
        password=bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode(),
        companyId=company.id,
        role="company_admin",
        name=payload.ownerName,
    )
    db.add(user)
    db.commit()
    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Company Registered",
        ip_address="Unknown",
        browser="Unknown",
    )

    access_token = create_access_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = generate_and_store_refresh_token(db, user, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "companyId": user.companyId,
            "companyName": company.name,
            "role": user.role,
        },
    }


@app.post("/auth/login", response_model=Token)
def login(payload: LoginRequest, db: DbDependency):
    user = get_user_by_email(db, str(payload.email).lower())
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    create_audit_log(
        db,
        company=user.email,
        user=user.email,
        action="User Login",
        ip_address="Unknown",
        browser="Unknown",
    )

    access_token = create_access_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = generate_and_store_refresh_token(db, user, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    company = db.query(Company).filter(Company.id == user.companyId).first()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "companyId": user.companyId,
            "companyName": company.name if company else "Unknown",
            "role": user.role,
        },
    }


@app.post("/auth/refresh", response_model=Token)
def refresh(payload: RefreshTokenRequest, db: DbDependency):
    # validate the provided refresh token exists and is valid
    try:
        user = validate_refresh_token(db, payload.refresh_token)
    except HTTPException as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    # revoke the provided refresh token and issue a new one
    try:
        revoke_refresh_token(db, payload.refresh_token)
    except Exception:
        pass

    access_token = create_access_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = generate_and_store_refresh_token(db, user, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    company = db.query(Company).filter(Company.id == user.companyId).first()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "companyId": user.companyId,
            "companyName": company.name if company else "Unknown",
            "role": user.role,
        },
    }


@app.post("/auth/logout")
def logout(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    # attempt to decode token to check its type; if it's a refresh token, revoke it
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("token_type")
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if token_type == "refresh":
        revoke_refresh_token(db, token)
    # audit log based on email if present
    create_audit_log(
        db,
        company=email or "Unknown",
        user=email or "Unknown",
        action="User Logout",
        ip_address="Unknown",
        browser="Unknown",
    )
    return {"message": "Logged out successfully"}


@app.post("/auth/change-password")
def change_password(payload: ChangePasswordRequest, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)

    if payload.newPassword != payload.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if not verify_password(payload.currentPassword, user.password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    user.password = bcrypt.hashpw(payload.newPassword.encode(), bcrypt.gensalt()).decode()
    db.commit()
    create_audit_log(
        db,
        company=user.email,
        user=user.email,
        action="Password Changed",
        ip_address="Unknown",
        browser="Unknown",
    )
    return {"message": "Password changed successfully"}


@app.get("/auth/me", response_model=UserResponse)
def get_me(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    company = get_company_for_user(db, user)
    return format_user_profile(user, company)


@app.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    company = get_company_for_user(db, user)

    summary = _get_company_product_summary(db, user.companyId)

    return {
        "companyName": company.name,
        "metrics": {
            "totalProducts": summary.totalProducts,
            "activeProducts": summary.activeProducts,
            "inactiveProducts": summary.inactiveProducts,
            "totalCategories": summary.totalCategories,
        },
        "visibility": ["Sales", "Inventory", f"Region: {company.address or 'Unknown'}"],
    }


@app.get("/dashboard/product-summary", response_model=ProductSummaryResponse)
def dashboard_product_summary(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)

    return _get_company_product_summary(db, user.companyId)


@app.get("/companies/{company_id}/users")
def list_company_users(company_id: int, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    # company isolation: only allow same-company users or super_admins
    if user.companyId != company_id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    users = db.query(User).filter(User.companyId == company_id).all()
    result = []
    for u in users:
        result.append({"id": u.id, "email": u.email, "name": u.name, "role": u.role, "status": u.status})

    create_audit_log(
        db,
        company=str(company_id),
        user=user.email,
        action="List Company Users",
        ip_address="Unknown",
        browser="Unknown",
    )
    return result


@app.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    db: DbDependency,
    limit: int = 200,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    sanitized_limit = max(1, min(limit, 1000))
    company_keys = [str(user.companyId)]
    if company and company.name:
        company_keys.append(company.name)

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.company.in_(company_keys))
        .order_by(desc(AuditLog.timestamp), desc(AuditLog.id))
        .limit(sanitized_limit)
        .all()
    )

    response: list[AuditLogResponse] = []
    for item in logs:
        formatted_time = item.timestamp.strftime("%d %b %Y %H:%M") if item.timestamp else ""
        response.append(
            AuditLogResponse(
                id=item.id,
                company=item.company or (company.name if company else ""),
                entity=item.entityName,
                action=item.action or "",
                performedBy=item.user or "",
                time=formatted_time,
            )
        )
    return response


def _ensure_admin(user: User):
    if user.role not in ("company_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin role required")


def _get_company_product_summary(db, company_id: int) -> ProductSummaryResponse:
    total_products = db.query(Product).filter(Product.companyId == company_id).count()
    active_products = db.query(Product).filter(Product.companyId == company_id, Product.status == "active").count()
    inactive_products = db.query(Product).filter(Product.companyId == company_id, Product.status == "inactive").count()
    total_categories = db.query(Category).filter(Category.companyId == company_id).count()
    return ProductSummaryResponse(
        totalProducts=total_products,
        activeProducts=active_products,
        inactiveProducts=inactive_products,
        totalCategories=total_categories,
    )


def _to_product_response(product: Product) -> ProductResponse:
    stock_quantity = int(product.stockQuantity if product.stockQuantity is not None else (product.initialStockQuantity or 0))
    return ProductResponse(
        id=product.id,
        name=product.name,
        sku=product.sku,
        categoryId=product.categoryId,
        brand=product.brand or "",
        description=product.description,
        unitPrice=float(product.unitPrice or 0),
        costPrice=float(product.costPrice or 0),
        stockQuantity=stock_quantity,
        initialStockQuantity=stock_quantity,
        unitOfMeasure=product.unitOfMeasure or "",
        status=product.status or "active",
        createdAt=product.createdAt.isoformat() if product.createdAt else None,
        updatedAt=product.updatedAt.isoformat() if product.updatedAt else None,
    )


def _normalize_sku(sku: str) -> str:
    return sku.strip().upper()


def _is_product_active(product: Product) -> bool:
    return (product.status or "active").lower() == "active"


def _transaction_response(db, tx: SalesTransaction) -> SalesTransactionResponse:
    lines = db.query(SalesTransactionLine).filter(SalesTransactionLine.transactionId == tx.id).all()
    line_responses = [
        SalesLineResponse(
            productId=line.productId,
            productName=line.productNameSnapshot or "",
            sku=line.skuSnapshot or "",
            quantity=line.quantity or 0,
            unitPrice=float(line.unitPrice or 0),
            lineTotal=float(line.lineTotal or 0),
        )
        for line in lines
    ]
    return SalesTransactionResponse(
        transactionId=tx.id,
        companyId=tx.companyId,
        createdBy=tx.createdBy,
        totalAmount=float(tx.totalAmount or 0),
        createdAt=tx.createdAt.strftime("%Y-%m-%d %H:%M:%S") if tx.createdAt else "",
        lines=line_responses,
    )


@app.get("/categories", response_model=list[CategoryResponse])
def list_categories(db: DbDependency, q: str | None = None, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)

    query = db.query(Category).filter(Category.companyId == user.companyId)
    if q:
        query = query.filter(Category.name.ilike(f"%{q}%"))
    categories = query.all()

    result = []
    for c in categories:
        count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == c.id).count()
        result.append(CategoryResponse(id=c.id, name=c.name, description=c.description, status=c.status or "active", productCount=count))

    create_audit_log(db, company=str(user.companyId), user=user.email, action="List Categories", ip_address="Unknown", browser="Unknown")
    return result


@app.post("/categories", response_model=CategoryResponse)
def create_category(payload: CategoryRequest, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    # unique per company
    existing = db.query(Category).filter(Category.companyId == user.companyId, Category.name.ilike(payload.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category name already exists")

    cat = Category(
        companyId=user.companyId,
        name=payload.name.strip(),
        description=payload.description or "",
        status=payload.status or "active",
        updatedAt=datetime.now(timezone.utc),
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)

    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Category Created",
        entity_name=cat.name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return CategoryResponse(id=cat.id, name=cat.name, description=cat.description, status=cat.status or "active", productCount=0)


@app.get("/categories/{category_id}")
def get_category(category_id: int, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)

    cat = db.query(Category).filter(Category.id == category_id, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == cat.id).count()
    create_audit_log(db, company=str(user.companyId), user=user.email, action=f"Get Category:{cat.name}", ip_address="Unknown", browser="Unknown")
    return CategoryResponse(id=cat.id, name=cat.name, description=cat.description, status=cat.status or "active", productCount=count)


@app.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, payload: CategoryRequest, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    cat = db.query(Category).filter(Category.id == category_id, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # check unique name
    existing = db.query(Category).filter(Category.companyId == user.companyId, Category.name.ilike(payload.name), Category.id != category_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category name already exists")

    cat.name = payload.name.strip()
    cat.description = payload.description or ""
    cat.status = payload.status or cat.status
    cat.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cat)

    count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == cat.id).count()
    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Category Updated",
        entity_name=cat.name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return CategoryResponse(id=cat.id, name=cat.name, description=cat.description, status=cat.status or "active", productCount=count)


@app.delete("/categories/{category_id}")
def delete_category(category_id: int, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    cat = db.query(Category).filter(Category.id == category_id, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    prod_count = db.query(Product).filter(Product.companyId == user.companyId, Product.categoryId == cat.id).count()
    if prod_count > 0:
        raise HTTPException(status_code=400, detail="Category has products; deactivate instead of deleting")

    db.delete(cat)
    db.commit()
    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Category Deleted",
        entity_name=cat.name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return {"message": "Category deleted"}


@app.get("/products", response_model=list[ProductResponse])
def list_products(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    brand: str | None = None,
    status_filter: str | None = None,
    sortBy: str | None = None,
    sortOrder: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)

    query = db.query(Product).filter(Product.companyId == user.companyId)
    if q:
        wildcard = f"%{q}%"
        query = query.filter(
            Product.name.ilike(wildcard)
            | Product.sku.ilike(wildcard)
            | Product.brand.ilike(wildcard)
            | Product.description.ilike(wildcard)
        )
    if categoryId:
        query = query.filter(Product.categoryId == categoryId)
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if status_filter:
        query = query.filter(Product.status == status_filter.lower())

    normalized_sort = (sortBy or "").strip().lower()
    normalized_order = (sortOrder or "").strip().lower()
    if normalized_sort == "name":
        query = query.order_by(desc(Product.name) if normalized_order == "desc" else asc(Product.name))
    elif normalized_sort == "price":
        query = query.order_by(desc(Product.unitPrice) if normalized_order == "desc" else asc(Product.unitPrice))
    elif normalized_sort in ("recently_added", "recently-added", "recent"):
        # Recently added defaults to newest first.
        query = query.order_by(asc(Product.createdAt) if normalized_order == "asc" else desc(Product.createdAt))

    prods = query.all()
    result = [_to_product_response(p) for p in prods]

    create_audit_log(db, company=str(user.companyId), user=user.email, action="List Products", ip_address="Unknown", browser="Unknown")
    return result


@app.post("/products", response_model=ProductResponse)
def create_product(payload: ProductRequest, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    # ensure category belongs to company
    cat = db.query(Category).filter(Category.id == payload.categoryId, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category")

    # prevent duplicate product name within the same category for the company
    if db.query(Product).filter(
        Product.companyId == user.companyId,
        Product.categoryId == payload.categoryId,
        Product.name.ilike(payload.name.strip()),
    ).first():
        raise HTTPException(status_code=400, detail="Product name already exists in this category")

    normalized_sku = _normalize_sku(payload.sku)

    # unique sku per company
    if db.query(Product).filter(Product.companyId == user.companyId, Product.sku == normalized_sku).first():
        raise HTTPException(status_code=400, detail="SKU already exists")

    p = Product(
        companyId=user.companyId,
        categoryId=payload.categoryId,
        sku=normalized_sku,
        name=payload.name.strip(),
        brand=payload.brand.strip(),
        description=payload.description or "",
        unitPrice=payload.unitPrice,
        costPrice=payload.costPrice,
        stockQuantity=payload.stockQuantity,
        initialStockQuantity=payload.stockQuantity,
        unitOfMeasure=payload.unitOfMeasure.strip(),
        price=str(payload.unitPrice),
        status=(payload.status or "active").lower(),
        updatedAt=datetime.now(timezone.utc),
    )
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="SKU already exists")
    db.refresh(p)

    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Product Created",
        entity_name=p.name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return _to_product_response(p)


@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    create_audit_log(db, company=str(user.companyId), user=user.email, action=f"Get Product:{product.name}", ip_address="Unknown", browser="Unknown")
    return _to_product_response(product)


@app.put("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, payload: ProductRequest, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    p = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    # validate category
    cat = db.query(Category).filter(Category.id == payload.categoryId, Category.companyId == user.companyId).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category")

    normalized_sku = _normalize_sku(payload.sku)

    # check sku uniqueness
    existing = db.query(Product).filter(Product.companyId == user.companyId, Product.sku == normalized_sku, Product.id != product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")

    # prevent duplicate product name within the same category for the company
    duplicate_name = db.query(Product).filter(
        Product.companyId == user.companyId,
        Product.categoryId == payload.categoryId,
        Product.name.ilike(payload.name.strip()),
        Product.id != product_id,
    ).first()
    if duplicate_name:
        raise HTTPException(status_code=400, detail="Product name already exists in this category")

    p.name = payload.name.strip()
    p.sku = normalized_sku
    p.categoryId = payload.categoryId
    p.brand = payload.brand.strip()
    p.description = payload.description or ""
    p.unitPrice = payload.unitPrice
    p.costPrice = payload.costPrice
    p.stockQuantity = payload.stockQuantity
    p.initialStockQuantity = payload.stockQuantity
    p.unitOfMeasure = payload.unitOfMeasure.strip()
    p.price = str(payload.unitPrice)
    p.status = (payload.status or p.status or "active").lower()
    p.updatedAt = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="SKU already exists")
    db.refresh(p)

    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Product Updated",
        entity_name=p.name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return _to_product_response(p)


@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    p = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    product_name = p.name
    db.delete(p)
    db.commit()
    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action="Product Deleted",
        entity_name=product_name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return {"message": "Product deleted"}


@app.patch("/products/{product_id}/status", response_model=ProductResponse)
def update_product_status(product_id: int, payload: ProductStatusRequest, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)
    _ensure_admin(user)
    company = get_company_for_user(db, user)

    normalized = payload.status.lower().strip()
    if normalized not in ("active", "inactive"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")

    product = db.query(Product).filter(Product.id == product_id, Product.companyId == user.companyId).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.status = normalized
    product.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(product)

    action = "Product Activated" if normalized == "active" else "Product Deactivated"

    create_audit_log(
        db,
        company=company.name,
        user=user.email,
        action=action,
        entity_name=product.name,
        ip_address="Unknown",
        browser="Unknown",
    )
    return _to_product_response(product)


@app.get("/sales/products/selectable", response_model=list[ProductResponse])
def list_selectable_products_for_sales(
    db: DbDependency,
    q: str | None = None,
    categoryId: int | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)

    query = db.query(Product).filter(Product.companyId == user.companyId, Product.status == "active")
    if q:
        wildcard = f"%{q}%"
        query = query.filter(
            Product.name.ilike(wildcard)
            | Product.sku.ilike(wildcard)
            | Product.brand.ilike(wildcard)
            | Product.description.ilike(wildcard)
        )
    if categoryId:
        query = query.filter(Product.categoryId == categoryId)

    products = query.all()
    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="List Sales Selectable Products",
        ip_address="Unknown",
        browser="Unknown",
    )
    return [_to_product_response(product) for product in products]


@app.post("/sales/transactions", response_model=SalesTransactionResponse)
def create_sales_transaction(payload: SalesEntryRequest, db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)

    products_by_id = {}
    for line in payload.lines:
        product = db.query(Product).filter(Product.id == line.productId, Product.companyId == user.companyId).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {line.productId}")
        if not _is_product_active(product):
            raise HTTPException(status_code=400, detail=f"Inactive product cannot be used in new transactions: {product.sku}")
        products_by_id[line.productId] = product

    tx = SalesTransaction(companyId=user.companyId, createdBy=user.id, totalAmount=0)
    db.add(tx)
    db.flush()

    total_amount = 0.0
    for line in payload.lines:
        product = products_by_id[line.productId]
        unit_price = float(product.unitPrice or 0)
        line_total = unit_price * line.quantity
        total_amount += line_total
        tx_line = SalesTransactionLine(
            transactionId=tx.id,
            productId=product.id,
            quantity=line.quantity,
            unitPrice=unit_price,
            lineTotal=line_total,
            productNameSnapshot=product.name,
            skuSnapshot=product.sku,
        )
        db.add(tx_line)

    tx.totalAmount = total_amount
    db.commit()
    db.refresh(tx)

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action=f"Create Sales Transaction:{tx.id}",
        ip_address="Unknown",
        browser="Unknown",
    )
    return _transaction_response(db, tx)


@app.get("/sales/reports/history", response_model=list[SalesTransactionResponse])
def sales_history_report(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    user = get_current_user(db, token)

    # Historical report includes all transactions regardless of current product status.
    transactions = (
        db.query(SalesTransaction)
        .filter(SalesTransaction.companyId == user.companyId)
        .order_by(SalesTransaction.id.desc())
        .all()
    )

    create_audit_log(
        db,
        company=str(user.companyId),
        user=user.email,
        action="View Sales History Report",
        ip_address="Unknown",
        browser="Unknown",
    )
    return [_transaction_response(db, tx) for tx in transactions]
