from datetime import timedelta

import bcrypt
from jose import JWTError, jwt

from backend.auth_utils import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
    create_access_token,
    generate_and_store_refresh_token,
    generate_unique_company_name,
    generate_unique_email,
    get_company_for_user,
    get_current_user,
    get_user_by_email,
    revoke_refresh_token,
    validate_refresh_token,
    verify_password,
)
from backend.database import DbDependency
from backend.helpers import create_audit_log
from backend.models import Company, User
from backend.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    Token,
    UserResponse,
)


def _extract_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise JWTError("Missing token")
    return authorization.split(" ", 1)[1]


def register_user(payload: RegisterRequest, db: DbDependency) -> dict:
    if payload.password != payload.confirmPassword:
        raise ValueError("Passwords do not match")

    normalized_company_name = payload.companyName.strip()
    if not normalized_company_name:
        raise ValueError("Company name is required")

    normalized_owner_email = str(payload.ownerEmail).lower()
    normalized_company_email = str(payload.companyEmail).lower()

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
    create_audit_log(db, company=company.name, user=user.email, action="Company Registered",
                     ip_address="Unknown", browser="Unknown")

    access_token = create_access_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = generate_and_store_refresh_token(db, user, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
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


def login_user(payload: LoginRequest, db: DbDependency) -> dict:
    user = get_user_by_email(db, str(payload.email).lower())
    if not user or not verify_password(payload.password, user.password):
        raise ValueError("Invalid credentials")

    create_audit_log(db, company=user.email, user=user.email, action="User Login",
                     ip_address="Unknown", browser="Unknown")

    access_token = create_access_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = generate_and_store_refresh_token(db, user, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
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


def refresh_access_token(payload: RefreshTokenRequest, db: DbDependency) -> dict:
    user = validate_refresh_token(db, payload.refresh_token)
    revoke_refresh_token(db, payload.refresh_token)

    access_token = create_access_token(
        {"sub": user.email, "company_id": user.companyId},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = generate_and_store_refresh_token(db, user, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
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


def logout_user(db: DbDependency, authorization: str | None) -> dict:
    token = _extract_token(authorization)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("token_type")
        email = payload.get("sub")
    except JWTError:
        raise ValueError("Invalid token")

    if token_type == "refresh":
        revoke_refresh_token(db, token)
    create_audit_log(db, company=email or "Unknown", user=email or "Unknown", action="User Logout",
                     ip_address="Unknown", browser="Unknown")
    return {"message": "Logged out successfully"}


def change_password(payload: ChangePasswordRequest, db: DbDependency, authorization: str | None) -> dict:
    token = _extract_token(authorization)
    user = get_current_user(db, token)

    if payload.newPassword != payload.confirmPassword:
        raise ValueError("Passwords do not match")
    if not verify_password(payload.currentPassword, user.password):
        raise ValueError("Current password is incorrect")

    user.password = bcrypt.hashpw(payload.newPassword.encode(), bcrypt.gensalt()).decode()
    db.commit()
    create_audit_log(db, company=user.email, user=user.email, action="Password Changed",
                     ip_address="Unknown", browser="Unknown")
    return {"message": "Password changed successfully"}


def get_me_response(db: DbDependency, authorization: str | None) -> UserResponse:
    token = _extract_token(authorization)
    user = get_current_user(db, token)
    company = get_company_for_user(db, user)
    return {
        "id": user.id,
        "name": user.name or user.email,
        "email": user.email,
        "role": user.role or "viewer",
        "company": company.name,
        "lastLogin": user.lastLogin.strftime("%Y-%m-%d %H:%M:%S") if user.lastLogin else "Never",
        "accountStatus": user.status or "active",
    }
