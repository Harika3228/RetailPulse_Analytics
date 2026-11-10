import base64
import csv
import http.client
import hashlib
import ipaddress
import io
import json
import logging
import os
import socket
import ssl
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import text

from backend.access_control import has_permission
from backend.auth_utils import create_access_token, get_current_user
from backend.controllers.imports_controller import (
    FIELD_ALIASES,
    MAX_IMPORT_FILE_BYTES,
    REQUIRED_COLUMN_GROUPS,
    _decode_csv,
    create_import_preview,
    enqueue_import,
    run_import_job,
)
from backend.database import DbDependency, SessionLocal
from backend.helpers import _ensure_admin, create_audit_log, create_notification
from backend.integration_secrets import (
    decrypt_credentials,
    decrypt_source_data,
    encrypt_credentials,
    encrypt_source_data,
)
from backend.models import (
    Customer,
    IntegrationConnector,
    IntegrationSyncRun,
    ImportBatch,
    ImportRecord,
    Notification,
    Product,
    User,
)
from backend.schemas import (
    IntegrationConnectionTestRequest,
    IntegrationConnectorCreate,
    IntegrationConnectorUpdate,
    IntegrationFieldMappingUpdate,
    IntegrationScheduleUpdate,
)

SUPPORTED_MODULES = {"products", "inventory", "sales", "customers"}
SENSITIVE_CONFIG_KEYS = {
    "password",
    "token",
    "secret",
    "apikey",
    "authorization",
    "connectionstring",
    "connectionurl",
    "connectionuri",
    "uri",
    "url",
}
FIELD_TYPES = {
    "products": {
        "sku": "text", "name": "text", "categoryid": "integer", "categoryname": "text",
        "brand": "text", "description": "text", "unitprice": "decimal", "costprice": "decimal",
        "stockquantity": "integer", "maxstocklevel": "integer", "unitofmeasure": "text", "status": "text",
    },
    "inventory": {"sku": "text", "stockquantity": "integer", "reason": "text"},
    "customers": {
        "name": "text", "email": "email", "phone": "text", "dateofbirth": "date",
        "gender": "text", "address": "text", "city": "text", "state": "text", "country": "text",
        "postalcode": "text", "customertype": "text", "preferredsaleschannel": "text", "status": "text",
    },
    "sales": {
        "invoicenumber": "text", "sku": "text", "productid": "integer", "quantity": "integer",
        "unitprice": "decimal", "customeremail": "email", "customername": "text",
        "saledatetime": "date", "saleschannel": "text", "paymentmethod": "text",
        "paymentstatus": "text", "discountamount": "decimal", "taxamount": "decimal",
    },
}


def _authorize(
    db: DbDependency,
    authorization: str | None,
    action: str,
    *,
    require_admin: bool,
):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = get_current_user(db, authorization.split(" ", 1)[1])
    if require_admin:
        _ensure_admin(user)
    if not has_permission(db, user.companyId, user.role, "data_integrations", action):
        raise HTTPException(status_code=403, detail=f"Permission denied: {action} access to integrations is required")
    return user


def _get_connector(db: DbDependency, company_id: int, connector_id: int) -> IntegrationConnector:
    connector = db.query(IntegrationConnector).filter(
        IntegrationConnector.id == connector_id,
        IntegrationConnector.companyId == company_id,
    ).first()
    if connector is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return connector


def _source_type(connector: IntegrationConnector) -> str:
    return (connector.dataSourceType or "unknown").strip().lower()


def _parse_configuration(connector: IntegrationConnector) -> dict:
    try:
        configuration = json.loads(connector.connectionConfiguration or "{}")
    except (TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Stored integration configuration is invalid") from error
    if not isinstance(configuration, dict):
        raise HTTPException(status_code=500, detail="Stored integration configuration is invalid")
    return configuration


def _public_connector(db: DbDependency, connector: IntegrationConnector) -> dict:
    creator = db.query(User).filter(User.id == connector.createdByUserId).first()
    source_type = _source_type(connector)
    return {
        "id": connector.id,
        "name": connector.name,
        "dataSourceType": source_type,
        "connectionConfiguration": _parse_configuration(connector),
        "authenticationMethod": connector.authenticationMethod or "none",
        "hasCredentials": bool(connector.credentialsConfigured),
        "targetModule": connector.targetModule or "products",
        "syncFrequency": connector.syncFrequency or "manual",
        "scheduleEnabled": bool(connector.scheduleEnabled),
        "scheduleTime": connector.scheduleTime or "00:00",
        "scheduleDay": connector.scheduleDay,
        "duplicateStrategy": connector.duplicateStrategy or "skip",
        "hasSourceFile": bool(connector.encryptedSourceData),
        "nextSyncAt": connector.nextSyncAt,
        "status": (connector.status or "inactive").lower(),
        "isOperational": source_type == "csv",
        "createdBy": creator.name or creator.email if creator else "Unknown user",
        "createdAt": connector.createdAt,
        "updatedAt": connector.updatedAt,
    }


def _validate_connection(
    source_type: str,
    configuration: dict,
    authentication_method: str,
    credentials: dict[str, str],
    sync_frequency: str,
    target_module: str | None = None,
) -> dict:
    if not isinstance(configuration, dict):
        raise HTTPException(status_code=422, detail="Connection configuration must be an object")
    if len(json.dumps(configuration, default=str)) > 8000:
        raise HTTPException(status_code=422, detail="Connection configuration is too large")

    def contains_sensitive_key(value) -> bool:
        if isinstance(value, dict):
            return any(
                str(key).replace("-", "").replace("_", "").lower() in SENSITIVE_CONFIG_KEYS
                or contains_sensitive_key(nested)
                for key, nested in value.items()
            )
        if isinstance(value, list):
            return any(contains_sensitive_key(item) for item in value)
        return False

    if contains_sensitive_key(configuration):
        raise HTTPException(
            status_code=422,
            detail="Secrets must be supplied through the credentials field, not connection configuration",
        )
    if any(len(key) > 64 or len(value) > 4096 for key, value in credentials.items()):
        raise HTTPException(status_code=422, detail="Credential fields exceed the supported size")
    if any("\r" in value or "\n" in value for value in credentials.values()):
        raise HTTPException(status_code=422, detail="Credential fields cannot contain line breaks")
    if authentication_method == "none" and credentials:
        raise HTTPException(status_code=422, detail="Credentials cannot be provided when authentication is disabled")

    if source_type == "csv":
        if authentication_method != "none" or credentials:
            raise HTTPException(status_code=422, detail="CSV upload connectors do not support authentication")
        if set(configuration) - {"mode", "fieldMappings"}:
            raise HTTPException(status_code=422, detail="CSV connectors accept uploaded files and no connection settings")
        if configuration.get("mode", "upload") != "upload":
            raise HTTPException(status_code=422, detail="CSV connector mode must be upload")
        if "fieldMappings" in configuration:
            if target_module is None:
                raise HTTPException(status_code=422, detail="A target module is required to validate saved field mappings")
            saved_mapping = configuration["fieldMappings"]
            if not isinstance(saved_mapping, dict):
                raise HTTPException(status_code=422, detail="Saved field mappings must be an object")
            _validate_field_mapping(target_module, list(saved_mapping), saved_mapping)
        return {**configuration, "mode": "upload"}

    if source_type == "postgresql":
        allowed = {"host", "port", "database", "schema", "table", "username"}
        if set(configuration) - allowed:
            raise HTTPException(status_code=422, detail="PostgreSQL connection configuration contains unsupported fields")
        host = configuration.get("host")
        database = configuration.get("database")
        if not isinstance(host, str) or not host.strip() or not isinstance(database, str) or not database.strip():
            raise HTTPException(status_code=422, detail="PostgreSQL host and database are required")
        if "@" in host or "://" in host:
            raise HTTPException(status_code=422, detail="Use a hostname without embedded credentials or a connection URI")
        if not isinstance(configuration.get("table"), str) or not configuration["table"].strip():
            raise HTTPException(status_code=422, detail="PostgreSQL table is required to verify read permissions")
        try:
            raw_port = configuration.get("port", 5432)
            if isinstance(raw_port, bool) or (
                not isinstance(raw_port, int)
                and not (isinstance(raw_port, str) and raw_port.isdigit())
            ):
                raise ValueError
            port = int(raw_port)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail="PostgreSQL port must be an integer") from error
        if not 1 <= port <= 65535:
            raise HTTPException(status_code=422, detail="PostgreSQL port must be between 1 and 65535")
        configuration = {**configuration, "port": port}
        if authentication_method == "password" and not credentials.get("password"):
            raise HTTPException(status_code=422, detail="A password is required for password authentication")
        if authentication_method not in {"none", "password"}:
            raise HTTPException(status_code=422, detail="PostgreSQL supports none or password authentication")
        return configuration

    if source_type == "rest_api":
        allowed = {"baseUrl", "resourcePath", "httpMethod"}
        if set(configuration) - allowed:
            raise HTTPException(status_code=422, detail="REST API configuration contains unsupported fields")
        base_url = configuration.get("baseUrl")
        if not isinstance(base_url, str):
            raise HTTPException(status_code=422, detail="REST API base URL is required")
        if any(ord(char) < 32 for char in base_url):
            raise HTTPException(status_code=422, detail="REST API base URL contains invalid control characters")
        try:
            parsed_url = urlsplit(base_url)
            parsed_port = parsed_url.port
        except ValueError as error:
            raise HTTPException(status_code=422, detail="REST API base URL is invalid") from error
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise HTTPException(status_code=422, detail="REST API base URL must be an HTTP(S) URL without embedded credentials")
        if parsed_port is not None and not 1 <= parsed_port <= 65535:
            raise HTTPException(status_code=422, detail="REST API port must be between 1 and 65535")
        resource_path = configuration.get("resourcePath", "")
        if (
            not isinstance(resource_path, str)
            or "?" in resource_path
            or "#" in resource_path
            or any(ord(char) < 32 for char in resource_path)
        ):
            raise HTTPException(status_code=422, detail="REST API resource path cannot contain query parameters or fragments")
        method = str(configuration.get("httpMethod", "GET")).upper()
        if method not in {"GET", "POST"}:
            raise HTTPException(status_code=422, detail="REST API method must be GET or POST")
        configuration = {**configuration, "httpMethod": method}
        required_secret = {
            "bearer_token": ("token",),
            "api_key": ("apiKey",),
            "basic": ("username", "password"),
        }.get(authentication_method)
        if authentication_method not in {"none", "bearer_token", "api_key", "basic"}:
            raise HTTPException(status_code=422, detail="Unsupported REST API authentication method")
        if required_secret and any(not credentials.get(key) for key in required_secret):
            raise HTTPException(
                status_code=422,
                detail=f"Credentials are required for {authentication_method} authentication",
            )
        return configuration

    raise HTTPException(status_code=422, detail="Unsupported integration data source type")


def _resolve_connection_addresses(host: str, port: int):
    allowed_hosts = {
        entry.strip().lower().rstrip(".")
        for entry in os.environ.get("INTEGRATION_ALLOWED_HOSTS", "").split(",")
        if entry.strip()
    }
    explicitly_allowed = host.lower().rstrip(".") in allowed_hosts
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError("The host name could not be resolved. Check the host and DNS settings.") from error
    if not addresses:
        raise ValueError("The host name did not resolve to an address.")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global and not explicitly_allowed:
            raise ValueError(
                "The host resolves to a private or reserved address. For an approved internal source, add its exact host to the server's INTEGRATION_ALLOWED_HOSTS setting."
            )
    return addresses


def _test_postgresql_connection(
    configuration: dict,
    authentication_method: str,
    credentials: dict[str, str],
) -> tuple[bool, str, list[str]]:
    try:
        import psycopg
        from psycopg import sql
    except ImportError as error:
        logging.exception("PostgreSQL test connection requires psycopg")
        return False, "PostgreSQL connection testing is unavailable because its database driver is not installed.", []

    host = configuration["host"].strip()
    port = int(configuration["port"])
    try:
        addresses = _resolve_connection_addresses(host, port)
    except ValueError as error:
        return False, str(error), []

    last_error = None
    for address in addresses:
        resolved_ip = address[4][0]
        try:
            connect_options = {
                "host": host,
                "hostaddr": resolved_ip,
                "port": port,
                "dbname": configuration["database"],
                "user": configuration.get("username") or None,
                "connect_timeout": 4,
                "sslmode": "require",
            }
            if authentication_method == "password":
                connect_options["password"] = credentials.get("password")
            with psycopg.connect(**connect_options) as connection:
                connection.execute("SET TRANSACTION READ ONLY")
                schema = configuration.get("schema")
                table = configuration["table"]
                qualified_table = sql.Identifier(schema, table) if schema else sql.Identifier(table)
                connection.execute(
                    sql.SQL("SELECT 1 FROM {} LIMIT 0").format(qualified_table)
                )
                connection.rollback()
            return True, "Connection succeeded and the configured table is readable.", [
                f"Host resolved and connected using TLS on port {port}.",
                "Read access to the configured table was verified; no data was written.",
            ]
        except psycopg.OperationalError as error:
            last_error = type(error).__name__
        except psycopg.Error as error:
            last_error = type(error).__name__

    message = {
        "InvalidPassword": "Authentication failed. Verify the PostgreSQL username and saved password.",
        "OperationalError": "Could not connect to PostgreSQL. Verify the host, port, firewall, TLS, and database availability.",
        "InsufficientPrivilege": "The connection succeeded, but the account lacks SELECT permission on the configured table.",
        "UndefinedTable": "The connection succeeded, but the configured schema or table was not found.",
    }.get(last_error, "PostgreSQL connection or table-permission check failed. Verify the connection settings and read-only access.")
    return False, message, []


def _test_rest_connection(
    configuration: dict,
    authentication_method: str,
    credentials: dict[str, str],
) -> tuple[bool, str, list[str]]:
    base_url = configuration["baseUrl"]
    parsed_url = urlsplit(base_url)
    host = parsed_url.hostname
    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
    if host is None:
        return False, "The REST API URL does not contain a valid host.", []
    if authentication_method != "none" and parsed_url.scheme != "https":
        return False, "Authentication credentials are only sent to HTTPS endpoints.", []
    try:
        addresses = _resolve_connection_addresses(host, port)
    except ValueError as error:
        return False, str(error), []

    resource_path = configuration.get("resourcePath", "")
    target = "/".join(
        part.strip("/")
        for part in (parsed_url.path, resource_path)
        if part.strip("/")
    )
    target = f"/{target}" if target else "/"
    headers = {
        "Host": host if port in {80, 443} else f"{host}:{port}",
        "Connection": "close",
        "Accept": "application/json, text/plain;q=0.5",
        "User-Agent": "RetailPulse-Integration-Connection-Test",
    }
    if authentication_method == "bearer_token":
        headers["Authorization"] = f"Bearer {credentials['token']}"
    elif authentication_method == "api_key":
        headers["X-API-Key"] = credentials["apiKey"]
    elif authentication_method == "basic":
        encoded = base64.b64encode(
            f"{credentials['username']}:{credentials['password']}".encode("utf-8")
        ).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"

    for address in addresses:
        transport = None
        response = None
        try:
            transport = socket.create_connection(address[4], timeout=4)
            if parsed_url.scheme == "https":
                transport = ssl.create_default_context().wrap_socket(
                    transport,
                    server_hostname=host,
                )
            request = f"GET {target} HTTP/1.1\r\n"
            request += "".join(f"{key}: {value}\r\n" for key, value in headers.items())
            request += "\r\n"
            transport.sendall(request.encode("ascii"))
            response = http.client.HTTPResponse(transport, method="GET")
            response.begin()
            status_code = response.status
            response.read(1024)
            if 200 <= status_code < 300:
                return True, "REST API connection succeeded and the endpoint accepted the configured authentication.", [
                    f"HTTP GET returned status {status_code}.",
                    "The endpoint was read only; no data was posted or modified.",
                ]
            if status_code in {401, 403}:
                return False, "The endpoint is reachable, but authentication or access permission was denied.", [
                    f"HTTP GET returned status {status_code}.",
                    "Verify the authentication method and source-side read permission.",
                ]
            return False, f"The endpoint is reachable but returned HTTP {status_code}. Check the resource path and API configuration.", [
                "Connection test sent a GET request only and did not follow redirects.",
            ]
        except (OSError, ssl.SSLError, http.client.HTTPException, UnicodeError) as error:
            logging.info("REST integration connection test failed (%s)", type(error).__name__)
            return False, "Could not complete the REST API connection test. Verify DNS, TLS, firewall access, and endpoint availability.", []
        finally:
            if response is not None:
                response.close()
            if transport is not None:
                transport.close()
    return False, "Could not connect to the configured REST API host.", []


def test_integration_connection(
    payload: IntegrationConnectionTestRequest,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _authorize(db, authorization, "update", require_admin=True)
    configuration = dict(payload.connectionConfiguration)
    authentication_method = payload.authenticationMethod
    credentials = dict(payload.credentials or {})
    if payload.connectorId is not None:
        connector = _get_connector(db, user.companyId, payload.connectorId)
        if connector.dataSourceType != payload.dataSourceType:
            raise HTTPException(status_code=422, detail="Data source type cannot be changed while testing a saved connector")
        if payload.credentials is None:
            credentials = decrypt_credentials(connector.encryptedCredentials)
    configuration = _validate_connection(
        payload.dataSourceType,
        configuration,
        authentication_method,
        credentials,
        payload.syncFrequency,
        payload.targetModule,
    )
    if payload.dataSourceType == "csv":
        db.execute(text("SELECT 1"))
        success = True
        message = "CSV connector is ready. File access is provided by upload; no business data was imported."
        details = [
            "The application database is reachable.",
            "Target module and upload configuration are valid.",
            "Upload a CSV file to test its headers and field mapping before synchronization.",
        ]
    elif payload.dataSourceType == "postgresql":
        success, message, details = _test_postgresql_connection(
            configuration,
            authentication_method,
            credentials,
        )
    else:
        success, message, details = _test_rest_connection(
            configuration,
            authentication_method,
            credentials,
        )
    if payload.connectorId is not None:
        _audit(
            db,
            user,
            connector,
            "Integration Connection Tested",
            f"Tested the saved connection; result: {'success' if success else 'failure'}.",
        )
    if payload.connectorId is not None:
        connection_alert_key = f"integration-connection:{connector.id}"
        if not success:
            create_notification(
                db,
                company_id=user.companyId,
                message=f"Connection test failed for integration {connector.name}.",
                notification_type="integration_connection_failed",
                severity="warning",
                target_role="admin",
                resource_type="Integration",
                resource_id=connector.id,
                alert_key=connection_alert_key,
            )
        else:
            unresolved = db.query(Notification).filter(
                Notification.companyId == user.companyId,
                Notification.alertKey == connection_alert_key,
                Notification.resolvedAt.is_(None),
            ).all()
            for notification in unresolved:
                notification.resolvedAt = datetime.now(timezone.utc)
            if unresolved:
                create_notification(
                    db,
                    company_id=user.companyId,
                    message=f"Connection test recovered for integration {connector.name}.",
                    notification_type="integration_connection_recovered",
                    severity="success",
                    target_role="admin",
                    resource_type="Integration",
                    resource_id=connector.id,
                    alert_key=f"integration-connection-recovered:{connector.id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
                )
        db.commit()
    return {
        "success": success,
        "message": message,
        "details": details,
        "testedAt": datetime.now(timezone.utc),
    }


def _validate_field_mapping(
    entity_type: str,
    source_fields: list[str],
    field_mapping: dict[str, str] | None,
) -> dict[str, str]:
    if entity_type not in FIELD_ALIASES:
        raise HTTPException(status_code=422, detail="Unsupported target module for field mapping")
    if len(source_fields) != len(set(source_fields)) or any(not field.strip() for field in source_fields):
        raise HTTPException(status_code=400, detail="CSV contains blank or duplicate source field names")
    available_fields = FIELD_ALIASES[entity_type]
    normalized_aliases = {
        alias.replace("_", "").replace("-", "").replace(" ", "").lower(): target
        for target, aliases in available_fields.items()
        for alias in aliases | {target}
    }
    if field_mapping is None:
        field_mapping = {
            source_field: normalized_aliases.get(
                source_field.replace("_", "").replace("-", "").replace(" ", "").lower(),
            )
            for source_field in source_fields
        }
        field_mapping = {
            source_field: target_field
            for source_field, target_field in field_mapping.items()
            if target_field is not None
        }
    if not field_mapping:
        raise HTTPException(status_code=422, detail="Map external fields to RetailPulse fields before synchronizing")
    if len(field_mapping) > len(available_fields):
        raise HTTPException(status_code=422, detail="Field mapping contains too many fields")
    for source_field, target_field in field_mapping.items():
        if source_field not in source_fields:
            raise HTTPException(status_code=422, detail=f"Mapped source field '{source_field}' is not in the CSV header")
        if target_field not in available_fields:
            raise HTTPException(status_code=422, detail=f"Target field '{target_field}' is not valid for {entity_type}")
    if len(set(field_mapping.values())) != len(field_mapping):
        raise HTTPException(status_code=422, detail="A RetailPulse field can only be mapped once")
    mapped_fields = set(field_mapping.values())
    missing_groups = [
        group for group in REQUIRED_COLUMN_GROUPS[entity_type]
        if not group.intersection(mapped_fields)
    ]
    if missing_groups:
        missing_labels = [
            " or ".join(sorted(group))
            for group in missing_groups
        ]
        raise HTTPException(
            status_code=422,
            detail=f"Required RetailPulse fields are not mapped: {', '.join(missing_labels)}",
        )
    return field_mapping


def _apply_field_mapping(raw: bytes, entity_type: str, field_mapping: dict[str, str]) -> bytes:
    text_content = _decode_csv(raw)
    try:
        dialect = csv.Sniffer().sniff(text_content[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text_content), dialect=dialect, strict=True)
    source_fields = next(
        (row for row in reader if any(field.strip() for field in row)),
        [],
    )
    if not source_fields:
        raise HTTPException(status_code=400, detail="The CSV file appears to be empty")
    mapping = _validate_field_mapping(entity_type, source_fields, field_mapping)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=list(mapping.values()),
        dialect=csv.excel,
        extrasaction="ignore",
    )
    writer.writeheader()
    try:
        for values in reader:
            if not any(value.strip() for value in values):
                continue
            if len(values) > len(source_fields):
                raise HTTPException(status_code=400, detail="CSV row has more values than the header")
            row = {
                field: values[index] if index < len(values) else ""
                for index, field in enumerate(source_fields)
            }
            writer.writerow({
                target: row.get(source, "")
                for source, target in mapping.items()
            })
    except csv.Error as error:
        raise HTTPException(status_code=400, detail="CSV file contains invalid quoting or delimiters") from error
    return output.getvalue().encode("utf-8")


def _audit(
    db: DbDependency,
    user,
    connector: IntegrationConnector,
    action: str,
    description: str,
) -> None:
    create_audit_log(
        db,
        company=str(user.companyId),
        company_id=user.companyId,
        user=user.email,
        user_id=user.id,
        action=action,
        entity_name=connector.name,
        resource_type="Integration",
        resource_id=connector.id,
        description=description,
        commit=False,
    )


def _audit_sync_run(db, sync_run: IntegrationSyncRun, connector: IntegrationConnector | None, action: str) -> None:
    actor = db.query(User).filter(User.id == sync_run.triggeredByUserId).first() if sync_run.triggeredByUserId else None
    create_audit_log(
        db,
        company=str(sync_run.companyId),
        company_id=sync_run.companyId,
        user=actor.email if actor else "Scheduled service",
        user_id=actor.id if actor else None,
        action=action,
        entity_name=connector.name if connector else f"Integration {sync_run.connectorId}",
        resource_type="Integration",
        resource_id=sync_run.connectorId,
        description=f"Synchronization {sync_run.id} reached status '{sync_run.status}'.",
        commit=False,
    )


def _next_schedule_at(
    frequency: str,
    schedule_time: str | None,
    schedule_day: int | None,
    after: datetime,
) -> datetime | None:
    if frequency == "hourly":
        return after + timedelta(hours=1)
    if frequency not in {"daily", "weekly"}:
        return None
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    try:
        hour, minute = (int(part) for part in (schedule_time or "00:00").split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(status_code=500, detail="Stored integration schedule time is invalid")
    candidate = after.astimezone(timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if frequency == "weekly":
        target_day = schedule_day if schedule_day is not None else 0
        if not 0 <= target_day <= 6:
            raise HTTPException(status_code=500, detail="Stored integration schedule day is invalid")
        candidate += timedelta(days=(target_day - candidate.weekday()) % 7)
    if candidate <= after:
        candidate += timedelta(days=7 if frequency == "weekly" else 1)
    return candidate


def _notify_sync_outcome(db, sync_run: IntegrationSyncRun, connector: IntegrationConnector | None) -> None:
    if connector is None:
        return
    status = (sync_run.status or "failed").lower()
    if status == "completed":
        notification_type, severity, label = "integration_sync_completed", "success", "completed"
    elif status == "completed_with_errors":
        notification_type, severity, label = "integration_sync_completed_with_errors", "warning", "completed with errors"
    elif status == "failed":
        notification_type, severity, label = "integration_sync_failed", "error", "failed"
    else:
        return
    create_notification(
        db,
        company_id=sync_run.companyId,
        message=f"Synchronization {sync_run.id} for integration {connector.name} {label}.",
        notification_type=notification_type,
        severity=severity,
        target_role="admin",
        resource_type="IntegrationSyncRun",
        resource_id=sync_run.id,
        alert_key=f"integration-sync:{sync_run.id}:{status}",
    )


def _validate_duplicate_strategy(target_module: str, strategy: str) -> None:
    if target_module == "sales" and strategy == "update":
        raise HTTPException(status_code=422, detail="Sales records cannot use update-existing synchronization")
    if target_module == "inventory" and strategy == "insert":
        raise HTTPException(status_code=422, detail="Inventory synchronization updates existing products; insert-only is not supported")


def _prepare_integration_batch(
    db: DbDependency,
    batch_id: int,
    connector: IntegrationConnector,
    field_mapping: dict[str, str],
    sync_mode: str,
) -> None:
    strategy = connector.duplicateStrategy or "skip"
    batch = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.companyId == connector.companyId,
    ).first()
    if batch is None:
        raise HTTPException(status_code=500, detail="Integration import preview could not be loaded")
    batch.integrationDuplicateStrategy = strategy
    batch.integrationMappedFields = json.dumps(sorted(set(field_mapping.values())))
    records = db.query(ImportRecord).filter(
        ImportRecord.batchId == batch.id,
        ImportRecord.companyId == connector.companyId,
        ImportRecord.status == "duplicate",
    ).all()
    _validate_duplicate_strategy(connector.targetModule, strategy)

    updated_records = 0
    for record in records:
        row_data = json.loads(record.rowData or "{}")
        resolved = row_data.get("resolved", {})
        existing = None
        if strategy == "update" and connector.targetModule == "products":
            sku = str(resolved.get("sku") or "").upper()
            if sku:
                existing = db.query(Product).filter(
                    Product.companyId == connector.companyId,
                    func.upper(Product.sku) == sku,
                ).first()
        elif strategy == "update" and connector.targetModule == "customers":
            email = str(resolved.get("email") or "").lower()
            if email:
                existing = db.query(Customer).filter(
                    Customer.companyId == connector.companyId,
                    Customer.isDeleted != 1,
                    func.lower(Customer.email) == email,
                ).first()

        if strategy == "update" and existing is not None:
            resolved["_integrationUpdate"] = True
            row_data["resolved"] = resolved
            record.rowData = json.dumps(row_data, default=str)
            record.status = "valid"
            record.message = None
            updated_records += 1
        elif strategy in {"insert", "reject"} or strategy == "update":
            record.status = "invalid"
            record.message = (
                "Duplicate record rejected by the configured integration strategy."
            )
            batch.duplicateCount = max(0, int(batch.duplicateCount or 0) - 1)
            batch.invalidCount = int(batch.invalidCount or 0) + 1

    if connector.targetModule == "inventory" and sync_mode == "incremental" and strategy == "skip":
        product_ids = {
            row[0]
            for row in db.query(Product.id).filter(Product.companyId == connector.companyId).all()
        }
        inventory_records = db.query(ImportRecord).filter(
            ImportRecord.batchId == batch.id,
            ImportRecord.companyId == connector.companyId,
            ImportRecord.status == "valid",
        ).all()
        for record in inventory_records:
            row_data = json.loads(record.rowData or "{}")
            resolved = row_data.get("resolved", {})
            if resolved.get("productId") in product_ids:
                record.status = "duplicate"
                record.message = "Existing inventory record skipped by incremental synchronization strategy."
                batch.validCount = max(0, int(batch.validCount or 0) - 1)
                batch.duplicateCount = int(batch.duplicateCount or 0) + 1

    if updated_records:
        batch.duplicateCount = max(0, int(batch.duplicateCount or 0) - updated_records)
        batch.validCount = int(batch.validCount or 0) + updated_records


def get_integration_dashboard(db: DbDependency, authorization: str | None) -> dict:
    user = _authorize(db, authorization, "view", require_admin=False)
    connectors = db.query(IntegrationConnector).filter(
        IntegrationConnector.companyId == user.companyId,
    ).order_by(IntegrationConnector.name.asc(), IntegrationConnector.id.asc()).all()
    run_summaries = db.query(
        IntegrationSyncRun.connectorId,
        func.max(IntegrationSyncRun.completedAt).label("last_sync_at"),
        func.sum(case(
            (IntegrationSyncRun.status.in_(("pending", "running")), 1),
            else_=0,
        )).label("pending_jobs"),
        func.coalesce(func.sum(IntegrationSyncRun.recordsSynced), 0).label("records_synced"),
        func.coalesce(func.sum(IntegrationSyncRun.recordsFailed), 0).label("records_failed"),
    ).filter(
        IntegrationSyncRun.companyId == user.companyId,
    ).group_by(IntegrationSyncRun.connectorId).all()
    summaries = {row.connectorId: row for row in run_summaries}
    latest_run_status: dict[int, str] = {}
    for connector_id, status in db.query(
        IntegrationSyncRun.connectorId,
        IntegrationSyncRun.status,
    ).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.completedAt.isnot(None),
    ).order_by(IntegrationSyncRun.id.desc()).all():
        latest_run_status.setdefault(connector_id, status or "unknown")

    connector_rows = []
    for connector in connectors:
        summary = summaries.get(connector.id)
        source_type = _source_type(connector)
        status = (connector.status or "inactive").strip().lower()
        if status not in {"active", "inactive", "failed"}:
            raise HTTPException(status_code=500, detail="An integration has an invalid stored status")
        connector_rows.append({
            "id": connector.id,
            "name": connector.name,
            "dataSourceType": source_type,
            "status": status,
            "isOperational": source_type == "csv",
            "targetModule": connector.targetModule or "products",
            "syncFrequency": connector.syncFrequency or "manual",
            "scheduleEnabled": bool(connector.scheduleEnabled),
            "scheduleTime": connector.scheduleTime or "00:00",
            "scheduleDay": connector.scheduleDay,
            "nextSyncAt": connector.nextSyncAt,
            "lastSyncAt": summary.last_sync_at if summary else None,
            "lastSyncStatus": latest_run_status.get(connector.id),
            "pendingJobs": int(summary.pending_jobs or 0) if summary else 0,
            "recordsSynced": int(summary.records_synced or 0) if summary else 0,
            "recordsFailed": int(summary.records_failed or 0) if summary else 0,
        })

    normalized_statuses = [(connector.status or "inactive").lower() for connector in connectors]
    return {
        "totalIntegrations": len(connectors),
        "activeIntegrations": normalized_statuses.count("active"),
        "inactiveIntegrations": normalized_statuses.count("inactive"),
        "failedIntegrations": normalized_statuses.count("failed"),
        "lastSyncAt": max(
            (row.last_sync_at for row in run_summaries if row.last_sync_at is not None),
            default=None,
        ),
        "pendingSyncJobs": sum(int(row.pending_jobs or 0) for row in run_summaries),
        "recordsSynced": sum(int(row.records_synced or 0) for row in run_summaries),
        "recordsFailed": sum(int(row.records_failed or 0) for row in run_summaries),
        "integrations": connector_rows,
    }


def get_integration_detail(db: DbDependency, connector_id: int, authorization: str | None) -> dict:
    user = _authorize(db, authorization, "view", require_admin=True)
    connector = _get_connector(db, user.companyId, connector_id)
    return _public_connector(db, connector)


def list_integrations(db: DbDependency, authorization: str | None) -> list[dict]:
    return get_integration_dashboard(db, authorization)["integrations"]


def update_integration_field_mapping(
    connector_id: int,
    payload: IntegrationFieldMappingUpdate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _authorize(db, authorization, "update", require_admin=True)
    connector = _get_connector(db, user.companyId, connector_id)
    if _source_type(connector) != "csv":
        raise HTTPException(status_code=409, detail="Field mapping is available for operational CSV integrations")
    if db.query(IntegrationSyncRun.id).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
        IntegrationSyncRun.status.in_(("pending", "running")),
    ).first():
        raise HTTPException(status_code=409, detail="Field mapping cannot be changed during synchronization")
    field_mappings = _validate_field_mapping(
        connector.targetModule,
        list(payload.fieldMappings),
        dict(payload.fieldMappings),
    )
    configuration = _parse_configuration(connector)
    configuration["fieldMappings"] = field_mappings
    connector.connectionConfiguration = json.dumps(configuration, separators=(",", ":"), sort_keys=True)
    connector.updatedAt = datetime.now(timezone.utc)
    _audit(db, user, connector, "Integration Field Mapping Updated", "Updated validated source-to-target field mappings.")
    db.commit()
    return {
        "connectorId": connector.id,
        "targetModule": connector.targetModule,
        "fieldMappings": field_mappings,
        "updatedAt": connector.updatedAt,
    }


def update_integration_schedule(
    connector_id: int,
    payload: IntegrationScheduleUpdate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    return update_integration(
        connector_id,
        IntegrationConnectorUpdate(
            syncFrequency=payload.syncFrequency,
            scheduleEnabled=payload.scheduleEnabled,
            scheduleTime=payload.scheduleTime,
            scheduleDay=payload.scheduleDay,
        ),
        db,
        authorization,
    )


def set_integration_enabled(
    connector_id: int,
    enabled: bool,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    return update_integration(
        connector_id,
        IntegrationConnectorUpdate(status="active" if enabled else "inactive"),
        db,
        authorization,
    )


def create_integration(
    payload: IntegrationConnectorCreate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _authorize(db, authorization, "create", require_admin=True)
    if payload.scheduleEnabled and payload.syncFrequency == "manual":
        raise HTTPException(status_code=422, detail="A manual integration cannot have an active schedule")
    if payload.scheduleEnabled and payload.dataSourceType != "csv":
        raise HTTPException(status_code=422, detail="Scheduled synchronization is only implemented for CSV integrations")
    credentials = dict(payload.credentials)
    configuration = _validate_connection(
        payload.dataSourceType,
        dict(payload.connectionConfiguration),
        payload.authenticationMethod,
        credentials,
        payload.syncFrequency,
        payload.targetModule,
    )
    _validate_duplicate_strategy(payload.targetModule, payload.duplicateStrategy)
    connector = IntegrationConnector(
        companyId=user.companyId,
        name=payload.name.strip(),
        dataSourceType=payload.dataSourceType,
        connectionConfiguration=json.dumps(configuration, separators=(",", ":"), sort_keys=True),
        encryptedCredentials=encrypt_credentials(credentials),
        credentialsConfigured=bool(credentials),
        authenticationMethod=payload.authenticationMethod,
        targetModule=payload.targetModule,
        syncFrequency=payload.syncFrequency,
        scheduleEnabled=bool(payload.scheduleEnabled and payload.syncFrequency != "manual"),
        scheduleTime=payload.scheduleTime,
        scheduleDay=payload.scheduleDay if payload.scheduleDay is not None else (0 if payload.syncFrequency == "weekly" else None),
        duplicateStrategy=payload.duplicateStrategy,
        status=payload.status,
        createdByUserId=user.id,
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )
    if not connector.name:
        raise HTTPException(status_code=422, detail="Integration name cannot be blank")
    db.add(connector)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An integration with this name already exists") from error
    _audit(db, user, connector, "Integration Created", "Created integration configuration.")
    db.commit()
    return _public_connector(db, connector)


def update_integration(
    connector_id: int,
    payload: IntegrationConnectorUpdate,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _authorize(db, authorization, "update", require_admin=True)
    connector = _get_connector(db, user.companyId, connector_id)
    previous_status = (connector.status or "inactive").lower()
    if db.query(IntegrationSyncRun.id).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
        IntegrationSyncRun.status.in_(("pending", "running")),
    ).first():
        raise HTTPException(status_code=409, detail="Integration configuration cannot be edited during synchronization")
    if payload.clearCredentials and payload.credentials is not None:
        raise HTTPException(status_code=422, detail="Provide credentials or clearCredentials, not both")

    configuration = _parse_configuration(connector)
    authentication_method = connector.authenticationMethod or "none"
    sync_frequency = connector.syncFrequency or "manual"
    schedule_enabled = bool(connector.scheduleEnabled)
    schedule_time = connector.scheduleTime or "00:00"
    schedule_day = connector.scheduleDay
    duplicate_strategy = connector.duplicateStrategy or "skip"
    credentials = decrypt_credentials(connector.encryptedCredentials)
    if payload.connectionConfiguration is not None:
        configuration = dict(payload.connectionConfiguration)
    if payload.authenticationMethod is not None:
        authentication_method = payload.authenticationMethod
    if payload.syncFrequency is not None:
        sync_frequency = payload.syncFrequency
    if payload.scheduleEnabled is not None:
        schedule_enabled = payload.scheduleEnabled
    if payload.scheduleTime is not None:
        schedule_time = payload.scheduleTime
    if payload.scheduleDay is not None:
        schedule_day = payload.scheduleDay
    elif sync_frequency == "weekly" and schedule_day is None:
        schedule_day = 0
    elif sync_frequency != "weekly":
        schedule_day = None
    if schedule_enabled and sync_frequency == "manual":
        raise HTTPException(status_code=422, detail="A manual integration cannot have an active schedule")
    if schedule_enabled and _source_type(connector) != "csv":
        raise HTTPException(status_code=422, detail="Scheduled synchronization is only implemented for CSV integrations")
    if payload.duplicateStrategy is not None:
        duplicate_strategy = payload.duplicateStrategy
    if payload.credentials is not None:
        credentials = dict(payload.credentials)
        connector.encryptedCredentials = encrypt_credentials(credentials)
        connector.credentialsConfigured = bool(credentials)
    elif payload.clearCredentials:
        credentials = {}
        connector.encryptedCredentials = None
        connector.credentialsConfigured = False
    elif authentication_method == "none":
        credentials = {}
        connector.encryptedCredentials = None
        connector.credentialsConfigured = False

    configuration = _validate_connection(
        _source_type(connector),
        configuration,
        authentication_method,
        credentials,
        sync_frequency,
        payload.targetModule or connector.targetModule,
    )
    _validate_duplicate_strategy(
        payload.targetModule or connector.targetModule,
        payload.duplicateStrategy or duplicate_strategy,
    )
    connector.connectionConfiguration = json.dumps(configuration, separators=(",", ":"), sort_keys=True)
    connector.authenticationMethod = authentication_method
    connector.syncFrequency = sync_frequency
    connector.scheduleEnabled = bool(schedule_enabled and sync_frequency != "manual")
    connector.scheduleTime = schedule_time
    connector.scheduleDay = schedule_day
    connector.duplicateStrategy = duplicate_strategy
    if payload.name is not None:
        connector.name = payload.name.strip()
        if not connector.name:
            raise HTTPException(status_code=422, detail="Integration name cannot be blank")
    if payload.targetModule is not None:
        connector.targetModule = payload.targetModule
    if payload.status is not None:
        connector.status = payload.status
    if connector.status != "active" or not connector.scheduleEnabled or _source_type(connector) != "csv":
        connector.nextSyncAt = None
    elif payload.syncFrequency is not None or payload.status == "active" or payload.scheduleEnabled is not None or payload.scheduleTime is not None or payload.scheduleDay is not None:
        connector.nextSyncAt = (
            _next_schedule_at(sync_frequency, schedule_time, schedule_day, datetime.now(timezone.utc))
            if connector.encryptedSourceData else None
        )
    connector.updatedAt = datetime.now(timezone.utc)
    _audit(db, user, connector, "Integration Updated", "Updated integration configuration.")
    if payload.status is not None and payload.status != previous_status:
        _audit(
            db,
            user,
            connector,
            "Integration Enabled" if payload.status == "active" else "Integration Disabled",
            "Enabled the integration." if payload.status == "active" else "Disabled the integration.",
        )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An integration with this name already exists") from error
    return _public_connector(db, connector)


def delete_integration(connector_id: int, db: DbDependency, authorization: str | None) -> dict:
    user = _authorize(db, authorization, "delete", require_admin=True)
    connector = _get_connector(db, user.companyId, connector_id)
    active_run = db.query(IntegrationSyncRun.id).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
        IntegrationSyncRun.status.in_(("pending", "running")),
    ).first()
    if active_run:
        raise HTTPException(status_code=409, detail="An integration cannot be deleted while synchronization is in progress")

    _audit(db, user, connector, "Integration Deleted", "Deleted integration configuration and its synchronization history.")
    db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
    ).delete(synchronize_session=False)
    db.delete(connector)
    db.commit()
    return {"id": connector_id, "status": "deleted"}


def _sync_run_item(db: DbDependency, sync_run: IntegrationSyncRun) -> dict:
    connector = db.query(IntegrationConnector).filter(
        IntegrationConnector.id == sync_run.connectorId,
        IntegrationConnector.companyId == sync_run.companyId,
    ).first()
    actor = db.query(User).filter(User.id == sync_run.triggeredByUserId).first() if sync_run.triggeredByUserId else None
    status = (sync_run.status or "failed").lower()
    if status not in {"pending", "running", "completed", "completed_with_errors", "failed", "cancelled"}:
        raise HTTPException(status_code=500, detail="A synchronization record has an invalid status")
    started_at = sync_run.startedAt
    completed_at = sync_run.completedAt
    duration_seconds = None
    if started_at:
        end_time = completed_at or datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        duration_seconds = max(0.0, round((end_time - started_at).total_seconds(), 2))
    return {
        "id": sync_run.id,
        "integrationId": sync_run.connectorId,
        "integrationName": connector.name if connector else "Deleted integration",
        "triggeredBy": actor.name or actor.email if actor else ("Scheduled service" if sync_run.triggerType == "scheduled" else "Unknown user"),
        "triggerType": sync_run.triggerType or "manual",
        "syncMode": sync_run.syncMode or "initial",
        "importBatchId": sync_run.importBatchId,
        "startedAt": sync_run.startedAt,
        "completedAt": sync_run.completedAt,
        "durationSeconds": duration_seconds,
        "recordsProcessed": int(sync_run.recordsProcessed or 0),
        "recordsInserted": int(sync_run.recordsInserted or 0),
        "recordsUpdated": int(sync_run.recordsUpdated or 0),
        "recordsSkipped": int(sync_run.recordsSkipped or 0),
        "recordsFailed": int(sync_run.recordsFailed or 0),
        "status": status,
        "failureReason": sync_run.failureReason,
    }


def list_integration_sync_runs(
    db: DbDependency,
    authorization: str | None,
    *,
    offset: int = 0,
    limit: int = 50,
    connector_id: int | None = None,
    status: str | None = None,
) -> dict:
    user = _authorize(db, authorization, "view", require_admin=False)
    if status and status not in {"pending", "running", "completed", "completed_with_errors", "failed", "cancelled"}:
        raise HTTPException(status_code=422, detail="Synchronization status filter is invalid")
    query = db.query(IntegrationSyncRun).filter(IntegrationSyncRun.companyId == user.companyId)
    if connector_id is not None:
        query = query.filter(IntegrationSyncRun.connectorId == connector_id)
    if status:
        query = query.filter(IntegrationSyncRun.status == status)
    total = query.count()
    runs = query.order_by(IntegrationSyncRun.startedAt.desc(), IntegrationSyncRun.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_sync_run_item(db, run) for run in runs]}


def get_integration_sync_run(
    sync_run_id: int,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _authorize(db, authorization, "view", require_admin=False)
    sync_run = db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.id == sync_run_id,
        IntegrationSyncRun.companyId == user.companyId,
    ).first()
    if sync_run is None:
        raise HTTPException(status_code=404, detail="Synchronization record not found")
    result = _sync_run_item(db, sync_run)
    batch = db.query(ImportBatch).filter(
        ImportBatch.id == sync_run.importBatchId,
        ImportBatch.companyId == user.companyId,
    ).first() if sync_run.importBatchId else None
    result["importSummary"] = None if batch is None else {
        "entityType": batch.entityType,
        "fileName": batch.fileName,
        "totalRows": int(batch.totalRows or 0),
        "validRows": int(batch.validCount or 0),
        "invalidRows": int(batch.invalidCount or 0),
        "duplicateRows": int(batch.duplicateCount or 0),
        "status": batch.status,
    }
    return result


def _failed_sync_rows(db: DbDependency, sync_run: IntegrationSyncRun, company_id: int) -> list[dict]:
    if not sync_run.importBatchId:
        return []
    records = db.query(ImportRecord).filter(
        ImportRecord.batchId == sync_run.importBatchId,
        ImportRecord.companyId == company_id,
        ImportRecord.status.in_(("invalid", "duplicate", "failed", "cancelled")),
    ).order_by(ImportRecord.rowNumber.asc(), ImportRecord.id.asc()).all()
    rows = []
    for record in records:
        payload = {}
        try:
            payload = json.loads(record.rowData or "{}")
        except (json.JSONDecodeError, TypeError):
            pass
        resolved = payload.get("resolved") if isinstance(payload, dict) else {}
        resolved = resolved if isinstance(resolved, dict) else {}
        source_id = next(
            (str(resolved[key]) for key in ("sku", "email", "invoiceNumber", "productId", "customerId") if resolved.get(key) not in (None, "")),
            f"row-{int(record.rowNumber or 0)}",
        )
        rows.append({
            "sourceRecordIdentifier": source_id[:200],
            "rowNumber": int(record.rowNumber or 0),
            "errorCategory": {
                "invalid": "Validation",
                "duplicate": "Duplicate",
                "failed": "Processing",
                "cancelled": "Cancelled",
            }.get(record.status or "", "Import"),
            "errorMessage": (record.message or "Row could not be synchronized")[:1000],
            "processingStatus": record.status or "failed",
        })
    return rows


def get_integration_sync_errors(
    sync_run_id: int,
    db: DbDependency,
    authorization: str | None,
) -> dict:
    user = _authorize(db, authorization, "view", require_admin=False)
    sync_run = db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.id == sync_run_id,
        IntegrationSyncRun.companyId == user.companyId,
    ).first()
    if sync_run is None:
        raise HTTPException(status_code=404, detail="Synchronization record not found")
    rows = _failed_sync_rows(db, sync_run, user.companyId)
    return {"syncRunId": sync_run.id, "total": len(rows), "items": rows}


def export_integration_sync_errors(
    sync_run_id: int,
    db: DbDependency,
    authorization: str | None,
) -> Response:
    user = _authorize(db, authorization, "view", require_admin=False)
    sync_run = db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.id == sync_run_id,
        IntegrationSyncRun.companyId == user.companyId,
    ).first()
    if sync_run is None:
        raise HTTPException(status_code=404, detail="Synchronization record not found")
    output = io.StringIO(newline="")
    fieldnames = ["SourceRecordIdentifier", "RowNumber", "ErrorCategory", "ErrorMessage", "ProcessingStatus"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in _failed_sync_rows(db, sync_run, user.companyId):
        writer.writerow({
            "SourceRecordIdentifier": row["sourceRecordIdentifier"],
            "RowNumber": row["rowNumber"],
            "ErrorCategory": row["errorCategory"],
            "ErrorMessage": row["errorMessage"],
            "ProcessingStatus": row["processingStatus"],
        })
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="integration-sync-{sync_run.id}-errors.csv"'},
    )


def retry_failed_sync_records(
    sync_run_id: int,
    db: DbDependency,
    authorization: str | None,
    background_tasks,
) -> dict:
    user = _authorize(db, authorization, "create", require_admin=True)
    previous_run = db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.id == sync_run_id,
        IntegrationSyncRun.companyId == user.companyId,
    ).first()
    if previous_run is None:
        raise HTTPException(status_code=404, detail="Synchronization record not found")
    if previous_run.status not in {"failed", "completed_with_errors"} or not previous_run.importBatchId:
        raise HTTPException(status_code=409, detail="This synchronization has no retryable failed records")
    connector = _get_connector(db, user.companyId, previous_run.connectorId)
    if (connector.status or "").lower() != "active":
        raise HTTPException(status_code=409, detail="Enable this integration before retrying failed records")
    if db.query(IntegrationSyncRun.id).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
        IntegrationSyncRun.status.in_(("pending", "running")),
    ).first():
        raise HTTPException(status_code=409, detail="A synchronization is already in progress for this integration")
    old_records = db.query(ImportRecord).filter(
        ImportRecord.batchId == previous_run.importBatchId,
        ImportRecord.companyId == user.companyId,
        ImportRecord.status == "failed",
    ).order_by(ImportRecord.rowNumber.asc(), ImportRecord.id.asc()).all()
    retry_rows: list[dict[str, str]] = []
    for record in old_records:
        try:
            record_payload = json.loads(record.rowData or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        resolved = record_payload.get("resolved") if isinstance(record_payload, dict) else None
        if isinstance(resolved, dict):
            retry_rows.append({
                key: str(value)
                for key, value in resolved.items()
                if key in FIELD_ALIASES.get(connector.targetModule, {})
                and value is not None
            })
    if not retry_rows:
        raise HTTPException(status_code=409, detail="No failed records contain safe, retryable data")
    target_fields = list(dict.fromkeys(key for row in retry_rows for key in row))
    retry_rows = [{field: row.get(field, "") for field in target_fields} for row in retry_rows]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=target_fields)
    writer.writeheader()
    writer.writerows(retry_rows)
    raw = output.getvalue().encode("utf-8-sig")
    field_mapping = {field: field for field in target_fields}
    field_mapping = _validate_field_mapping(connector.targetModule, target_fields, field_mapping)
    mapped_raw = _apply_field_mapping(raw, connector.targetModule, field_mapping)
    preview = create_import_preview(
        mapped_raw,
        connector.targetModule,
        f"integration-{connector.id}-retry-{sync_run_id}.csv",
        db,
        authorization,
    )
    _prepare_integration_batch(db, preview.batchId, connector, field_mapping, "incremental")
    retry_run = IntegrationSyncRun(
        companyId=user.companyId,
        connectorId=connector.id,
        importBatchId=preview.batchId,
        triggeredByUserId=user.id,
        sourceHash=hashlib.sha256(f"retry:{sync_run_id}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest(),
        syncMode="incremental",
        triggerType="manual",
        status="pending",
    )
    db.add(retry_run)
    db.flush()
    _, import_user_id = enqueue_import(preview.batchId, db, authorization)
    retry_id = retry_run.id
    _audit(db, user, connector, "Integration Failed Records Retried", f"Retried failed records from synchronization {sync_run_id}.")
    db.commit()
    background_tasks.add_task(run_csv_integration_sync, retry_id, preview.batchId, import_user_id)
    return {"syncRunId": retry_id, "importBatchId": preview.batchId, "retriedRecords": len(retry_rows), "status": "pending"}


async def start_csv_sync(
    connector_id: int,
    request: Request,
    db: DbDependency,
    authorization: str | None,
    file_name: str | None,
    background_tasks,
    field_mapping_json: str | None = None,
    *,
    scheduled: bool = False,
) -> dict:
    user = _authorize(db, authorization, "create", require_admin=True)
    connector = _get_connector(db, user.companyId, connector_id)
    if _source_type(connector) != "csv":
        raise HTTPException(status_code=409, detail="Synchronization is not implemented for this data source")
    if (connector.status or "").lower() != "active":
        raise HTTPException(status_code=409, detail="Enable this integration before synchronizing")
    if db.query(IntegrationSyncRun.id).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
        IntegrationSyncRun.status.in_(("pending", "running")),
    ).first():
        raise HTTPException(status_code=409, detail="A synchronization is already in progress for this integration")
    if connector.targetModule not in SUPPORTED_MODULES:
        raise HTTPException(status_code=500, detail="Integration target module is invalid")
    _validate_duplicate_strategy(connector.targetModule, connector.duplicateStrategy or "skip")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(status_code=415, detail="Upload a CSV file to synchronize this integration")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_IMPORT_FILE_BYTES:
                raise HTTPException(status_code=413, detail="CSV file exceeds the 25 MB size limit")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header") from error
    raw = await await_request_bytes(request)
    if len(raw) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 25 MB size limit")
    content_hash = hashlib.sha256(raw).hexdigest()
    source_hash = (
        hashlib.sha256(f"{content_hash}:scheduled:{datetime.now(timezone.utc).isoformat()}".encode("utf-8")).hexdigest()
        if scheduled
        else content_hash
    )
    duplicate = None if scheduled else db.query(IntegrationSyncRun.id).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
        IntegrationSyncRun.sourceHash == content_hash,
        IntegrationSyncRun.triggerType == "manual",
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="This CSV file has already been submitted for this integration")

    try:
        uploaded_text = _decode_csv(raw)
        try:
            dialect = csv.Sniffer().sniff(uploaded_text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        source_fields = next(
            (
                row for row in csv.reader(io.StringIO(uploaded_text), dialect=dialect, strict=True)
                if any(field.strip() for field in row)
            ),
            [],
        )
    except csv.Error as error:
        raise HTTPException(status_code=400, detail="CSV file contains invalid quoting or delimiters") from error
    if any(not field.strip() for field in source_fields):
        raise HTTPException(status_code=400, detail="CSV column names cannot be blank")
    field_mapping = None
    if field_mapping_json:
        try:
            field_mapping = json.loads(field_mapping_json)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=422, detail="Field mapping must be valid JSON") from error
        if not isinstance(field_mapping, dict) or any(
            not isinstance(source, str) or not isinstance(target, str)
            for source, target in field_mapping.items()
        ):
            raise HTTPException(status_code=422, detail="Field mapping must map source field names to RetailPulse field names")
    else:
        saved_mapping = _parse_configuration(connector).get("fieldMappings")
        if isinstance(saved_mapping, dict):
            field_mapping = saved_mapping
    field_mapping = _validate_field_mapping(
        connector.targetModule,
        source_fields,
        field_mapping,
    )
    mapped_raw = _apply_field_mapping(raw, connector.targetModule, field_mapping)
    safe_file_name = file_name or f"integration-{connector.id}.csv"
    preview = create_import_preview(
        mapped_raw,
        connector.targetModule,
        safe_file_name,
        db,
        authorization,
    )
    successful_runs = db.query(IntegrationSyncRun.id).filter(
        IntegrationSyncRun.companyId == user.companyId,
        IntegrationSyncRun.connectorId == connector.id,
        IntegrationSyncRun.status.in_(("completed", "completed_with_errors")),
    ).count()
    sync_mode = "initial" if successful_runs == 0 else "incremental"
    _prepare_integration_batch(db, preview.batchId, connector, field_mapping, sync_mode)
    prepared_batch = db.query(ImportBatch).filter(
        ImportBatch.id == preview.batchId,
        ImportBatch.companyId == user.companyId,
    ).first()
    sync_run = IntegrationSyncRun(
        companyId=user.companyId,
        connectorId=connector.id,
        importBatchId=preview.batchId,
        triggeredByUserId=user.id,
        sourceHash=source_hash,
        syncMode=sync_mode,
        triggerType="scheduled" if scheduled else "manual",
        status="pending",
        recordsSynced=0,
        recordsProcessed=0,
        recordsInserted=0,
        recordsUpdated=0,
        recordsSkipped=0,
        recordsFailed=0,
    )
    configuration = _parse_configuration(connector)
    configuration["mode"] = "upload"
    configuration["fieldMappings"] = field_mapping
    connector.connectionConfiguration = json.dumps(configuration, separators=(",", ":"), sort_keys=True)
    connector.encryptedSourceData = encrypt_source_data(raw)
    connector.sourceFileName = safe_file_name
    connector.nextSyncAt = (
        _next_schedule_at(connector.syncFrequency or "manual", connector.scheduleTime, connector.scheduleDay, datetime.now(timezone.utc))
        if connector.scheduleEnabled and connector.status == "active" else None
    )
    connector.updatedAt = datetime.now(timezone.utc)
    db.add(sync_run)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="This CSV file has already been submitted for this integration") from error

    try:
        import_response, import_user_id = enqueue_import(preview.batchId, db, authorization)
    except HTTPException:
        sync_run = db.query(IntegrationSyncRun).filter(
            IntegrationSyncRun.id == sync_run.id,
            IntegrationSyncRun.companyId == user.companyId,
        ).first()
        if sync_run:
            sync_run.status = "failed"
            sync_run.completedAt = datetime.now(timezone.utc)
            sync_run.failureReason = "The existing import workflow could not queue this synchronization."
            _audit_sync_run(db, sync_run, connector, "Integration Sync Failed")
            db.commit()
        raise

    sync_run_id = sync_run.id
    connector_name = connector.name
    _audit(
        db,
        user,
        connector,
        "Integration Sync Started",
        f"Started CSV synchronization for import batch {preview.batchId}.",
    )
    db.commit()
    background_tasks.add_task(run_csv_integration_sync, sync_run_id, preview.batchId, import_user_id)
    return {
        "syncRunId": sync_run_id,
        "importBatchId": import_response.batchId,
        "status": "pending",
        "totalRows": preview.totalRows,
        "validRows": int(prepared_batch.validCount or 0) if prepared_batch else preview.validRows,
        "invalidRows": int(prepared_batch.invalidCount or 0) if prepared_batch else preview.invalidRows,
        "duplicateRows": int(prepared_batch.duplicateCount or 0) if prepared_batch else preview.duplicateRows,
        "syncMode": sync_run.syncMode,
        "triggerType": sync_run.triggerType,
        "insertedRows": 0,
        "updatedRows": 0,
        "skippedRows": int(prepared_batch.duplicateCount or 0) if prepared_batch and connector.duplicateStrategy == "skip" else 0,
        "failedRows": int(prepared_batch.invalidCount or 0) if prepared_batch else preview.invalidRows,
        "integrationName": connector_name,
    }


async def await_request_bytes(request: Request) -> bytes:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_IMPORT_FILE_BYTES:
            raise HTTPException(status_code=413, detail="CSV file exceeds the 25 MB size limit")
    return bytes(raw)


def run_csv_integration_sync(sync_run_id: int, batch_id: int, user_id: int) -> None:
    db = SessionLocal()
    try:
        sync_run = db.query(IntegrationSyncRun).filter(IntegrationSyncRun.id == sync_run_id).first()
        if sync_run is None or sync_run.status != "pending":
            return
        sync_run.status = "running"
        sync_run.startedAt = datetime.now(timezone.utc)
        db.commit()
        company_id = sync_run.companyId
        connector_id = sync_run.connectorId
        db.close()

        run_import_job(batch_id, user_id)

        db = SessionLocal()
        sync_run = db.query(IntegrationSyncRun).filter(
            IntegrationSyncRun.id == sync_run_id,
            IntegrationSyncRun.companyId == company_id,
        ).first()
        batch = db.query(ImportBatch).filter(
            ImportBatch.id == batch_id,
            ImportBatch.companyId == company_id,
        ).first()
        if sync_run is None or batch is None:
            return
        sync_run.recordsProcessed = int(batch.totalRows or 0)
        sync_run.recordsInserted = int(batch.insertedCount or 0)
        sync_run.recordsUpdated = int(batch.updatedCount or 0)
        sync_run.recordsSkipped = int(batch.duplicateCount or 0)
        sync_run.recordsFailed = int(batch.failedCount or 0) + int(batch.invalidCount or 0)
        sync_run.recordsSynced = sync_run.recordsInserted + sync_run.recordsUpdated
        if batch.status == "failed":
            sync_run.status = "failed"
        elif batch.status == "cancelled":
            sync_run.status = "cancelled"
        elif batch.status == "completed_with_errors":
            sync_run.status = "completed_with_errors"
        else:
            sync_run.status = "completed"
        sync_run.failureReason = (
            "The CSV import could not be completed. Review the linked import batch for safe diagnostic details."
            if sync_run.status in {"failed", "completed_with_errors"}
            else None
        )
        sync_run.completedAt = datetime.now(timezone.utc)
        connector = db.query(IntegrationConnector).filter(
            IntegrationConnector.id == connector_id,
            IntegrationConnector.companyId == company_id,
        ).first()
        if connector and sync_run.status == "failed":
            connector.status = "failed"
            connector.updatedAt = datetime.now(timezone.utc)
        elif connector and connector.status == "failed":
            connector.status = "active"
            connector.updatedAt = datetime.now(timezone.utc)
        if connector and connector.status == "active":
            connector.nextSyncAt = (
                _next_schedule_at(
                    connector.syncFrequency or "manual",
                    connector.scheduleTime,
                    connector.scheduleDay,
                    datetime.now(timezone.utc),
                )
                if connector.scheduleEnabled and connector.encryptedSourceData else None
            )
        final_action = {
            "completed": "Integration Sync Completed",
            "completed_with_errors": "Integration Sync Completed with Errors",
            "failed": "Integration Sync Failed",
            "cancelled": "Integration Sync Cancelled",
        }[sync_run.status]
        _audit_sync_run(db, sync_run, connector, final_action)
        _notify_sync_outcome(db, sync_run, connector)
        db.commit()
    except Exception:
        db.rollback()
        logging.exception("Integration synchronization %s failed", sync_run_id)
        sync_run = db.query(IntegrationSyncRun).filter(
            IntegrationSyncRun.id == sync_run_id,
        ).first()
        if sync_run:
            sync_run.status = "failed"
            sync_run.failureReason = "The CSV synchronization failed unexpectedly. Review the linked import batch."
            sync_run.completedAt = datetime.now(timezone.utc)
            connector = db.query(IntegrationConnector).filter(
                IntegrationConnector.id == sync_run.connectorId,
                IntegrationConnector.companyId == sync_run.companyId,
            ).first()
            _audit_sync_run(db, sync_run, connector, "Integration Sync Failed")
            _notify_sync_outcome(db, sync_run, connector)
            db.commit()
    finally:
        db.close()
