from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from backend.controllers.imports_controller import (
    MAX_IMPORT_FILE_BYTES,
    authorize_import_admin,
    cancel_import_batch,
    create_import_preview,
    delete_import_batch,
    enqueue_import,
    export_failed_records,
    get_import_batch_detail,
    get_import_errors,
    list_import_batches,
    run_import_job,
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
    authorize_import_admin(db, authorization)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(status_code=415, detail="Unsupported media type. Upload a CSV file.")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_IMPORT_FILE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File is too large. Maximum allowed size is {MAX_IMPORT_FILE_BYTES // (1024 * 1024)} MB.",
                )
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from error

    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_IMPORT_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large. Maximum allowed size is {MAX_IMPORT_FILE_BYTES // (1024 * 1024)} MB.",
            )
    return create_import_preview(bytes(raw), entity_type, fileName or "", db, authorization)


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
    background_tasks: BackgroundTasks,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    response, user_id = enqueue_import(batch_id, db, authorization)
    background_tasks.add_task(run_import_job, batch_id, user_id)
    return response


@router.post("/imports/{batch_id}/cancel")
def cancel_import_route(
    batch_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return cancel_import_batch(batch_id, db, authorization)


@router.delete("/imports/{batch_id}")
def delete_import_route(
    batch_id: int,
    db: DbDependency,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return delete_import_batch(batch_id, db, authorization)
