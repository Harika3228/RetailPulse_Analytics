import json
import unittest
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.controllers.governance_controller import ROLE_PERMISSION_MODULES
from backend.auth_utils import create_access_token
from backend.models import (
    AccessReviewRecord,
    ApprovalHistoryRecord,
    ApprovalRequestRecord,
    AuditLog,
    Company,
    Notification,
    RolePermissionConfiguration,
    User,
)


class GovernanceOverviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()
        login = self.client.post(
            "/auth/login",
            json={"email": "admin@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        self.company_admin = self.db.query(User).filter_by(
            email="admin@retailpulse.com"
        ).one()
        self.user_ids = []
        self.approval_ids = []
        self.audit_ids = []
        self.role_permission_ids = []
        self.access_review_ids = []
        self.company_ids = []

    def tearDown(self):
        if self.approval_ids:
            self.db.query(ApprovalHistoryRecord).filter(
                ApprovalHistoryRecord.requestId.in_(self.approval_ids)
            ).delete(synchronize_session=False)
            self.db.query(ApprovalRequestRecord).filter(
                ApprovalRequestRecord.id.in_(self.approval_ids)
            ).delete(synchronize_session=False)
        if self.access_review_ids:
            self.db.query(AccessReviewRecord).filter(
                AccessReviewRecord.id.in_(self.access_review_ids)
            ).delete(synchronize_session=False)
        if self.approval_ids:
            self.db.query(Notification).filter(
                Notification.resourceType == "Approval Request",
                Notification.resourceId.in_([str(request_id) for request_id in self.approval_ids]),
            ).delete(synchronize_session=False)
        if self.audit_ids:
            self.db.query(AuditLog).filter(
                AuditLog.id.in_(self.audit_ids)
            ).delete(synchronize_session=False)
        if self.role_permission_ids:
            self.db.query(RolePermissionConfiguration).filter(
                RolePermissionConfiguration.id.in_(self.role_permission_ids)
            ).delete(synchronize_session=False)
        if self.user_ids:
            self.db.query(User).filter(User.id.in_(self.user_ids)).delete(
                synchronize_session=False
            )
        if self.company_ids:
            self.db.query(AuditLog).filter(
                AuditLog.companyId.in_(self.company_ids)
            ).delete(synchronize_session=False)
            self.db.query(User).filter(
                User.companyId.in_(self.company_ids)
            ).delete(synchronize_session=False)
            self.db.query(Company).filter(
                Company.id.in_(self.company_ids)
            ).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_overview_uses_company_user_role_approval_and_audit_data(self):
        suffix = uuid.uuid4().hex[:10]
        now = datetime.now(timezone.utc)
        same_company_users = [
            User(
                companyId=self.company_admin.companyId,
                name="Governance Active",
                email=f"governance-active-{suffix}@example.com",
                role="governance_test_role",
                status="active",
            ),
            User(
                companyId=self.company_admin.companyId,
                name="Governance Inactive",
                email=f"governance-inactive-{suffix}@example.com",
                role="viewer",
                status="inactive",
            ),
            User(
                companyId=self.company_admin.companyId,
                name="Governance Elevated",
                email=f"governance-elevated-{suffix}@example.com",
                role="admin",
                status="active",
            ),
            User(
                companyId=self.company_admin.companyId + 700000,
                name="Other Company User",
                email=f"governance-other-{suffix}@example.com",
                role="other_company_role",
                status="active",
            ),
        ]
        self.db.add_all(same_company_users)
        self.db.flush()
        self.user_ids.extend(user.id for user in same_company_users)
        access_request = ApprovalRequestRecord(
            companyId=self.company_admin.companyId,
            requesterId=same_company_users[0].id,
            requestType="access_request",
            title="Access request",
            description="Request access to inventory",
            reason="Role responsibilities",
            relatedRecord="Inventory",
            status="pending_approval",
            createdAt=now,
            updatedAt=now,
        )
        unrelated_request = ApprovalRequestRecord(
            companyId=self.company_admin.companyId,
            requesterId=same_company_users[0].id,
            requestType="stock_adjustment",
            title="Stock adjustment",
            description="Adjust stock",
            reason="Correction",
            relatedRecord="Product #1",
            status="pending_approval",
            createdAt=now,
            updatedAt=now,
        )
        role_change = AuditLog(
            companyId=self.company_admin.companyId,
            userId=self.company_admin.id,
            user=self.company_admin.email,
            action="User Role Changed",
            resourceType="User",
            resourceId=str(same_company_users[0].id),
            description="Role changed from viewer to governance_test_role.",
            createdAt=now,
            timestamp=now,
            company=str(self.company_admin.companyId),
        )
        access_review = AuditLog(
            companyId=self.company_admin.companyId,
            userId=self.company_admin.id,
            user=self.company_admin.email,
            action="Access Review Completed",
            resourceType="Company",
            resourceId=str(self.company_admin.companyId),
            description="Quarterly user access review completed.",
            createdAt=now,
            timestamp=now,
            company=str(self.company_admin.companyId),
        )
        self.db.add_all([access_request, unrelated_request, role_change, access_review])
        self.db.flush()
        self.approval_ids.extend([access_request.id, unrelated_request.id])
        self.audit_ids.extend([role_change.id, access_review.id])
        self.db.commit()

        response = self.client.get(
            "/governance/overview",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        overview = response.json()
        self.assertEqual(
            overview["totalUsers"],
            self.db.query(User).filter(
                User.companyId == self.company_admin.companyId
            ).count(),
        )
        self.assertEqual(
            overview["activeUsers"],
            self.db.query(User).filter(
                User.companyId == self.company_admin.companyId,
                User.status == "active",
            ).count(),
        )
        self.assertEqual(
            overview["inactiveUsers"],
            overview["totalUsers"] - overview["activeUsers"],
        )
        self.assertEqual(
            overview["totalRoles"],
            self.db.query(User.role).filter(
                User.companyId == self.company_admin.companyId,
                User.role.isnot(None),
                User.role != "",
            ).distinct().count(),
        )
        self.assertEqual(overview["pendingAccessRequests"], 1)
        self.assertGreaterEqual(overview["elevatedPermissionUsers"], 1)
        self.assertEqual(
            overview["lastAccessReviewAt"],
            access_review.createdAt.isoformat(),
        )
        self.assertTrue(any(
            item["id"] == role_change.id
            for item in overview["recentPermissionChanges"]
        ))

    def test_overview_requires_admin_and_authentication(self):
        self.assertEqual(self.client.get("/governance/overview").status_code, 401)
        preflight = self.client.options(
            "/dashboard/analytics",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertEqual(preflight.status_code, 200, preflight.text)
        self.assertEqual(
            preflight.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )
        self.assertIn("GET", preflight.headers.get("access-control-allow-methods", ""))
        self.assertIn("authorization", preflight.headers.get("access-control-allow-headers", "").lower())
        unauthenticated_matrix = self.client.get("/governance/roles/permissions")
        self.assertEqual(unauthenticated_matrix.status_code, 401)
        self.assertEqual(
            unauthenticated_matrix.headers.get("www-authenticate"),
            "Bearer",
        )
        login = self.client.post(
            "/auth/login",
            json={"email": "analyst@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        response = self.client.get(
            "/governance/overview",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_role_matrix_shows_current_roles_and_protects_admin_full_access(self):
        response = self.client.get(
            "/governance/roles/permissions",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        matrix = response.json()
        roles_response = self.client.get(
            "/governance/roles",
            headers=self.admin_headers,
        )
        self.assertEqual(roles_response.status_code, 200, roles_response.text)
        self.assertEqual(roles_response.json()["roles"], matrix["roles"])
        self.assertIn("analyst", matrix["roles"])
        self.assertIn("viewer", matrix["roles"])
        self.assertEqual(set(matrix["modules"]), set(ROLE_PERMISSION_MODULES))
        self.assertEqual(
            sorted(matrix["permissions"]["company_admin"]["data_governance"]),
            ["approve", "create", "delete", "export", "manage_access", "update", "view"],
        )
        self.assertIn("view", matrix["permissions"]["analyst"]["dashboard_analytics"])

        payload = {
            "reason": "Confirm administrator roles cannot be reconfigured.",
            "permissions": {
                module: ["view"] if module == "products" else []
                for module in ROLE_PERMISSION_MODULES
            }
        }
        protected = self.client.put(
            "/governance/roles/company_admin/permissions",
            json=payload,
            headers=self.admin_headers,
        )
        self.assertEqual(protected.status_code, 409, protected.text)

    def test_admin_can_configure_known_non_admin_role_and_audit_change(self):
        suffix = uuid.uuid4().hex[:10]
        role_user = User(
            companyId=self.company_admin.companyId,
            name="Custom Governance Role",
            email=f"governance-custom-{suffix}@example.com",
            role="custom_governance_role",
            status="active",
        )
        self.db.add(role_user)
        self.db.commit()
        self.user_ids.append(role_user.id)
        payload = {
            "reason": "Configure product view access for the test role.",
            "permissions": {
                module: ["view"] if module == "products" else []
                for module in ROLE_PERMISSION_MODULES
            }
        }
        updated = self.client.put(
            "/governance/roles/custom_governance_role/permissions",
            json=payload,
            headers=self.admin_headers,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        role_matrix = updated.json()
        self.assertEqual(
            role_matrix["permissions"]["custom_governance_role"]["products"],
            ["view"],
        )
        configuration = self.db.query(RolePermissionConfiguration).filter_by(
            companyId=self.company_admin.companyId,
            role="custom_governance_role",
        ).one()
        self.role_permission_ids.append(configuration.id)
        self.assertEqual(configuration.updatedByUserId, self.company_admin.id)
        audit = self.db.query(AuditLog).filter(
            AuditLog.companyId == self.company_admin.companyId,
            AuditLog.action == "Role Permissions Updated",
            AuditLog.resourceId == "custom_governance_role",
        ).one()
        self.audit_ids.append(audit.id)

        invalid = {
            "reason": "Reject unsupported permission actions.",
            "permissions": {
                module: ["unknown_action"] if module == "products" else []
                for module in ROLE_PERMISSION_MODULES
            }
        }
        rejected = self.client.put(
            "/governance/roles/custom_governance_role/permissions",
            json=invalid,
            headers=self.admin_headers,
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)

    def test_role_permission_configuration_is_company_scoped(self):
        foreign_configuration = RolePermissionConfiguration(
            companyId=self.company_admin.companyId + 900000,
            role="analyst",
            permissions='{"products":["delete"]}',
        )
        self.db.add(foreign_configuration)
        self.db.commit()
        self.role_permission_ids.append(foreign_configuration.id)

        response = self.client.get(
            "/governance/roles/permissions",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(
            "delete",
            response.json()["permissions"]["analyst"]["products"],
        )

    def test_user_access_updates_are_company_scoped_audited_and_effective(self):
        managed_user = User(
            companyId=self.company_admin.companyId,
            name="Governance User Access Test",
            email=f"governance-access-{uuid.uuid4().hex[:10]}@example.com",
            role="viewer",
            status="active",
        )
        foreign_user = User(
            companyId=self.company_admin.companyId + 900001,
            name="Foreign Governance User",
            email=f"foreign-governance-{uuid.uuid4().hex[:10]}@example.com",
            role="viewer",
            status="active",
        )
        self.db.add_all([managed_user, foreign_user])
        self.db.commit()
        self.user_ids.extend([managed_user.id, foreign_user.id])
        managed_headers = {
            "Authorization": "Bearer " + create_access_token({
                "sub": managed_user.email,
                "company_id": managed_user.companyId,
            })
        }
        users_response = self.client.get("/governance/users", headers=self.admin_headers)
        self.assertEqual(users_response.status_code, 200, users_response.text)
        listed_user = next(item for item in users_response.json() if item["id"] == managed_user.id)
        self.assertIn("permissions", listed_user)
        self.assertEqual(listed_user["role"], "viewer")

        changed = self.client.patch(
            f"/governance/users/{managed_user.id}/access",
            headers=self.admin_headers,
            json={
                "role": "analyst",
                "status": "active",
                "reason": "The user now performs analysis work.",
            },
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["role"], "analyst")
        self.assertEqual(
            changed.json()["accessUpdatedBy"],
            self.company_admin.name or self.company_admin.email,
        )
        overview = self.client.get("/governance/overview", headers=self.admin_headers)
        self.assertEqual(overview.status_code, 200, overview.text)
        access_change = next(
            item for item in overview.json()["recentPermissionChanges"]
            if item["target"] == managed_user.email
        )
        self.assertEqual(access_change["previous"], {"role": "viewer", "status": "active"})
        self.assertEqual(access_change["newValue"], {"role": "analyst", "status": "active"})
        self.assertEqual(access_change["reason"], "The user now performs analysis work.")
        history = self.client.get(
            f"/governance/permission-changes?userId={managed_user.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertTrue(any(
            entry["target"] == managed_user.email
            and entry["reason"] == "The user now performs analysis work."
            for entry in history.json()
        ))
        me = self.client.get("/auth/me", headers=managed_headers)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["role"], "analyst")
        own_request = self.client.post(
            "/workflows",
            headers=managed_headers,
            json={
                "requestType": "role_access_change",
                "relatedRecord": str(managed_user.id),
                "requestedChanges": {"role": "viewer"},
                "reason": "My duties no longer require analyst access.",
            },
        )
        self.assertEqual(own_request.status_code, 200, own_request.text)
        self.approval_ids.append(own_request.json()["id"])
        own_request_history = self.client.get(
            "/governance/access-requests?scope=submitted",
            headers=managed_headers,
        )
        self.assertEqual(own_request_history.status_code, 200, own_request_history.text)
        self.assertEqual([item["id"] for item in own_request_history.json()], [own_request.json()["id"]])
        forbidden_company_history = self.client.get(
            "/governance/access-requests?scope=all",
            headers=managed_headers,
        )
        self.assertEqual(forbidden_company_history.status_code, 403, forbidden_company_history.text)

        foreign_change = self.client.patch(
            f"/governance/users/{foreign_user.id}/access",
            headers=self.admin_headers,
            json={
                "role": "analyst",
                "status": "active",
                "reason": "Foreign company access must remain isolated.",
            },
        )
        self.assertEqual(foreign_change.status_code, 404, foreign_change.text)

        disabled = self.client.patch(
            f"/governance/users/{managed_user.id}/access",
            headers=self.admin_headers,
            json={
                "role": "analyst",
                "status": "inactive",
                "reason": "The managed user's access is no longer required.",
            },
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        denied = self.client.get("/auth/me", headers=managed_headers)
        self.assertEqual(denied.status_code, 401, denied.text)
        self.audit_ids.extend(
            audit.id
            for audit in self.db.query(AuditLog).filter(
                AuditLog.companyId == self.company_admin.companyId,
                AuditLog.resourceType == "User Access Assignment",
                AuditLog.resourceId == str(managed_user.id),
            ).all()
        )

    def test_role_permissions_enforce_backend_actions_and_customer_contact_redaction(self):
        analyst_login = self.client.post(
            "/auth/login",
            json={"email": "analyst@retailpulse.com", "password": "password123"},
        )
        viewer = User(
            companyId=self.company_admin.companyId,
            name="Permission Viewer",
            email=f"permission-viewer-{uuid.uuid4().hex[:10]}@example.com",
            role="viewer",
            status="active",
        )
        self.db.add(viewer)
        self.db.commit()
        self.user_ids.append(viewer.id)
        self.assertEqual(analyst_login.status_code, 200, analyst_login.text)
        analyst_headers = {"Authorization": "Bearer " + analyst_login.json()["access_token"]}
        viewer_headers = {
            "Authorization": "Bearer " + create_access_token({
                "sub": viewer.email,
                "company_id": viewer.companyId,
            })
        }

        denied_customer_data = self.client.get("/customers", headers=analyst_headers)
        self.assertEqual(denied_customer_data.status_code, 403, denied_customer_data.text)
        denied_export = self.client.get("/dashboard/export", headers=analyst_headers)
        self.assertEqual(denied_export.status_code, 403, denied_export.text)
        denied_sales = self.client.get("/sales", headers=viewer_headers)
        self.assertEqual(denied_sales.status_code, 403, denied_sales.text)

        summary = self.client.get("/dashboard/analytics", headers=analyst_headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertTrue(all("email" not in customer for customer in summary.json()["recentCustomers"]))
        selectable_customers = self.client.get("/api/sales/customers/selectable", headers=analyst_headers)
        self.assertEqual(selectable_customers.status_code, 200, selectable_customers.text)
        self.assertTrue(all(
            not customer["email"] and customer["phone"] is None
            for customer in selectable_customers.json()
        ))

        analyst = self.db.query(User).filter_by(email="analyst@retailpulse.com").one()
        config = self.db.query(RolePermissionConfiguration).filter_by(
            companyId=analyst.companyId,
            role="analyst",
        ).first()
        created_config = config is None
        original_permissions = config.permissions if config else None
        if config is None:
            config = RolePermissionConfiguration(
                companyId=analyst.companyId,
                role="analyst",
            )
            self.db.add(config)
        configured = {
            module: (["view"] if module == "sales" else [])
            for module in ROLE_PERMISSION_MODULES
        }
        config.permissions = json.dumps(configured)
        self.db.commit()
        if created_config:
            self.role_permission_ids.append(config.id)
        try:
            denied_write = self.client.post("/api/sales", headers=analyst_headers, json={})
            self.assertEqual(denied_write.status_code, 403, denied_write.text)
        finally:
            if created_config:
                self.db.delete(config)
            else:
                config.permissions = original_permissions
            self.db.commit()

    def test_access_reviews_are_company_scoped_append_only_and_audited(self):
        suffix = uuid.uuid4().hex[:10]
        target = User(
            companyId=self.company_admin.companyId,
            name="Access Review Target",
            email=f"review-target-{suffix}@example.com",
            role="analyst",
            status="active",
        )
        foreign_target = User(
            companyId=self.company_admin.companyId + 900002,
            name="Foreign Access Review Target",
            email=f"review-foreign-{suffix}@example.com",
            role="viewer",
            status="active",
        )
        self.db.add_all([target, foreign_target])
        self.db.commit()
        self.user_ids.extend([target.id, foreign_target.id])

        invalid_flag = self.client.post(
            f"/governance/access-reviews/{target.id}",
            headers=self.admin_headers,
            json={
                "status": "flagged",
                "comment": "This permission is not granted.",
                "flaggedPermissions": ["customers:view"],
            },
        )
        self.assertEqual(invalid_flag.status_code, 422, invalid_flag.text)

        recorded = self.client.post(
            f"/governance/access-reviews/{target.id}",
            headers=self.admin_headers,
            json={
                "status": "flagged",
                "comment": "Export permission is not needed for this role.",
                "flaggedPermissions": ["sales:export"],
            },
        )
        self.assertEqual(recorded.status_code, 200, recorded.text)
        self.access_review_ids.append(recorded.json()["id"])

        assignments = self.client.get(
            "/governance/access-reviews",
            headers=self.admin_headers,
        )
        self.assertEqual(assignments.status_code, 200, assignments.text)
        entry = next(item for item in assignments.json() if item["userId"] == target.id)
        self.assertEqual(entry["reviewStatus"], "flagged")
        self.assertEqual(entry["reviewedBy"], self.company_admin.name or self.company_admin.email)
        self.assertEqual(entry["flaggedPermissions"], ["sales:export"])

        history = self.client.get(
            f"/governance/access-reviews/history?userId={target.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()), 1)
        self.assertEqual(history.json()[0]["comment"], "Export permission is not needed for this role.")

        denied_foreign = self.client.post(
            f"/governance/access-reviews/{foreign_target.id}",
            headers=self.admin_headers,
            json={"status": "reviewed", "comment": "Not in this company"},
        )
        self.assertEqual(denied_foreign.status_code, 404, denied_foreign.text)
        self.assertEqual(
            self.client.patch(
                f"/governance/access-reviews/{target.id}",
                headers=self.admin_headers,
                json={"status": "reviewed"},
            ).status_code,
            405,
        )
        analyst_login = self.client.post(
            "/auth/login",
            json={"email": "analyst@retailpulse.com", "password": "password123"},
        )
        self.assertEqual(analyst_login.status_code, 200, analyst_login.text)
        denied = self.client.get(
            "/governance/access-reviews",
            headers={"Authorization": "Bearer " + analyst_login.json()["access_token"]},
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        audit = self.db.query(AuditLog).filter(
            AuditLog.companyId == self.company_admin.companyId,
            AuditLog.action == "Access Review Flagged",
            AuditLog.resourceId == str(target.id),
        ).order_by(AuditLog.id.desc()).first()
        self.assertIsNotNone(audit)
        self.audit_ids.append(audit.id)

    def test_access_review_change_runs_through_approval_and_preserves_reason(self):
        suffix = uuid.uuid4().hex[:10]
        target = User(
            companyId=self.company_admin.companyId,
            name="Workflow Access Review Target",
            email=f"review-workflow-target-{suffix}@example.com",
            role="viewer",
            status="active",
        )
        approver = User(
            companyId=self.company_admin.companyId,
            name="Workflow Access Review Approver",
            email=f"review-workflow-approver-{suffix}@example.com",
            role="admin",
            status="active",
        )
        deactivation_target = User(
            companyId=self.company_admin.companyId,
            name="Workflow Access Removal Target",
            email=f"review-workflow-remove-{suffix}@example.com",
            role="viewer",
            status="active",
        )
        self.db.add_all([target, approver, deactivation_target])
        self.db.commit()
        self.user_ids.extend([target.id, approver.id, deactivation_target.id])

        started = self.client.post(
            f"/governance/access-reviews/{target.id}/workflow",
            headers=self.admin_headers,
            json={
                "role": "analyst",
                "reason": "The user's approved responsibilities now include sales analysis.",
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        request_id = started.json()["id"]
        self.approval_ids.append(request_id)
        request_history = self.client.get(
            "/governance/access-requests?scope=all",
            headers=self.admin_headers,
        )
        self.assertEqual(request_history.status_code, 200, request_history.text)
        self.assertTrue(any(item["id"] == request_id for item in request_history.json()))
        self.db.refresh(target)
        self.assertEqual(target.role, "viewer")
        self.assertEqual(started.json()["status"], "pending_approval")

        approver_headers = {
            "Authorization": "Bearer " + create_access_token({
                "sub": approver.email,
                "company_id": approver.companyId,
            })
        }
        decision = self.client.post(
            f"/workflows/{request_id}/decision",
            headers=approver_headers,
            json={"decision": "approved", "comment": "Approved after access review."},
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        self.db.refresh(target)
        self.assertEqual(target.role, "analyst")
        target_notification = self.db.query(Notification).filter(
            Notification.userId == target.id,
            Notification.resourceType == "Approval Request",
            Notification.resourceId == str(request_id),
            Notification.type == "access_request_approved",
        ).first()
        self.assertIsNotNone(target_notification)
        self.assertIn("approved", target_notification.message.lower())
        audit = self.db.query(AuditLog).filter(
            AuditLog.companyId == self.company_admin.companyId,
            AuditLog.action == "Access Request Approved",
            AuditLog.resourceId == str(target.id),
        ).order_by(AuditLog.id.desc()).first()
        self.assertIsNotNone(audit)
        self.assertEqual(
            json.loads(audit.description)["reason"],
            "The user's approved responsibilities now include sales analysis.",
        )
        self.audit_ids.append(audit.id)

        removal_started = self.client.post(
            f"/governance/access-reviews/{deactivation_target.id}/workflow",
            headers=self.admin_headers,
            json={
                "status": "inactive",
                "reason": "The user's contract has ended and access must be removed.",
            },
        )
        self.assertEqual(removal_started.status_code, 200, removal_started.text)
        removal_request_id = removal_started.json()["id"]
        self.approval_ids.append(removal_request_id)
        self.db.refresh(deactivation_target)
        self.assertEqual(deactivation_target.status, "active")
        removal_decision = self.client.post(
            f"/workflows/{removal_request_id}/decision",
            headers=approver_headers,
            json={"decision": "approved", "comment": "Access removal approved."},
        )
        self.assertEqual(removal_decision.status_code, 200, removal_decision.text)
        self.db.refresh(deactivation_target)
        self.assertEqual(deactivation_target.status, "inactive")
        self.audit_ids.extend(
            row.id
            for row in self.db.query(AuditLog).filter(
                AuditLog.companyId == self.company_admin.companyId,
                AuditLog.resourceType == "Approval Request",
                AuditLog.resourceId.in_([str(request_id), str(removal_request_id)]),
            ).all()
        )
        access_audit = self.db.query(AuditLog).filter(
            AuditLog.companyId == self.company_admin.companyId,
            AuditLog.action == "Access Request Approved",
            AuditLog.resourceId == str(deactivation_target.id),
        ).order_by(AuditLog.id.desc()).first()
        self.assertIsNotNone(access_audit)
        self.audit_ids.append(access_audit.id)

    def test_clearing_audit_logs_preserves_immutable_access_history(self):
        suffix = uuid.uuid4().hex[:10]
        company = Company(
            name=f"Audit Preservation {suffix}",
            email=f"audit-preservation-{suffix}@example.com",
        )
        self.db.add(company)
        self.db.flush()
        self.company_ids.append(company.id)
        admin = User(
            companyId=company.id,
            name="Audit Preservation Admin",
            email=f"audit-preservation-admin-{suffix}@example.com",
            role="admin",
            status="active",
        )
        protected = AuditLog(
            companyId=company.id,
            userId=admin.id,
            action="Access Review Completed",
            resourceType="Access Review",
            resourceId="77",
            description="Reviewed access.",
            company=str(company.id),
            user=admin.email,
            createdAt=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )
        ordinary = AuditLog(
            companyId=company.id,
            userId=admin.id,
            action="Product Viewed",
            resourceType="Product",
            resourceId="5",
            description="Viewed a product.",
            company=str(company.id),
            user=admin.email,
            createdAt=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(admin)
        self.db.flush()
        protected.userId = admin.id
        ordinary.userId = admin.id
        self.db.add_all([protected, ordinary])
        self.db.commit()
        protected_id = protected.id
        ordinary_id = ordinary.id
        admin_headers = {
            "Authorization": "Bearer " + create_access_token({
                "sub": admin.email,
                "company_id": company.id,
            })
        }

        cleared = self.client.delete("/audit-logs", headers=admin_headers)
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["deletedCount"], 1)
        self.assertEqual(cleared.json()["preservedAccessHistoryCount"], 1)
        with SessionLocal() as verification_db:
            self.assertIsNotNone(verification_db.query(AuditLog).filter_by(id=protected_id).first())
            self.assertIsNone(
                verification_db.query(AuditLog).filter(
                    AuditLog.id == ordinary_id,
                    AuditLog.action == "Product Viewed",
                ).first()
            )


if __name__ == "__main__":
    unittest.main()
