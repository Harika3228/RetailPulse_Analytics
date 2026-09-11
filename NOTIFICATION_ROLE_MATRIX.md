# Notification Role Matrix

Notifications are filtered on the backend by company, target user, and target role. The frontend does not enforce delivery isolation.

| Notification | Admin / Company Admin / Super Admin | Analyst | Viewer |
|---|---:|---:|---:|
| Stockout and zero-stock alerts | Yes | Yes, when published as an inventory insight | No unless explicitly targeted |
| Low-stock and reorder alerts | Yes | Yes, when published as an inventory insight | No unless explicitly targeted |
| Overstock alerts | Yes | Yes | No unless explicitly targeted |
| Import completed | Yes | No by default | No |
| Import failed | Yes | No by default | No |
| Sales alerts | Yes | Yes | No unless explicitly targeted |
| Forecast and analytics alerts | Yes | Yes | No unless explicitly targeted |
| System alerts | Yes | Yes when relevant | No unless explicitly targeted |

## Priority Rules

- **Critical**: zero stock, predicted stockout, import failure.
- **High**: demand exceeds available inventory, import completed with errors.
- **Medium**: stock at or below the calculated reorder point, overstock.
- **Low**: successful imports, sales activity, and general information.

A notification with `targetRole = NULL` is company-wide. A notification with `targetRole = admin` is visible to `admin`, `company_admin`, and `super_admin`. A `userId` target further restricts delivery to that authenticated user.
