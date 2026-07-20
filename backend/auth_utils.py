import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt

from backend.database import SessionLocal
from backend.models import Company, RefreshToken, User
from backend.schemas import TokenData

SECRET_KEY = os.environ.get("SECRET_KEY", "retailpulse-dev-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "token_type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "token_type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def generate_and_store_refresh_token(db, user: User, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode = {"sub": user.email, "company_id": user.companyId, "exp": expire, "token_type": "refresh"}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    try:
        rt = RefreshToken(userId=user.id, token=token, expiresAt=expire)
        db.add(rt)
        db.commit()
    except Exception:
        db.rollback()
    return token


def validate_refresh_token(db, token: str) -> User:
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
        "role": user.role or "viewer",
        "company": company.name,
        "lastLogin": user.lastLogin.strftime("%Y-%m-%d %H:%M:%S") if user.lastLogin else "Never",
        "accountStatus": user.status or "active",
    }


def get_current_user(db, token: str, expected_type: str = "access"):
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
