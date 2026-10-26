"""Review request and decision are separate chronological audit events."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from orgs.models import Project
from .models import ComplianceDocument, CoverPage, ReviewTask


class ReviewActivityTests(TestCase):
    def setUp(self):
        self.project = Project.objects.get(slug="ozgur")
        self.requester = get_user_model().objects.create_superuser("a10001")
        self.reviewer = get_user_model().objects.create_superuser("a10002")
        cover = CoverPage.objects.create(project=self.project, number="CP-REVIEW")
        self.document = ComplianceDocument.objects.create(project=self.project, cover_page=cover, name="Review document")
        self.task = ReviewTask.objects.create(document=self.document, kind="approval", assignee=self.reviewer,
            assignee_username=self.reviewer.username, requested_by=self.requester,
            requested_by_username=self.requester.username, request_note="Please approve this document.", source_version=1)
        self.requested_at = timezone.now() - timedelta(days=10)
        ReviewTask.objects.filter(pk=self.task.pk).update(created_at=self.requested_at)
        self.client = APIClient()
        self.client.force_authenticate(self.reviewer)
        self.url = f"/api/projects/ozgur/compliance-documents/{self.document.pk}/"

    def review_activity(self):
        response = self.client.get(self.url + "activity/")
        self.assertEqual(response.status_code, 200)
        return [item for item in response.data["results"] if item["type"] == "review"]

    def test_decision_keeps_request_evidence_and_uses_its_own_timestamp(self):
        decision = self.client.post(self.url + f"reviews/{self.task.pk}/decision/", {
            "status": "approved", "decision_note": "Approved the evidence.",
        }, format="json")
        self.assertEqual(decision.status_code, 200)
        rows = self.review_activity()
        self.assertEqual(len(rows), 2)
        decided, requested = rows
        self.assertEqual(decided["at"], decision.data["decided_at"])
        self.assertEqual(decided["data"]["decision_note"], "Approved the evidence.")
        self.assertEqual(decided["data"]["decided_by_username"], self.reviewer.username)
        self.assertEqual(requested["at"], decision.data["created_at"])
        self.assertEqual(requested["data"]["status"], "pending")
        self.assertEqual(requested["data"]["requested_by_username"], self.requester.username)
        self.assertEqual(requested["data"]["decision_note"], "")
        self.assertEqual(requested["data"]["decided_by_username"], "")

    def test_pending_task_has_only_its_request_event(self):
        rows = self.review_activity()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data"]["status"], "pending")

    def test_recent_decision_on_an_old_task_remains_in_recent_activity(self):
        ReviewTask.objects.bulk_create([
            ReviewTask(document=self.document, kind="review", status="approved",
                assignee=self.reviewer, assignee_username=self.reviewer.username,
                requested_by=self.requester, requested_by_username=self.requester.username,
                request_note="Later request.", source_version=1)
            for _ in range(101)
        ])
        decision = self.client.post(self.url + f"reviews/{self.task.pk}/decision/", {
            "status": "approved", "decision_note": "Recent decision on older evidence.",
        }, format="json")
        self.assertEqual(decision.status_code, 200)
        rows = self.review_activity()
        self.assertTrue(any(row["at"] == decision.data["decided_at"] and
            row["data"]["id"] == str(self.task.pk) for row in rows))

    def test_older_pending_task_is_available_on_a_bounded_second_page(self):
        for _ in range(50):
            ReviewTask.objects.create(document=self.document, kind="review", status="approved",
                assignee=self.reviewer, assignee_username=self.reviewer.username,
                requested_by=self.requester, requested_by_username=self.requester.username,
                request_note="Later review.", source_version=1)
        response = self.client.get(self.url + "reviews/", {"page": 2, "page_size": 50})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 51)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.task.pk))
        self.assertTrue(response.data["results"][0]["allowed_actions"]["approve"])
