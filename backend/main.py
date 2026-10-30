# RetailPulse Analytics - backend entry point
import os
import sys
import logging
from time import perf_counter

BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from backend.auth_utils import ALGORITHM, SECRET_KEY
from backend.auth_utils import get_current_user
from backend.access_control import has_permission, permission_for_request
from backend.database import SessionLocal
from backend.migrations import ensure_schema
from backend.system_monitoring import (
    cleanup_monitoring_data,
    evaluate_api_thresholds,
    record_api_request,
)
from backend.seed import seed_demo_data
from backend.routers.auth_routes import router as auth_router
from backend.routers.dashboard_routes import router as dashboard_router
from backend.routers.categories_routes import router as categories_router
from backend.routers.products_routes import router as products_router
from backend.routers.sales_routes import router as sales_router
from backend.routers.inventory_routes import router as inventory_router
from backend.routers.customers_routes import router as customers_router
from backend.routers.imports_routes import router as imports_router
from backend.routers.forecasting_routes import router as forecasting_router
from backend.routers.analytics_routes import router as analytics_router
from backend.routers.workflows_routes import router as workflows_router
from backend.routers.system_health_routes import router as system_health_router
from backend.routers.governance_routes import router as governance_router

ensure_schema()
seed_demo_data()
app = FastAPI(title="RetailPulse Analytics API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def enforce_role_permissions(request, call_next):
    policy = permission_for_request(request)
    authorization = request.headers.get("authorization", "")
    is_cors_preflight = (
        request.method.upper() == "OPTIONS"
        and "origin" in request.headers
        and "access-control-request-method" in request.headers
    )
    if policy and not is_cors_preflight and not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if policy and not is_cors_preflight:
        db = SessionLocal()
        try:
            try:
                user = get_current_user(db, authorization.split(" ", 1)[1])
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
            module, action = policy
            if not has_permission(db, user.companyId, user.role, module, action):
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Permission denied: {action} access to {module} is required"},
                )
        finally:
            db.close()
    return await call_next(request)


@app.middleware("http")
async def record_api_request_metrics(request, call_next):
    started_at = perf_counter()
    company_id = None
    exclude_metric = request.url.path in {
        "/health",
        "/api/health",
        "/system-health",
        "/system-health/requests",
        "/api/system-health/requests",
    } or request.url.path.startswith("/system-health/")
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        try:
            claims = jwt.decode(
                authorization.split(" ", 1)[1],
                SECRET_KEY,
                algorithms=[ALGORITHM],
                options={"verify_exp": False},
            )
            if claims.get("token_type") == "access" and isinstance(claims.get("company_id"), int):
                company_id = claims.get("company_id")
        except (JWTError, TypeError, ValueError):
            company_id = None

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (perf_counter() - started_at) * 1000
        if not exclude_metric:
            _persist_api_request_metric(
                company_id,
                request.method,
                _metric_endpoint(request),
                500,
                elapsed_ms,
                "Unhandled server error",
            )
        raise

    if not exclude_metric:
        elapsed_ms = (perf_counter() - started_at) * 1000
        _persist_api_request_metric(
            company_id,
            request.method,
            _metric_endpoint(request),
            response.status_code,
            elapsed_ms,
            _safe_error_detail(response.status_code),
        )
    return response


def _persist_api_request_metric(
    company_id: int | None,
    method: str,
    path: str,
    status_code: int,
    response_time_ms: float,
    error_details: str | None,
) -> None:
    if company_id is None:
        return
    db = SessionLocal()
    try:
        record_api_request(
            db,
            company_id=int(company_id),
            method=method,
            path=path,
            status_code=status_code,
            response_time_ms=round(response_time_ms, 2),
            error_details=error_details,
        )
        db.commit()
        evaluate_api_thresholds(db, int(company_id))
        cleanup_monitoring_data(db)
    except Exception:
        db.rollback()
        logging.exception("Unable to persist API health metric")
    finally:
        db.close()


def _metric_endpoint(request) -> str:
    route = request.scope.get("route")
    route_template = getattr(route, "path", None)
    return route_template if isinstance(route_template, str) else request.url.path


def _safe_error_detail(status_code: int) -> str | None:
    if status_code < 400:
        return None
    if status_code >= 500:
        return "Server error"
    return "Client error"


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(categories_router)
app.include_router(products_router)
app.include_router(sales_router)
app.include_router(inventory_router)
app.include_router(customers_router)
app.include_router(imports_router)
app.include_router(forecasting_router)
app.include_router(analytics_router)
app.include_router(workflows_router)
app.include_router(system_health_router)
app.include_router(governance_router)
