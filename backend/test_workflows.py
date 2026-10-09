import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import (
    ApprovalHistoryRecord,
    ApprovalRequestRecord,
    AuditLog,
    Category,
    Company,
    Customer,
    ImportBatch,
    Notification,
    Product,
    RefreshToken,
    StockAdjustment,
    StockMovement,
    User,
    WorkflowConfiguration,
)


class WorkflowApprovalTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.request_ids = []
        self.configuration_audit_ids = []
        self.admin_headers = self._login("admin@retailpulse.com")
        self.analyst_headers = self._login("analyst@retailpulse.com")
        self.analyst = self.db.query(User).filter_by(email="analyst@retailpulse.com").first()
        suffix = uuid.uuid4().hex[:10]
        self.product = Product(
            companyId=self.analyst.companyId,
            sku=f"WF-{suffix}",
            name=f"Workflow Product {suffix}",
            brand="Workflow Test",
            unitPrice=12.5,
            costPrice=5,
            stockQuantity=100,
            initialStockQuantity=100,
            price="12.5",
            status="active",
        )
        self.customer = Customer(
            companyId=self.analyst.companyId,
            customerId=f"WF-C-{suffix}",
            name=f"Workflow Customer {suffix}",
            email=f"wf-{suffix}@example.com",
            phone=f"555{suffix[:7]}",
            isDeleted=0,
        )
        self.import_batch = ImportBatch(
            companyId=self.analyst.companyId,
            entityType="inventory",
            fileName=f"workflow-{suffix}.csv",
            totalRows=0,
            validCount=0,
            invalidCount=0,
            duplicateCount=0,
            status="uploaded",
            importedBy=self.analyst.email,
        )
        self.category = Category(
            companyId=self.analyst.companyId,
            name=f"Workflow Test {suffix}",
            description="Workflow API integration test category",
            status="active",
        )
        self.db.add(self.category)
        self.db.flush()
        self.product.categoryId = self.category.id
        self.db.add_all([self.product, self.customer, self.import_batch])
        self.db.commit()
        self.product_id = self.product.id
        self.customer_id = self.customer.id
        self.import_batch_id = self.import_batch.id
        self.original_configurations = {
            configuration.requestType: (
                configuration.approverRole,
                configuration.approvalRequired,
                configuration.isActive,
                configuration.allowSelfApproval,
            )
            for configuration in self.db.query(WorkflowConfiguration).filter(
                WorkflowConfiguration.companyId == self.analyst.companyId
            ).all()
        }

    def tearDown(self):
        if self.request_ids:
            self.db.query(ApprovalHistoryRecord).filter(
                ApprovalHistoryRecord.requestId.in_(self.request_ids)
            ).delete(synchronize_session=False)
            request_ids = [str(request_id) for request_id in self.request_ids]
            self.db.query(AuditLog).filter(
                AuditLog.resourceType == "Approval Request",
                AuditLog.resourceId.in_(request_ids),
            ).delete(synchronize_session=False)
            self.db.query(Notification).filter(
                Notification.resourceType == "Approval Request",
                Notification.resourceId.in_(request_ids),
            ).delete(synchronize_session=False)
            self.db.query(ApprovalRequestRecord).filter(
                ApprovalRequestRecord.id.in_(self.request_ids)
            ).delete(synchronize_session=False)
        if self.configuration_audit_ids:
            self.db.query(AuditLog).filter(
                AuditLog.id.in_(self.configuration_audit_ids)
            ).delete(synchronize_session=False)
        self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Product",
            AuditLog.resourceId == str(self.product_id),
            AuditLog.action.in_(["Product Price Change", "Product Deactivation"]),
        ).delete(synchronize_session=False)
        self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Customer",
            AuditLog.resourceId == str(self.customer_id),
            AuditLog.action == "Customer Information Change",
        ).delete(synchronize_session=False)
        self.db.query(StockAdjustment).filter(StockAdjustment.productId == self.product_id).delete(synchronize_session=False)
        self.db.query(StockMovement).filter(StockMovement.productId == self.product_id).delete(synchronize_session=False)
        self.db.query(Product).filter(Product.id == self.product_id).delete(synchronize_session=False)
        self.db.query(Category).filter(Category.id == self.category.id).delete(synchronize_session=False)
        self.db.query(Customer).filter(Customer.id == self.customer_id).delete(synchronize_session=False)
        self.db.query(ImportBatch).filter(ImportBatch.id == self.import_batch_id).delete(synchronize_session=False)
        for configuration in self.db.query(WorkflowConfiguration).filter(
            WorkflowConfiguration.companyId == self.analyst.companyId
        ).all():
            original = self.original_configurations.get(configuration.requestType)
            if original is None:
                self.db.delete(configuration)
            else:
                (
                    configuration.approverRole,
                    configuration.approvalRequired,
                    configuration.isActive,
                    configuration.allowSelfApproval,
                ) = original
        self.db.commit()
        self.db.close()

    def _login(self, email):
        response = self.client.post(
            "/auth/login",
            json={"email": email, "password": "password123"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _submit_request(self, request_type="stock_adjustment"):
        return self._create_request(request_type, submit=True)

    def _create_request(self, request_type="stock_adjustment", submit=True):
        related_records = {
            "stock_adjustment": self.product.sku,
            "product_deactivation": self.product.sku,
            "product_price_change": self.product.sku,
            "customer_information_change": self.customer.customerId,
            "inventory_import_approval": str(self.import_batch_id),
        }
        changes = {
            "stock_adjustment": {"stockQuantity": 125},
            "product_deactivation": {"status": "inactive"},
            "product_price_change": {"unitPrice": 15.75},
            "customer_information_change": {"name": "Updated Workflow Customer"},
            "inventory_import_approval": {"importBatchId": self.import_batch_id},
        }
        response = self.client.post(
            "/workflows",
            headers=self.analyst_headers,
            json={
                "requestType": request_type,
                "relatedRecord": related_records[request_type],
                "requestedChanges": changes[request_type],
                "reason": "Correct the recorded stock quantity.",
                "submit": submit,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        request = response.json()
        self.request_ids.append(request["id"])
        return request

    def _configuration(self, request_type):
        response = self.client.get("/workflows/configuration", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        return next(item for item in response.json() if item["requestType"] == request_type)

    def _update_configuration(self, request_type, **changes):
        configuration = {**self._configuration(request_type), **changes}
        response = self.client.put(
            f"/workflows/configuration/{request_type}",
            headers=self.admin_headers,
            json=configuration,
        )
        self.assertEqual(response.status_code, 200, response.text)
        audit_entry = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Workflow Configuration",
            AuditLog.resourceId == f"{self.analyst.companyId}:{request_type}",
            AuditLog.action == "Workflow Configuration Updated",
        ).order_by(AuditLog.id.desc()).first()
        if audit_entry:
            self.configuration_audit_ids.append(audit_entry.id)
        return response.json()

    def test_submit_and_review_request_with_persistent_history(self):
        submitted = self._submit_request()
        self.assertEqual(submitted["status"], "pending_approval")
        self.assertEqual([entry["action"] for entry in submitted["history"]], ["created", "submitted", "pending_approval"])
        self.assertEqual(submitted["requestType"], "stock_adjustment")
        self.assertEqual(submitted["requestedChanges"]["stockQuantity"], 125)
        self.assertEqual(submitted["currentValues"]["stockQuantity"], 100)
        self.assertEqual(submitted["reason"], "Correct the recorded stock quantity.")
        self.assertEqual(submitted["relatedRecord"], submitted["title"].split()[-1])
        self.assertTrue(submitted["companyName"])

        pending = self.client.get(
            "/workflows?scope=pending&requestType=stock_adjustment&status=pending_approval",
            headers=self.admin_headers,
        )
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertIn(submitted["id"], [request["id"] for request in pending.json()])

        decision = self.client.post(
            f"/workflows/{submitted['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "approved", "comment": "Within the approved promotion budget."},
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        reviewed = decision.json()
        self.assertEqual(reviewed["status"], "approved")
        self.db.refresh(self.product)
        self.assertEqual(self.product.stockQuantity, 125)
        self.assertEqual(
            self.db.query(StockAdjustment).filter(StockAdjustment.productId == self.product_id).count(),
            1,
        )
        reviewed_actions = [entry["action"] for entry in reviewed["history"]]
        self.assertEqual(
            reviewed_actions,
            ["created", "submitted", "pending_approval", "inventory_updated", "approved"],
        )
        self.assertEqual(reviewed["history"][-1]["comment"], "Within the approved promotion budget.")

        repeated_decision = self.client.post(
            f"/workflows/{submitted['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "approved", "comment": "Duplicate approval."},
        )
        self.assertEqual(repeated_decision.status_code, 409)

        audit = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Approval Request",
            AuditLog.resourceId == str(submitted["id"]),
        ).all()
        created_audit = next(entry for entry in audit if entry.action == "Approval Request Created")
        self.assertEqual(created_audit.userId, submitted["requesterId"])
        self.assertEqual(created_audit.resourceId, str(submitted["id"]))
        self.assertIsNotNone(created_audit.createdAt)
        self.assertEqual(
            {entry.action for entry in audit},
            {
                "Approval Request Created",
                "Approval Request Submitted",
                "Approval Request Pending Approval",
                "Approval Request Inventory Updated",
                "Approval Request Approved",
            },
        )
        detail = self.client.get(
            f"/workflows/{submitted['id']}",
            headers=self.admin_headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["history"][-1]["action"], "viewed")
        self.assertEqual(detail.json()["history"][-1]["actorId"], detail.json()["reviewerId"])
        viewed_audit = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Approval Request",
            AuditLog.resourceId == str(submitted["id"]),
            AuditLog.action == "Approval Request Viewed",
        ).first()
        self.assertIsNotNone(viewed_audit)
        self.assertEqual(viewed_audit.userId, reviewed["reviewerId"])
        self.assertEqual(viewed_audit.resourceId, str(submitted["id"]))
        self.assertIn("Request viewed by", viewed_audit.description)
        notification = self.db.query(Notification).filter(
            Notification.resourceType == "Approval Request",
            Notification.resourceId == str(submitted["id"]),
            Notification.userId == reviewed["requesterId"],
        ).first()
        self.assertIsNotNone(notification)
        submitted_notification = self.db.query(Notification).filter(
            Notification.resourceType == "Approval Request",
            Notification.resourceId == str(submitted["id"]),
            Notification.type == "approval_request_submitted",
            Notification.userId == submitted["requesterId"],
        ).first()
        self.assertIsNotNone(submitted_notification)

    def test_explicit_approval_api_history_and_pending_counts(self):
        baseline_counts_response = self.client.get("/workflows/pending-counts", headers=self.admin_headers)
        self.assertEqual(baseline_counts_response.status_code, 200, baseline_counts_response.text)
        baseline_counts = baseline_counts_response.json()
        request = self._submit_request()
        counts = self.client.get("/workflows/pending-counts", headers=self.admin_headers)
        self.assertEqual(counts.status_code, 200, counts.text)
        self.assertEqual(counts.json()["total"], baseline_counts["total"] + 1)
        self.assertEqual(
            counts.json()["byRequestType"]["stock_adjustment"],
            baseline_counts["byRequestType"]["stock_adjustment"] + 1,
        )

        history = self.client.get(
            f"/workflows/{request['id']}/history",
            headers=self.admin_headers,
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(
            [event["action"] for event in history.json()],
            ["created", "submitted", "pending_approval"],
        )

        approved = self.client.post(
            f"/workflows/{request['id']}/approve",
            headers=self.admin_headers,
            json={"comment": "Approved through the explicit action endpoint."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(approved.json()["history"][-1]["comment"], "Approved through the explicit action endpoint.")
        sales_products = self.client.get(
            "/sales/products/selectable",
            headers=self.admin_headers,
        )
        self.assertEqual(sales_products.status_code, 200, sales_products.text)
        sales_product = next(item for item in sales_products.json() if item["id"] == self.product_id)
        self.assertEqual(sales_product["stockQuantity"], 125)
        counts_after_approval = self.client.get("/workflows/pending-counts", headers=self.admin_headers)
        self.assertEqual(counts_after_approval.json(), baseline_counts)

        rejected_request = self._submit_request("product_price_change")
        rejected = self.client.post(
            f"/workflows/{rejected_request['id']}/reject",
            headers=self.admin_headers,
            json={"comment": "Price change is not supported."},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")

    def test_workflow_api_endpoints_enforce_authentication_and_company_scope(self):
        for path in ("/workflows/pending-counts",):
            self.assertEqual(self.client.get(path).status_code, 401)
        request = self._submit_request()
        self.assertEqual(
            self.client.get(f"/workflows/{request['id']}/history").status_code,
            401,
        )

        registered = self.client.post(
            "/auth/register",
            json={
                "companyName": f"Workflow API Isolation {uuid.uuid4().hex[:8]}",
                "industry": "Retail",
                "companyEmail": f"workflow-api-{uuid.uuid4().hex[:8]}@example.com",
                "companyAddress": "1 Isolated Road",
                "companyPhone": "555-2211",
                "ownerName": "Workflow API Owner",
                "ownerEmail": f"workflow-api-owner-{uuid.uuid4().hex[:8]}@example.com",
                "password": "Password123",
                "confirmPassword": "Password123",
            },
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        other_company_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        other_company_id = registered.json()["user"]["companyId"]
        other_user_id = registered.json()["user"]["id"]
        try:
            not_found = self.client.get(
                f"/workflows/{request['id']}/history",
                headers=other_company_headers,
            )
            self.assertEqual(not_found.status_code, 404)
        finally:
            self.db.query(RefreshToken).filter_by(userId=other_user_id).delete(synchronize_session=False)
            self.db.query(WorkflowConfiguration).filter_by(companyId=other_company_id).delete(synchronize_session=False)
            self.db.query(AuditLog).filter_by(companyId=other_company_id).delete(synchronize_session=False)
            other_user = self.db.query(User).filter_by(id=other_user_id).first()
            other_company = self.db.query(Company).filter_by(id=other_company_id).first()
            if other_user:
                self.db.delete(other_user)
            if other_company:
                self.db.delete(other_company)
            self.db.commit()

    def test_rejection_requires_comment_and_decisions_are_authorized(self):
        submitted = self._submit_request()
        self.assertEqual(self.product.stockQuantity, 100)
        rejected_without_comment = self.client.post(
            f"/workflows/{submitted['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "rejected", "comment": "  "},
        )
        self.assertEqual(rejected_without_comment.status_code, 422)

        analyst_decision = self.client.post(
            f"/workflows/{submitted['id']}/decision",
            headers=self.analyst_headers,
            json={"decision": "approved"},
        )
        self.assertEqual(analyst_decision.status_code, 403)

        rejected = self.client.post(
            f"/workflows/{submitted['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "rejected", "comment": "Please attach the supporting approval."},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.db.refresh(self.product)
        self.assertEqual(self.product.stockQuantity, 100)
        self.assertEqual(rejected.json()["history"][-1]["comment"], "Please attach the supporting approval.")
        rejection_audit = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Approval Request",
            AuditLog.resourceId == str(submitted["id"]),
            AuditLog.action == "Approval Request Rejected",
        ).first()
        self.assertIsNotNone(rejection_audit)
        self.assertEqual(rejection_audit.userId, self.db.query(User).filter_by(email="admin@retailpulse.com").first().id)
        self.assertIn("Please attach the supporting approval.", rejection_audit.description)

        duplicate_decision = self.client.post(
            f"/workflows/{submitted['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "approved", "comment": ""},
        )
        self.assertEqual(duplicate_decision.status_code, 409)
        self.assertEqual(duplicate_decision.json()["detail"], "Cannot review a request with status rejected")

    def test_draft_requires_submission_before_approval_queue_and_notifies_approver(self):
        draft = self._create_request(submit=False)
        self.assertEqual(draft["status"], "draft")
        self.assertEqual([entry["action"] for entry in draft["history"]], ["created", "draft"])
        pending = self.client.get("/workflows?scope=pending", headers=self.admin_headers)
        self.assertNotIn(draft["id"], [request["id"] for request in pending.json()])
        submission_notifications = self.db.query(Notification).filter(
            Notification.resourceType == "Approval Request",
            Notification.resourceId == str(draft["id"]),
            Notification.type == "approval_request_assigned",
            Notification.userId == self.db.query(User).filter_by(email="admin@retailpulse.com").first().id,
        ).count()
        self.assertEqual(submission_notifications, 0)

        submit = self.client.post(
            f"/workflows/{draft['id']}/submit",
            headers=self.analyst_headers,
        )
        self.assertEqual(submit.status_code, 200, submit.text)
        submitted = submit.json()
        self.assertEqual(submitted["status"], "pending_approval")
        self.assertEqual(
            [entry["action"] for entry in submitted["history"]],
            ["created", "draft", "submitted", "pending_approval"],
        )
        submission_notifications = self.db.query(Notification).filter(
            Notification.resourceType == "Approval Request",
            Notification.resourceId == str(draft["id"]),
            Notification.type == "approval_request_assigned",
            Notification.userId == self.db.query(User).filter_by(email="admin@retailpulse.com").first().id,
        ).count()
        self.assertGreater(submission_notifications, 0)
        requester_notification = self.db.query(Notification).filter(
            Notification.resourceType == "Approval Request",
            Notification.resourceId == str(draft["id"]),
            Notification.type == "approval_request_submitted",
            Notification.userId == draft["requesterId"],
        ).count()
        self.assertEqual(requester_notification, 1)

        repeated_submit = self.client.post(
            f"/workflows/{draft['id']}/submit",
            headers=self.analyst_headers,
        )
        self.assertEqual(repeated_submit.status_code, 409)

    def test_request_visibility_is_company_and_owner_scoped(self):
        submitted = self._submit_request()
        own_requests = self.client.get(
            "/workflows?scope=submitted",
            headers=self.analyst_headers,
        )
        self.assertEqual(own_requests.status_code, 200, own_requests.text)
        self.assertIn(submitted["id"], [request["id"] for request in own_requests.json()])

        analyst_pending = self.client.get(
            "/workflows?scope=pending",
            headers=self.analyst_headers,
        )
        self.assertEqual(analyst_pending.status_code, 200, analyst_pending.text)
        self.assertNotIn(submitted["id"], [request["id"] for request in analyst_pending.json()])

        missing_request = self.client.get("/workflows/2147483647", headers=self.analyst_headers)
        self.assertEqual(missing_request.status_code, 404)

    def test_all_initial_request_types_are_supported(self):
        request_types = [
            "stock_adjustment",
            "product_deactivation",
            "product_price_change",
            "customer_information_change",
            "inventory_import_approval",
        ]
        for request_type in request_types:
            with self.subTest(request_type=request_type):
                request = self._submit_request(request_type)
                self.assertEqual(request["requestType"], request_type)

    def test_approved_change_requests_apply_to_the_scoped_business_records(self):
        for request_type in (
            "product_price_change",
            "product_deactivation",
            "customer_information_change",
        ):
            with self.subTest(request_type=request_type):
                request = self._submit_request(request_type)
                result = self.client.post(
                    f"/workflows/{request['id']}/decision",
                    headers=self.admin_headers,
                    json={"decision": "approved", "comment": "Verified."},
                )
                self.assertEqual(result.status_code, 200, result.text)
                if request_type == "product_price_change":
                    self.db.refresh(self.product)
                    self.assertEqual(self.product.unitPrice, 15.75)
                elif request_type == "product_deactivation":
                    self.db.refresh(self.product)
                    self.assertEqual(self.product.status, "inactive")
                    self.product.status = "active"
                    self.db.commit()
                else:
                    self.db.refresh(self.customer)
                    self.assertEqual(self.customer.name, "Updated Workflow Customer")
                    self.customer.name = "Workflow Customer"
                    self.db.commit()

    def test_inventory_import_is_queued_only_after_approval(self):
        request = self._submit_request("inventory_import_approval")
        self.assertEqual(self.import_batch.status, "uploaded")
        response = self.client.post(
            f"/workflows/{request['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "approved", "comment": "Import preview verified."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "approved")
        self.db.refresh(self.import_batch)
        self.assertIn(self.import_batch.status, {"completed", "completed_with_errors"})

    def test_approval_rejects_a_related_record_changed_after_submission(self):
        request = self._submit_request()
        self.product.stockQuantity = 110
        self.db.commit()
        response = self.client.post(
            f"/workflows/{request['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "approved", "comment": "Reviewing stock change."},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("changed after", response.json()["detail"])
        self.db.refresh(self.product)
        self.assertEqual(self.product.stockQuantity, 110)
        self.db.refresh(self.db.query(ApprovalRequestRecord).get(request["id"]))
        self.assertEqual(self.db.query(ApprovalRequestRecord).get(request["id"]).status, "pending_approval")

    def test_business_mutation_failure_rolls_back_claim_status_history_and_audit(self):
        request = self._submit_request()

        def fail_after_mutation(db, reviewer, *_):
            product = db.query(Product).filter(
                Product.id == self.product_id,
                Product.companyId == reviewer.companyId,
            ).one()
            product.stockQuantity = 777
            raise RuntimeError("simulated failure after staging business mutation")

        with patch(
            "backend.controllers.workflows_controller._apply_requested_changes",
            side_effect=fail_after_mutation,
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                self.client.post(
                    f"/workflows/{request['id']}/decision",
                    headers=self.admin_headers,
                    json={"decision": "approved", "comment": "Approve stock change."},
                )

        self.db.expire_all()
        self.assertEqual(self.db.query(Product).filter_by(id=self.product_id).one().stockQuantity, 100)
        persisted_request = self.db.query(ApprovalRequestRecord).filter_by(id=request["id"]).one()
        self.assertEqual(persisted_request.status, "pending_approval")
        actions = self.db.query(ApprovalHistoryRecord.action).filter(
            ApprovalHistoryRecord.requestId == request["id"],
        ).all()
        self.assertNotIn(("approved",), actions)
        approved_audits = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Approval Request",
            AuditLog.resourceId == str(request["id"]),
            AuditLog.action == "Approval Request Approved",
        ).count()
        self.assertEqual(approved_audits, 0)
        approval_notifications = self.db.query(Notification).filter(
            Notification.resourceType == "Approval Request",
            Notification.resourceId == str(request["id"]),
            Notification.type == "approval_request_approved",
        ).count()
        self.assertEqual(approval_notifications, 0)

    def test_workflow_and_related_records_are_isolated_between_companies(self):
        suffix = uuid.uuid4().hex[:8]
        registration = self.client.post(
            "/auth/register",
            json={
                "companyName": f"Workflow Isolation {suffix}",
                "industry": "Retail",
                "companyEmail": f"workflow-company-{suffix}@example.com",
                "companyAddress": "1 Isolated Road",
                "companyPhone": "555-2200",
                "ownerName": f"Workflow Owner {suffix}",
                "ownerEmail": f"workflow-owner-{suffix}@example.com",
                "password": "Password123",
                "confirmPassword": "Password123",
            },
        )
        self.assertEqual(registration.status_code, 200, registration.text)
        foreign_token = registration.json()["access_token"]
        foreign_headers = {"Authorization": f"Bearer {foreign_token}"}
        foreign_company_id = registration.json()["user"]["companyId"]
        foreign_user = self.db.query(User).filter_by(companyId=foreign_company_id).first()
        foreign_product = Product(
            companyId=foreign_company_id,
            sku=f"FOREIGN-{suffix}",
            name="Foreign workflow product",
            brand="Test",
            unitPrice=10,
            stockQuantity=10,
            initialStockQuantity=10,
            price="10",
            status="active",
        )
        self.db.add(foreign_product)
        self.db.commit()
        foreign_product_id = foreign_product.id
        foreign_request_id = None
        try:
            foreign_configuration = self.client.get(
                "/workflows/configuration",
                headers=foreign_headers,
            )
            self.assertEqual(foreign_configuration.status_code, 200, foreign_configuration.text)
            foreign_stock_config = next(
                item for item in foreign_configuration.json()
                if item["requestType"] == "stock_adjustment"
            )
            foreign_stock_config["approverRole"] = "viewer"
            updated_foreign_configuration = self.client.put(
                "/workflows/configuration/stock_adjustment",
                headers=foreign_headers,
                json=foreign_stock_config,
            )
            self.assertEqual(updated_foreign_configuration.status_code, 200, updated_foreign_configuration.text)

            own_config = self.client.get("/workflows/configuration", headers=self.admin_headers)
            own_stock_config = next(
                item for item in own_config.json()
                if item["requestType"] == "stock_adjustment"
            )
            self.assertEqual(own_stock_config["approverRole"], "admin")

            foreign_request = self.client.post(
                "/workflows",
                headers=foreign_headers,
                json={
                    "requestType": "stock_adjustment",
                    "relatedRecord": foreign_product.sku,
                    "requestedChanges": {"stockQuantity": 15},
                    "reason": "Foreign company stock correction.",
                },
            )
            self.assertEqual(foreign_request.status_code, 200, foreign_request.text)
            foreign_request_id = foreign_request.json()["id"]

            self.assertEqual(
                self.client.get(f"/workflows/{foreign_request_id}", headers=self.admin_headers).status_code,
                404,
            )
            self.assertEqual(
                self.client.post(
                    f"/workflows/{foreign_request_id}/decision",
                    headers=self.admin_headers,
                    json={"decision": "approved", "comment": "Cross-company attempt."},
                ).status_code,
                404,
            )
            all_requests = self.client.get("/workflows?scope=all", headers=self.admin_headers)
            self.assertEqual(all_requests.status_code, 200, all_requests.text)
            self.assertFalse(any(item["id"] == foreign_request_id for item in all_requests.json()))
            foreign_reference_attempt = self.client.post(
                "/workflows",
                headers=self.admin_headers,
                json={
                    "requestType": "stock_adjustment",
                    "relatedRecord": foreign_product.sku,
                    "requestedChanges": {"stockQuantity": 15},
                    "reason": "Attempt against a foreign product.",
                },
            )
            self.assertEqual(foreign_reference_attempt.status_code, 404)
            self.assertEqual(
                self.client.get("/workflows/configuration", headers=self.admin_headers).status_code,
                200,
            )
        finally:
            if foreign_request_id is not None:
                self.db.query(ApprovalHistoryRecord).filter_by(requestId=foreign_request_id).delete(synchronize_session=False)
                self.db.query(AuditLog).filter(
                    AuditLog.resourceType == "Approval Request",
                    AuditLog.resourceId == str(foreign_request_id),
                ).delete(synchronize_session=False)
                self.db.query(Notification).filter(
                    Notification.resourceType == "Approval Request",
                    Notification.resourceId == str(foreign_request_id),
                ).delete(synchronize_session=False)
                self.db.query(ApprovalRequestRecord).filter_by(id=foreign_request_id).delete(synchronize_session=False)
            self.db.query(AuditLog).filter(
                AuditLog.companyId == foreign_company_id,
            ).delete(synchronize_session=False)
            self.db.query(WorkflowConfiguration).filter_by(companyId=foreign_company_id).delete(synchronize_session=False)
            self.db.query(Product).filter_by(id=foreign_product_id).delete(synchronize_session=False)
            if foreign_user:
                self.db.query(RefreshToken).filter_by(userId=foreign_user.id).delete(synchronize_session=False)
                foreign_company = self.db.query(Company).filter_by(id=foreign_company_id).first()
                self.db.delete(foreign_user)
                if foreign_company:
                    self.db.delete(foreign_company)
            self.db.commit()

    def test_approver_role_assignment_is_enforced_by_the_backend(self):
        self._update_configuration("stock_adjustment", approverRole="analyst")
        response = self.client.post(
            "/workflows",
            headers=self.admin_headers,
            json={
                "requestType": "stock_adjustment",
                "relatedRecord": self.product.sku,
                "requestedChanges": {"stockQuantity": 125},
                "reason": "Approve the planned inventory correction.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        request = response.json()
        self.request_ids.append(request["id"])
        self.assertEqual(request["assignedApproverRole"], "analyst")

        analyst_queue = self.client.get("/workflows?scope=pending", headers=self.analyst_headers)
        self.assertEqual(analyst_queue.status_code, 200, analyst_queue.text)
        self.assertIn(request["id"], [item["id"] for item in analyst_queue.json()])
        admin_queue = self.client.get("/workflows?scope=pending", headers=self.admin_headers)
        self.assertEqual(admin_queue.status_code, 200, admin_queue.text)
        self.assertIn(request["id"], [item["id"] for item in admin_queue.json()])

        decision = self.client.post(
            f"/workflows/{request['id']}/decision",
            headers=self.analyst_headers,
            json={"decision": "approved", "comment": "Assigned role approved."},
        )
        self.assertEqual(decision.status_code, 200, decision.text)

    def test_self_approval_requires_explicit_workflow_configuration(self):
        self._update_configuration(
            "stock_adjustment",
            approverRole="analyst",
            allowSelfApproval=False,
        )
        request = self._submit_request()
        denied = self.client.post(
            f"/workflows/{request['id']}/decision",
            headers=self.analyst_headers,
            json={"decision": "approved", "comment": "Attempt without permission."},
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(self.product.stockQuantity, 100)

        self._update_configuration("stock_adjustment", allowSelfApproval=True)
        approved = self.client.post(
            f"/workflows/{request['id']}/decision",
            headers=self.analyst_headers,
            json={"decision": "approved", "comment": "Explicitly allowed."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "approved")
        self.db.refresh(self.product)
        self.assertEqual(self.product.stockQuantity, 125)

    def test_workflow_configuration_is_admin_only_and_controls_activation(self):
        forbidden_get = self.client.get("/workflows/configuration", headers=self.analyst_headers)
        self.assertEqual(forbidden_get.status_code, 403)
        forbidden_update = self.client.put(
            "/workflows/configuration/stock_adjustment",
            headers=self.analyst_headers,
            json={
                "approverRole": "analyst",
                "approvalRequired": True,
                "isActive": True,
                "allowSelfApproval": False,
            },
        )
        self.assertEqual(forbidden_update.status_code, 403)

        configurations = self.client.get("/workflows/configuration", headers=self.admin_headers)
        self.assertEqual(configurations.status_code, 200, configurations.text)
        self.assertEqual(len(configurations.json()), 5)
        self._update_configuration("stock_adjustment", isActive=False)
        configuration_audit = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Workflow Configuration",
            AuditLog.resourceId == f"{self.analyst.companyId}:stock_adjustment",
            AuditLog.action == "Workflow Configuration Updated",
        ).first()
        self.assertIsNotNone(configuration_audit)
        self.assertEqual(configuration_audit.userId, self.db.query(User).filter_by(email="admin@retailpulse.com").first().id)
        response = self.client.post(
            "/workflows",
            headers=self.analyst_headers,
            json={
                "requestType": "stock_adjustment",
                "relatedRecord": self.product.sku,
                "requestedChanges": {"stockQuantity": 125},
                "reason": "This inactive workflow must reject submissions.",
            },
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_workflows_without_required_approval_apply_changes_on_submission(self):
        self._update_configuration("stock_adjustment", approvalRequired=False)
        request = self._submit_request()
        self.assertEqual(request["status"], "approved")
        self.assertEqual([event["action"] for event in request["history"]], ["created", "submitted", "inventory_updated", "approved"])
        self.db.refresh(self.product)
        self.assertEqual(self.product.stockQuantity, 125)

    def test_related_record_requested_changes_and_reason_are_required(self):
        response = self.client.post(
            "/workflows",
            headers=self.analyst_headers,
            json={
                "requestType": "product_price_change",
                "relatedRecord": "SKU-123",
                "requestedChanges": {},
                "reason": "Apply the updated price.",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_cancelled_requests_are_terminal_and_cannot_be_approved(self):
        submitted = self._submit_request()
        cancelled = self.client.post(
            f"/workflows/{submitted['id']}/cancel",
            headers=self.analyst_headers,
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.assertEqual(cancelled.json()["history"][-1]["action"], "cancelled")
        cancelled_audit = self.db.query(AuditLog).filter(
            AuditLog.resourceType == "Approval Request",
            AuditLog.resourceId == str(submitted["id"]),
            AuditLog.action == "Approval Request Cancelled",
        ).first()
        self.assertIsNotNone(cancelled_audit)
        self.assertEqual(cancelled_audit.userId, submitted["requesterId"])

        approval = self.client.post(
            f"/workflows/{submitted['id']}/decision",
            headers=self.admin_headers,
            json={"decision": "approved", "comment": "Should not be accepted."},
        )
        self.assertEqual(approval.status_code, 409)
        self.assertIn("cancelled", approval.json()["detail"])

        repeated_cancel = self.client.post(
            f"/workflows/{submitted['id']}/cancel",
            headers=self.analyst_headers,
        )
        self.assertEqual(repeated_cancel.status_code, 409)

    def test_cancelled_draft_cannot_be_submitted(self):
        draft = self._create_request(submit=False)
        cancelled = self.client.post(
            f"/workflows/{draft['id']}/cancel",
            headers=self.analyst_headers,
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")

        submit = self.client.post(
            f"/workflows/{draft['id']}/submit",
            headers=self.analyst_headers,
        )
        self.assertEqual(submit.status_code, 409)
        self.assertIn("cancelled", submit.json()["detail"])


if __name__ == "__main__":
    unittest.main()
