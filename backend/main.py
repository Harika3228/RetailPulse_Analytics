# RetailPulse Analytics - backend entry point
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.migrations import ensure_schema
from backend.seed import seed_demo_data
from backend.routers.auth_routes import router as auth_router
from backend.routers.dashboard_routes import router as dashboard_router
from backend.routers.categories_routes import router as categories_router
from backend.routers.products_routes import router as products_router
from backend.routers.sales_routes import router as sales_router

ensure_schema()
seed_demo_data()
app = FastAPI(title="RetailPulse Analytics API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(categories_router)
app.include_router(products_router)
app.include_router(sales_router)
