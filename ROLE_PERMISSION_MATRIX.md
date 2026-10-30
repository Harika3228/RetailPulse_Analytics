# Role Permission Matrix

The Data Governance page provides an administrator-only, company-scoped role matrix.
`GET /governance/roles/permissions` returns:

- roles currently assigned to company users, plus built-in `admin`, `company_admin`,
  `super_admin`, `analyst`, and `viewer` roles;
- supported module keys and actions (`view`, `create`, `update`, `delete`, `export`,
  `approve`, `manage_access`);
- the configured actions for each role/module pair and the most recent configuration
  timestamp.

`GET /governance/roles` returns the same role-and-permission catalog for clients
that need a role-list endpoint. Both APIs require an authenticated administrator
and return only roles and settings for the current company.

`PUT /governance/roles/{role}/permissions` accepts the complete matrix for one role:

```json
{
  "reason": "Grant the analyst team product lookup access.",
  "permissions": {
    "dashboard_analytics": ["view"],
    "products": ["view", "update"],
    "inventory": [],
    "sales": [],
    "customers": [],
    "reports": ["view"],
    "data_imports": [],
    "workflows_approvals": [],
    "audit_logs": [],
    "system_monitoring": [],
    "data_governance": []
  }
}
```

The request must include every supported module and only supported actions. The API
requires an authenticated admin, rejects unknown company roles, persists the setting
per company/role, and records the change in the audit log. Built-in administrator
roles cannot be restricted and always display full access.

## User access assignments and requests

`GET /governance/users` lists only users in the authenticated administrator's company,
including each user's resolved role permissions and the actor/time of the latest
access-assignment audit record. `PATCH /governance/users/{user_id}/access` accepts
`{"role":"analyst","status":"active","reason":"Role responsibilities changed"}` or
an `inactive` status. Assignments are company-scoped and audited with previous and
new role/status values and the supplied reason. Administrators cannot change their
own access; only a super administrator can modify administrator accounts or assign
an administrator role, and the last active administrator cannot be deactivated.

Users can request a role through the existing approval service using
`POST /workflows` with `requestType: "role_access_change"`, their own user ID as
`relatedRecord`, and `requestedChanges: {"role":"analyst"}`. Include a business
`reason`. Requests are company-scoped and require approval; pending requests do not
change the user's role. Approval applies the role change in the same transaction as
the request decision, records approval history/audit information, and notifies the
requester. Rejection requires the normal reviewer comment and leaves access unchanged.
Users can track or cancel their own request through the existing workflow endpoints;
authorized reviewers use the standard approval queue and decision endpoints.

## Access review and permission history

`GET /governance/access-reviews` lists current company users, effective permissions,
last access update, and the latest review result. Administrators can append a review
with `POST /governance/access-reviews/{user_id}`. A review records its reviewer,
timestamp, comments, status (`reviewed` or `flagged`), and flagged permissions.
`GET /governance/access-reviews/history` returns the immutable review timeline
(optionally filtered by `userId`). These records are company-scoped and the API
provides no edit or delete operation.

To request role changes or access removal based on a review, administrators can
submit `POST /governance/access-reviews/{user_id}/workflow` with either a `role` or
`status: "inactive"` and a reason. The request is created in the existing
`role_access_change` approval workflow. The target user's role/status remains
unchanged until an authorized approver approves it; approval and the access update
are committed together. Administrator account changes continue to require a
super-administrator approver, and the last active administrator is protected.
The affected user receives a notification when the request is submitted, approved,
rejected, or cancelled, in addition to requester and approver notifications.

`GET /governance/access-requests` exposes access request history using the existing
workflow records. A user can query their own submissions with `scope=submitted`;
only administrators may request `scope=all`. Standard workflow review and decisions
remain available through `/workflows`, including approval history at
`/workflows/{request_id}/history`.

`GET /governance/permission-changes` retrieves the immutable permission-change audit
history with `limit` (1-500), `offset`, and optional company-local `userId` filters.
It returns actor, target, previous/new values, reason, timestamp, and related access
request ID where recorded. Access-review comments and decisions are available from
`GET /governance/access-reviews/history`.

Access review actions and permission changes are also written to the existing
company-scoped audit log. User assignments and role permission matrix updates record
before/after state, the actor, timestamp, reason, and the related request ID when
the change came from workflow approval. Clearing ordinary audit logs preserves
access-review, user-access, and role-permission history. Audit records remain
read-only through normal application operations.

## Authorization and data visibility

The persisted matrix is enforced as a backend permission gate for the application API.
Module paths are mapped to view/create/update/delete/export/approve/manage-access
actions and checked against the current company role on every request; mapped APIs
fail closed with HTTP 401 when authentication is missing. A denied operation returns
HTTP 403; existing endpoint-specific checks continue to apply as additional
safeguards. Company-scoped queries and resource lookups remain responsible for
preventing cross-company access.

`GET /auth/me` and the login/refresh user payload include the current effective
permissions. Frontend routes and navigation use those permissions to hide modules
without access, while backend checks remain authoritative. Permission configuration
changes apply to the next API request because the server loads the current matrix.
User role assignments likewise affect backend checks immediately; inactive accounts
are denied access-token and refresh-token authentication.

Customer contact details are treated as sensitive: dashboard analytics omit customer
email addresses for non-administrator roles, and the sales customer selector omits
email and phone fields and does not search on those fields for non-administrators.
Customer profile endpoints continue to require an administrator, and customer exports
remain separately permission-gated.

Initial defaults mirror the application's broad role model where it is identifiable:
administrator roles receive full access; analysts receive dashboard/analytics,
inventory, sales (including the existing transaction deletion capability), reports,
and workflow permissions; viewers receive dashboard, reports, and workflow
view/request permissions. Unknown assigned roles start with no permissions until
configured. These defaults describe the matrix and do not replace endpoint
authorization.
