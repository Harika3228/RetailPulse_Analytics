from fastapi import APIRouter, Header, HTTPException
from jose import JWTError

from backend.controllers.auth_controller import (
    change_password,
    get_me_response,
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
)
from backend.database import DbDependency
from backend.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    Token,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register(payload: RegisterRequest, db: DbDependency):
    try:
        return register_user(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: DbDependency):
    try:
        return login_user(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshTokenRequest, db: DbDependency):
    try:
        return refresh_access_token(payload, db)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout")
def logout(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    try:
        return logout_user(db, authorization)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/change-password")
def change_password_route(
    payload: ChangePasswordRequest,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    try:
        return change_password(payload, db, authorization)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/me", response_model=UserResponse)
def get_me(db: DbDependency, authorization: str | None = Header(default=None, alias="Authorization")):
    try:
        return get_me_response(db, authorization)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
