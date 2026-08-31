from fastapi import APIRouter, Header, Request

from backend.controllers.imports_controller import (
    confirm_import,
    create_import_preview,
    delete_import_batch,
    export_failed_records,
    get_import_batch_detail,
    get_import_errors,
    list_import_batches,
)
from backend.database import DbDependency
from backend.schemas import (
    ImportBatchDetailResponse,
    ImportBatchResponse,
    ImportConfirmResponse,
    ImportErrorsResponse,
    ImportPreviewResponse,
)

router = APIRouter(tags=["data-imports"])


@router.post("/imports/{entity_type}/preview", response_model=ImportPreviewResponse)
async def preview_import_route(
    entity_type: str,
    request: Request,
    db: DbDependency,
    fileName: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    raw = await request.body()
    return create_import_preview(raw, entity_type, fileName or "", db, authorization)


@router.get("/imports", response_model=list[ImportBatchResponse])
def list_imports_route(
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return list_import_batches(db, authorization)


@router.get("/imports/{batch_id}", response_model=ImportBatchDetailResponse)
def import_detail_route(
    batch_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_import_batch_detail(batch_id, db, authorization)


@router.get("/imports/{batch_id}/failed-records")
def export_failed_records_route(
    batch_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return export_failed_records(batch_id, db, authorization)


@router.get("/imports/{batch_id}/errors", response_model=ImportErrorsResponse)
def import_errors_route(
    batch_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return get_import_errors(batch_id, db, authorization)


@router.post("/imports/{batch_id}/confirm", response_model=ImportConfirmResponse)
def confirm_import_route(
    batch_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return confirm_import(batch_id, db, authorization)


@router.delete("/imports/{batch_id}")
def delete_import_route(
    batch_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return delete_import_batch(batch_id, db, authorization)
