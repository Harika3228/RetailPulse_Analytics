# System Health API

All timestamps are ISO 8601 date-times. Unless stated otherwise, monitoring endpoints require `Authorization: Bearer <access-token>`, an active user with an administrator role (`admin`, `company_admin`, or `super_admin`), and return only records belonging to the authenticated user's company. The backend checks these permissions and company boundaries on every request.

## Endpoints

| Method and path | Purpose | Permission |
|---|---|---|
| `GET /api/health` | Component health for probes; returns `503` when overall status is unavailable | Public; intentionally limited operational detail |
| `GET /system-health` | Company-scoped overview and minute-level API trend | Administrator |
| `GET /system-health/requests` | Filtered, sortable, paginated API request samples | Administrator |
| `GET /system-health/jobs` | Filtered, paginated background job list | Administrator |
| `GET /system-health/jobs/{job_id}` | Job details and related import, reconciliation, or report counts | Administrator |
| `POST /system-health/jobs/{job_id}/retry` | Queue a safe retry for an eligible failed import | Administrator |
| `POST /system-health/jobs/{job_id}/cancel` | Request cancellation of an eligible import | Administrator |
| `GET /system-health/errors` | Filtered, paginated incidents | Administrator |
| `GET /system-health/errors/{error_id}` | Incident details | Administrator |
| `GET /system-health/errors/{error_id}/timeline` | Incident timeline | Administrator |
| `PATCH /system-health/errors/{error_id}` | Change incident status and add required notes | Administrator |
| `GET /system-health/thresholds` | Read current company monitoring thresholds | Administrator |
| `PUT /system-health/thresholds` | Update company monitoring thresholds | Administrator |

## Request parameters

### `GET /api/health`

No query parameters or authentication are required. Returns component status (`healthy`, `degraded`, `unavailable`, or `not_configured`), a safe message, and `checkedAt`. It does not include credentials, connection strings, or stack traces.

### `GET /system-health`

No query parameters. Returns overall status, 24-hour API availability and request totals, response-time average, background job counters, recent safe error summaries, the latest health-check timestamp, and `apiTrend`. Trend values are grouped by minute from recorded API aggregates; successful requests are counted even though their individual detail rows are sampled.

Example trend item:

```json
{
  "timestamp": "2026-10-15T04:40:00Z",
  "requestCount": 24,
  "serverErrorCount": 1,
  "averageResponseTimeMs": 83.42
}
```

### `GET /system-health/requests`

| Query | Type | Default / constraints |
|---|---|---|
| `endpoint` | string | Optional route substring |
| `search` | string | Optional endpoint/method/error summary substring |
| `status_code` | integer | Optional; 100–599 |
| `start_time`, `end_time` | date-time | Optional inclusive timestamp bounds; start must not be after end |
| `outcome` | string | Optional: `success` (<400) or `failure` (>=400) |
| `sortBy` | string | `timestamp` (default), `endpoint`, `statusCode`, `responseTimeMs` |
| `sortOrder` | string | `desc` (default) or `asc` |
| `page` | integer | 1 (default), minimum 1 |
| `pageSize` | integer | 25 (default), 1–100 |

Returns `{ items, total, page, pageSize }`. Items contain route template, method, HTTP status, elapsed milliseconds, timestamp, outcome, and a generic safe error classification. All failures and a 5% sample of successful calls are retained for seven days; do not interpret the detail table as a complete request log.

### `GET /system-health/jobs`

Optional query parameters: `jobType`, `status` (`pending`, `running`, `completed`, `failed`, `cancelled`), `search`, `start_time`, `end_time`, `page` (default 1), and `pageSize` (default 25; maximum 100). Date bounds are inclusive and start must not follow end. Returns `{ items, total, page, pageSize }`; list items include `canRetry` and `canCancel` eligibility flags.

### Job details and actions

`GET /system-health/jobs/{job_id}` returns a job item and source-specific execution counts where available. `POST /system-health/jobs/{job_id}/cancel` and `POST /system-health/jobs/{job_id}/retry` have no body.

Cancellation currently applies to pending or running import jobs and is cooperative: the worker honors the request at its next safe checkpoint. Other job types return `409`.

Retry currently applies only to failed imports whose batch has no inserted or updated rows and has failed rows eligible for replay. The failed rows are reset and queued within the same database transaction; the endpoint audits the request and enqueues the worker after commit. Other jobs, and imports with any prior applied rows, return `409` to avoid unsafe duplicate business changes. Scheduled report definitions exist, but this application does not currently have a scheduler worker to execute or retry them.

Successful job responses use the job structure documented above. A retry returns the new pending retry job; cancellation returns the current job structure with a `message`.

### `GET /system-health/errors`

Optional query parameters: `severity` (`critical`, `high`, `medium`, `low`), `component`, `status` (`open`, `investigating`, `resolved`), `start_time`, `end_time`, `search`, `page` (default 1), and `pageSize` (default 25; maximum 100). Returns `{ items, total, page, pageSize }`. Incident entries include ID, category, component, endpoint/job label, latest occurrence timestamp, severity, occurrence count, status, and resolution notes.

`GET /system-health/errors/{error_id}` returns an incident with its first/latest occurrence timestamps and safe identifying details. `GET /system-health/errors/{error_id}/timeline` returns ordered events with action, previous/new status, notes, actor, and timestamp.

`PATCH /system-health/errors/{error_id}` accepts:

```json
{
  "status": "investigating",
  "investigationNotes": "Checking the import worker backlog."
}
```

`status` is required and must be `open`, `investigating`, or `resolved`. `investigationNotes` is required for `investigating`; `resolutionNotes` is required for `resolved`. Each note is optional otherwise and is limited to 2,000 characters. The response is the updated incident.

### Monitoring thresholds

`GET /system-health/thresholds` returns current values. `PUT /system-health/thresholds` requires all fields:

```json
{
  "apiErrorRatePercent": 5,
  "averageResponseTimeMs": 1000,
  "sampleWindowMinutes": 5,
  "minimumRequestCount": 10,
  "repeatedFailureCount": 3
}
```

Ranges are respectively 0.1–100%, greater than 0–120,000 ms, 1–1,440 minutes, 1–10,000 requests, and 1–1,000 failures. Changes are company-scoped and audited.

## Response and error behavior

List responses use `{ items, total, page, pageSize }`; details return the documented object directly. Validation errors use FastAPI's `422` response. Common errors:

| Status | Meaning |
|---|---|
| `401` | Missing, invalid, or expired access token |
| `403` | Authenticated user is not authorized for monitoring administration |
| `404` | Job or incident does not exist in the caller's company |
| `409` | Invalid state transition, unsupported action, or unsafe retry |
| `422` | Invalid query parameter, status, notes, or threshold value |
| `503` | Public `/api/health` endpoint reports overall system unavailable |

Unexpected server failures use a generic response; stack traces and sensitive request data are not returned by these APIs. Company records are never selected by client-supplied company IDs.

## Data sources and refresh

Monitoring is populated from real application operations: API middleware, import workers, reconciliation executions, generated report history, incident transitions, notification delivery, and audit events. Scheduled reports are definitions only until a scheduler/worker exists. The frontend polls overview and API samples every 15–30 seconds and invalidates relevant queries after job, incident, or threshold actions; no full-page reload is needed. Component health is checked by `GET /api/health`; the latest successful database writes are retained by component.

Retention limits: individual API samples 7 days, minute aggregates 30 days, terminal jobs 180 days, and resolved incidents/timelines/incident notifications 365 days. Open incidents and active jobs are retained.
