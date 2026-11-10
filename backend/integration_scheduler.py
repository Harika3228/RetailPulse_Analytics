import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request

from backend.auth_utils import create_access_token
from backend.controllers.integrations_controller import (
    _audit_sync_run,
    _next_schedule_at,
    start_csv_sync,
)
from backend.database import SessionLocal
from backend.helpers import create_notification
from backend.integration_secrets import decrypt_source_data
from backend.models import IntegrationConnector, IntegrationSyncRun, User


class _TaskCollector:
    def __init__(self) -> None:
        self.tasks: list[tuple[object, tuple, dict]] = []

    def add_task(self, function, *args, **kwargs) -> None:
        self.tasks.append((function, args, kwargs))

    def run(self) -> None:
        for function, args, kwargs in self.tasks:
            function(*args, **kwargs)


def _request_with_csv(content: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": content, "more_body": False}

    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/integrations/scheduled-sync",
            "raw_path": b"/integrations/scheduled-sync",
            "query_string": b"",
            "headers": [
                (b"content-type", b"text/csv"),
                (b"content-length", str(len(content)).encode("ascii")),
            ],
            "client": ("127.0.0.1", 0),
            "server": ("localhost", 80),
        },
        receive,
    )


def _eligible_actor(db, connector: IntegrationConnector) -> User | None:
    creator = db.query(User).filter(
        User.id == connector.createdByUserId,
        User.companyId == connector.companyId,
        User.status == "active",
        User.role.in_(("admin", "company_admin", "super_admin")),
    ).first()
    if creator:
        return creator
    return db.query(User).filter(
        User.companyId == connector.companyId,
        User.status == "active",
        User.role.in_(("admin", "company_admin", "super_admin")),
    ).order_by(User.id.asc()).first()


def _record_schedule_failure(db, connector: IntegrationConnector, actor: User | None) -> None:
    now = datetime.now(timezone.utc)
    failed_run = IntegrationSyncRun(
        companyId=connector.companyId,
        connectorId=connector.id,
        triggeredByUserId=actor.id if actor else None,
        triggerType="scheduled",
        syncMode="incremental",
        status="failed",
        startedAt=now,
        completedAt=now,
        failureReason="Scheduled synchronization could not be started. Review the integration configuration and saved source file.",
    )
    db.add(failed_run)
    db.flush()
    _audit_sync_run(db, failed_run, connector, "Integration Sync Failed")
    connector.nextSyncAt = (
        _next_schedule_at(connector.syncFrequency or "manual", connector.scheduleTime, connector.scheduleDay, now)
        if connector.scheduleEnabled and connector.encryptedSourceData else None
    )
    create_notification(
        db,
        company_id=connector.companyId,
        message=f"Scheduled synchronization for integration {connector.name} could not be started.",
        notification_type="integration_sync_failed",
        severity="error",
        target_role="admin",
        resource_type="IntegrationSyncRun",
        resource_id=failed_run.id,
        alert_key=f"integration-sync:{failed_run.id}:failed",
    )
    db.commit()


def process_due_csv_integrations() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due_rows = db.query(IntegrationConnector.id, IntegrationConnector.nextSyncAt).filter(
                IntegrationConnector.dataSourceType == "csv",
                IntegrationConnector.status == "active",
                IntegrationConnector.scheduleEnabled.is_(True),
                IntegrationConnector.syncFrequency.in_(("hourly", "daily", "weekly")),
                IntegrationConnector.encryptedSourceData.isnot(None),
                IntegrationConnector.nextSyncAt.isnot(None),
                IntegrationConnector.nextSyncAt <= now,
            ).order_by(IntegrationConnector.nextSyncAt.asc(), IntegrationConnector.id.asc()).limit(25).all()
        for connector_id, scheduled_for in due_rows:
            claimed = db.query(IntegrationConnector).filter(
                IntegrationConnector.id == connector_id,
                IntegrationConnector.status == "active",
                IntegrationConnector.scheduleEnabled.is_(True),
                IntegrationConnector.nextSyncAt.isnot(None),
                IntegrationConnector.nextSyncAt <= now,
            ).update(
                {IntegrationConnector.nextSyncAt: now + timedelta(minutes=5)},
                synchronize_session=False,
            )
            if claimed != 1:
                db.rollback()
                continue
            db.commit()
            connector = db.query(IntegrationConnector).filter(
                IntegrationConnector.id == connector_id,
            ).first()
            if connector is None:
                continue
            active_run = db.query(IntegrationSyncRun.id).filter(
                IntegrationSyncRun.companyId == connector.companyId,
                IntegrationSyncRun.connectorId == connector.id,
                IntegrationSyncRun.status.in_(("pending", "running")),
            ).first()
            if active_run:
                skipped_run = IntegrationSyncRun(
                    companyId=connector.companyId,
                    connectorId=connector.id,
                    triggerType="scheduled",
                    syncMode="incremental",
                    status="cancelled",
                    startedAt=now,
                    completedAt=now,
                    failureReason="Scheduled run skipped because another synchronization was still in progress.",
                )
                db.add(skipped_run)
                db.flush()
                create_notification(
                    db,
                    company_id=connector.companyId,
                    message=f"Scheduled synchronization for integration {connector.name} was skipped because another run is still in progress.",
                    notification_type="integration_sync_skipped",
                    severity="warning",
                    target_role="admin",
                    resource_type="IntegrationSyncRun",
                    resource_id=skipped_run.id,
                    alert_key=f"integration-sync-skipped:{connector.id}:{scheduled_for.isoformat()}",
                )
                connector.nextSyncAt = _next_schedule_at(
                    connector.syncFrequency or "manual",
                    connector.scheduleTime,
                    connector.scheduleDay,
                    now,
                )
                db.commit()
                continue

            actor = _eligible_actor(db, connector)
            if actor is None or not connector.encryptedSourceData:
                _record_schedule_failure(db, connector, actor)
                continue
            try:
                source_data = decrypt_source_data(connector.encryptedSourceData)
                token = create_access_token({"sub": actor.email, "company_id": actor.companyId})
                tasks = _TaskCollector()
                response = asyncio.run(start_csv_sync(
                    connector.id,
                    _request_with_csv(source_data),
                    db,
                    f"Bearer {token}",
                    connector.sourceFileName or f"integration-{connector.id}.csv",
                    tasks,
                    scheduled=True,
                ))
                if response.get("triggerType") != "scheduled":
                    raise RuntimeError("The scheduled synchronization was not recorded as scheduled")
                tasks.run()
            except Exception:
                db.rollback()
                logging.exception("Scheduled integration synchronization could not start for connector %s", connector.id)
                connector = db.query(IntegrationConnector).filter(
                    IntegrationConnector.id == connector_id,
                ).first()
                if connector:
                    _record_schedule_failure(db, connector, actor)
    finally:
        db.close()


async def integration_schedule_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(process_due_csv_integrations)
        except Exception:
            logging.exception("Integration schedule polling failed")
        await asyncio.sleep(30)
