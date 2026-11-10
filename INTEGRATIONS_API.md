# Integrations API

All endpoints require a bearer access token and enforce the authenticated user's company boundary. Dashboard viewing requires `data_integrations.view`; connector details and create/edit/delete/sync operations also require an administrator role and the corresponding permission. Credential values are encrypted before persistence and are never included in responses or audit descriptions.

## Supported sources

| Source | Configuration | Synchronization |
|---|---|---|
| CSV upload | Target module, duplicate strategy, and manual/hourly/daily/weekly frequency; scheduled runs can be enabled separately with a UTC execution time (and weekday for weekly schedules) | Implemented through the existing Data Imports validation, audit, and processing pipeline; one encrypted latest-upload snapshot is retained for scheduled replay |
| PostgreSQL | Host, port, database, schema/table, optional username and encrypted password | Not implemented; the connector is configuration-only |
| REST API | HTTPS/HTTP base URL, resource path, method, and selected authentication with encrypted credentials | Not implemented; the connector is configuration-only |

PostgreSQL and REST connectors may be enabled as configurations, but responses explicitly set `isOperational: false`; their configured synchronization frequency does not schedule work. CSV is the only operational connector. For scheduled CSV synchronization, the latest upload is retained encrypted at rest (one snapshot per connector) and replayed hourly, daily, or weekly. Daily and weekly execution times are in UTC; a weekly schedule defaults to Monday unless a weekday is specified. The schedule can be disabled without disabling manual synchronization. The scheduler checks for due runs every 30 seconds; runs are company-scoped and use the connector's saved field mapping. External source passwords/tokens and replay files are encrypted with an application key derived from `SECRET_KEY`; production deployments must configure a strong, persistent `SECRET_KEY`. Credential ciphertext is deferred in normal ORM queries; API responses expose only a `hasCredentials` flag, and credentials are only decrypted for connection testing or connector edits.

## Connection testing and field mapping

`POST /integrations/test-connection` accepts the current connector configuration without saving it. An optional `connectorId` lets an administrator test edits to an existing connector; if credentials are omitted, the saved encrypted credentials are used. The result is `{ success, message, details, testedAt }`. CSV tests verify that upload configuration and the target module are usable without creating an import. PostgreSQL tests use TLS, a short connection timeout, a read-only transaction, and `SELECT ... LIMIT 0` against the configured table to verify read permission. REST tests send a GET request only, do not follow redirects, and classify HTTP authentication/permission errors without returning response bodies. Private/reserved network addresses are blocked unless their exact hostname is listed in the backend `INTEGRATION_ALLOWED_HOSTS` environment variable. Credentials are only sent to HTTPS REST endpoints.

For CSV synchronization, the UI reads the uploaded file header and sample rows and presents a source-to-target mapping table. Required targets depend on the target module; type checks run on sample values before the sync action is enabled. Mappings use RetailPulse canonical target keys, for example:

```json
{
  "product_code": "sku",
  "product_title": "name",
  "stock_quantity": "stockquantity",
  "selling_price": "unitprice"
}
```

The mapping is sent in the `X-Field-Mapping` request header as JSON. The backend independently checks that source fields exist, targets are supported, target mappings are unique, and all required target groups are covered before transforming the CSV and invoking the existing import validator. The successful sync saves the field mapping on the connector; raw field values and credentials are not copied into the mapping configuration.

## Endpoints

| Method and path | Purpose | Permission |
|---|---|---|
| `GET /integrations` | List configured connectors and operational state for the authenticated company | `view` |
| `GET /integrations/dashboard` | Company-scoped KPI and connector list | `view` |
| `GET /integrations/sync-runs` | Company-scoped synchronization history; supports `offset`, `limit` (max 200), `integrationId`, and `status` | `view` |
| `GET /integrations/{connector_id}/sync-runs` | List one company's connector history; supports `offset`, `limit`, and `status` | `view` |
| `GET /integrations/sync-runs/{sync_run_id}` | View synchronization totals, failure summary, and linked import summary | `view` |
| `GET /integrations/sync-runs/{sync_run_id}/errors` | List safe row-level failure details | `view` |
| `GET /integrations/sync-runs/{sync_run_id}/errors/export` | Download a CSV containing source ID, row, category, safe message, and processing status | `view` |
| `POST /integrations/sync-runs/{sync_run_id}/retry` | Revalidate and retry only rows marked failed; successful rows are not replayed | Administrator + `create` |
| `POST /integrations` | Create connector configuration | Administrator + `create` |
| `POST /integrations/test-connection` | Test saved or unsaved configuration without importing data | Administrator + `update` |
| `GET /integrations/{connector_id}` | View details; credentials are redacted | `view` |
| `PATCH /integrations/{connector_id}` | Edit configuration and enable/disable | Administrator + `update` |
| `POST /integrations/{connector_id}/enable` | Enable a connector | Administrator + `update` |
| `POST /integrations/{connector_id}/disable` | Disable a connector without deleting schedule configuration | Administrator + `update` |
| `PUT /integrations/{connector_id}/field-mapping` | Validate and persist CSV source-to-target mapping | Administrator + `update` |
| `PUT /integrations/{connector_id}/schedule` | Configure/disable an hourly, daily, or weekly CSV schedule | Administrator + `update` |
| `DELETE /integrations/{connector_id}` | Delete configuration and its sync history | Administrator + `delete` |
| `POST /integrations/{connector_id}/sync` | Upload and synchronize a CSV | Administrator + `create` |

The dashboard returns `{ totalIntegrations, activeIntegrations, inactiveIntegrations, failedIntegrations, lastSyncAt, pendingSyncJobs, recordsSynced, recordsFailed, integrations }`. Each row includes connector ID/name/source, enabled status, `isOperational`, target module, frequency, schedule state/time/day, next scheduled run, previous run status/time, pending jobs, and success/failure counts. Metrics are derived from persisted connectors and sync runs, scoped to the caller's company.

The connector list returns those company-scoped integration rows without the aggregate KPIs. Connector history is an alias for the paginated sync-runs API filtered by connector ID. Connector IDs and sync-run IDs are always resolved within the authenticated user's company.

## Connector configuration

`POST /integrations` accepts:

```json
{
  "name": "Product CSV feed",
  "dataSourceType": "csv",
  "connectionConfiguration": { "mode": "upload" },
  "authenticationMethod": "none",
  "credentials": {},
  "targetModule": "products",
  "syncFrequency": "manual",
  "status": "active"
}
```

`dataSourceType` is `csv`, `postgresql`, or `rest_api`. `targetModule` is `products`, `inventory`, `sales`, or `customers`. Status is `active` (enabled) or `inactive` (disabled). CSV supports `manual`, `hourly`, `daily`, and `weekly`; scheduled runs begin after a successful manual upload. PostgreSQL and REST schedules remain configuration-only.

Scheduled connectors accept `scheduleEnabled`, `scheduleTime` (`HH:mm`, UTC), and `scheduleDay` (0=Monday through 6=Sunday). `scheduleEnabled` is independent of the overall connector `status`; a disabled schedule does not prevent manual CSV sync. Manual frequency cannot have a schedule.

`PUT /integrations/{connector_id}/field-mapping` accepts `{ "fieldMappings": { "source_column": "canonical_target" } }`. The endpoint is currently operational for CSV connectors; it validates the required target groups and one-to-one mapping before persisting, and rejects changes while synchronization is running. Sync upload can also provide `X-Field-Mapping`; a successful upload persists that validated mapping.

`PUT /integrations/{connector_id}/schedule` accepts `syncFrequency`, `scheduleEnabled`, `scheduleTime`, and optional `scheduleDay`. `POST .../enable` and `POST .../disable` update connector availability while retaining schedule configuration; scheduling itself can be separately disabled through the schedule endpoint. All three are administrator-only and write audit history.

`duplicateStrategy` controls matching rows:

| Strategy | Behavior |
|---|---|
| `insert` | Insert new records; matching duplicates are rejected and counted as failed. Not available for inventory because inventory synchronization updates existing products. |
| `update` | Update explicitly mapped fields for matching products by SKU, customers by email, and inventory quantities for their product SKU. Sales updates are prohibited because replaying a sale can repeat stock and revenue effects. |
| `skip` | Do not modify matching duplicates. Incremental inventory runs skip existing product rows; new product/customer rows are inserted. |
| `reject` | Reject duplicate rows while continuing with other valid rows; the run is completed with errors when any rows are rejected. |

Invalid rows are retained in the linked import batch and are not written. New customer records match by email; sales invoices are insert-only/idempotent and never updated. Initial synchronization is the first successful connector run; subsequent runs are marked incremental and apply the configured match strategy. For scheduled runs the full saved CSV snapshot is validated each time, while duplicate handling prevents unintended writes to already-imported records.

PostgreSQL configuration accepts `host`, `port`, `database`, and optional `schema`, `table`, and `username`. Passwords belong in `credentials`, not in connection configuration. REST configuration accepts `baseUrl`, optional `resourcePath`, and `httpMethod` (`GET` or `POST`). Supported REST authentication methods are `none`, `bearer_token`, `api_key`, and `basic`; credentials are sent separately as token/API key or username/password values.

Create and detail responses contain `connectionConfiguration`, `authenticationMethod`, `hasCredentials`, `createdBy`, and timestamps, but never return credential material. `PATCH /integrations/{connector_id}` accepts any editable configuration fields; omitted credentials are preserved, `credentials` replaces them, and `{ "clearCredentials": true }` removes them. Credentials and `clearCredentials` cannot be provided together. Source type cannot be changed after creation.

## CSV synchronization

Upload raw CSV bytes with `Content-Type: text/csv` and a `fileName` query parameter:

`POST /integrations/{connector_id}/sync?fileName=products.csv`

The server validates size and content type, checks the field mapping and required targets, creates a preview for the configured target, queues the existing import worker, and records the linked synchronization run. The `202` response contains `syncRunId`, `importBatchId`, `status`, row validation counts, mode, trigger type, and inserted/updated/skipped/failed counters. Imports use the existing entity validators, business-key duplicate handling, audit/system-job tracking, and post-import data-quality/reconciliation hook. Data-quality reconciliation errors are logged by the existing import workflow rather than bypassing import validation. Import details remain available through the existing `/imports/{batch_id}` endpoint. A manual upload with a content hash already used manually by the same connector is rejected; scheduled replay is allowed and relies on the selected duplicate strategy. CSV is limited to 25 MB. Only the newest upload is retained, encrypted, for scheduled replay.

The synchronization history list returns `{ total, items }`. Each item includes the sync ID, integration, triggering user/type, initial/incremental mode, start/completion/duration, processed/inserted/updated/skipped/failed counts, status, and a safe failure summary. Detail responses add import batch status and row totals without returning raw row data. Status values are `pending`, `running`, `completed`, `completed_with_errors`, `failed`, and `cancelled`.

The failed-record endpoint returns `{ syncRunId, total, items }`; each item contains `sourceRecordIdentifier`, `rowNumber`, `errorCategory`, `errorMessage`, and `processingStatus`. It does not expose raw imported row data. CSV export contains the same safe diagnostic fields. Retry creates a new import batch and sync run from only records with `failed` status, revalidates them through the regular import validator, and applies the connector's duplicate strategy against current business records. Invalid, duplicate, cancelled, and previously successful rows are not retried.

The sync runs asynchronously after the API response. Run status and record totals are reflected in the dashboard. The Audit Logs module receives company-scoped records with actor, action, connector resource ID, and timestamp for connector create/update/enable/disable/delete, saved connection tests, and sync start/completion/failure/cancellation (including retries and scheduled runs). Audit descriptions contain only safe identifiers and status summaries, never configuration or secret values. Integration notifications are deduplicated by sync-run ID for completed, completed-with-errors, and failed outcomes; skipped schedule occurrences are deduplicated by connector and scheduled time. Saved-connector connection test failures create one unresolved alert per connector; a later successful test resolves it and emits a recovery notice. A connector cannot be deleted while a sync is pending or running.

## Errors

| Status | Meaning |
|---|---|
| `401` | Missing, invalid, or expired token |
| `403` | User lacks the required permission or administrator role |
| `404` | Connector does not exist in the authenticated company |
| `409` | Duplicate name/file, unsupported source sync, disabled connector, or sync still running during deletion |
| `413` | CSV file exceeds 25 MB |
| `415` | Sync body is not CSV |
| `422` | Invalid configuration, source, target, frequency, or authentication fields |
| `500` | Invalid stored connector/sync data or unexpected failure |
