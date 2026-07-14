from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import bcrypt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import Column, Integer, String, DateTime, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

SECRET_KEY = "retailpulse-dev-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "retailpulse.db"

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
    user = Column(String)
    action = Column(String)
    ipAddress = Column(String)
    browser = Column(String)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)


def ensure_schema() -> None:
    inspector = inspect(engine)
    company_columns = {column["name"] for column in inspector.get_columns("companies")}
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    refresh_columns = {column["name"] for column in inspector.get_columns("refresh_tokens")}
    audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}

    with engine.begin() as connection:
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

DbDependency = Annotated[object, Depends(get_db)]


def create_audit_log(db, company: str, user: str, action: str, ip_address: str | None = None, browser: str | None = None) -> None:
    entry = AuditLog(
        company=company,
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
    refresh_token = create_refresh_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
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
    refresh_token = create_refresh_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
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
    try:
        user = get_current_user(db, payload.refresh_token, expected_type="refresh")
    except HTTPException as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    access_token = create_access_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
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
    user = get_current_user(db, token)
    create_audit_log(
        db,
        company=user.email,
        user=user.email,
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

    return {
        "companyName": company.name,
        "metrics": {
            "totalStores": 24 + user.companyId,
            "revenue": 1850000 + (user.companyId * 10000),
            "activePromotions": 8 + user.companyId,
        },
        "visibility": ["Sales", "Inventory", f"Region: {company.address or 'Unknown'}"],
    }
