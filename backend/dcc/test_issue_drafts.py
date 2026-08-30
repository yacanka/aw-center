"""Canonical role and durable-enqueue tests for JIRA issue drafts."""

import hashlib
import json
from unittest.mock import patch

from django.core.files.base import ContentFile

from jobs.models import Job, JobStatus
from jobs.tests.base import JobTestCase
from orgs.models import Project, ProjectRoleAssignment

from dcc.issue_draft_models import JiraIssueDraft, JiraIssueDraftStatus


class JiraIssueDraftApiTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.source_job = create_analysis_job(self.user)
        self.first = Project.objects.get(slug="hys")
        self.second = Project.objects.get(slug="gokbey")

    def grant(self, user, project, role):
        return ProjectRoleAssignment.objects.create(
            user=user,
            project=project,
            domain=ProjectRoleAssignment.Domain.DCC,
            role=role,
        )

    def grant_all(self, user, role):
        self.grant(user, self.first, role)
        self.grant(user, self.second, role)

    def create_draft(self, *, assigned_users=()):
        response = self.client.post(
            "/api/dcc/issue-drafts/",
            {
                "source_job_id": str(self.source_job.id),
                "project_key": "CHN",
                "project_slugs": [self.first.slug, self.second.slug],
                "assigned_users": [user.pk for user in assigned_users],
            },
            format="json",
        )
        self.assertIn(response.status_code, {200, 201})
        return response

    def approve(self, draft):
        response = self.client.post(
            f"/api/dcc/issue-drafts/{draft['id']}/approve/",
            {"version": draft["version"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_create_requires_operator_on_every_project_and_is_exactly_replayable(self):
        self.grant(self.user, self.first, ProjectRoleAssignment.Role.OPERATOR)
        blocked = self.client.post(
            "/api/dcc/issue-drafts/",
            {
                "source_job_id": str(self.source_job.id),
                "project_slugs": [self.first.slug, self.second.slug],
            },
            format="json",
        )
        self.grant(self.user, self.second, ProjectRoleAssignment.Role.OPERATOR)
        first = self.create_draft()
        replay = self.create_draft()

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(
            set(first.data["project_slugs"]),
            {self.first.slug, self.second.slug},
        )
        self.assertNotIn("projects", first.data)
        self.assertEqual(
            first.data["allowed_actions"],
            {
                "edit": True,
                "approve": True,
                "preflight": False,
                "publish": False,
            },
        )

    def test_assigned_viewer_must_hold_viewer_role_on_every_project(self):
        self.grant_all(self.user, ProjectRoleAssignment.Role.OPERATOR)
        draft = self.create_draft(assigned_users=[self.other_user]).data
        self.grant(self.other_user, self.first, ProjectRoleAssignment.Role.VIEWER)
        self.client.force_authenticate(self.other_user)
        url = f"/api/dcc/issue-drafts/{draft['id']}/"

        blocked = self.client.get(url)
        self.grant(self.other_user, self.second, ProjectRoleAssignment.Role.VIEWER)
        allowed = self.client.get(url)

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(any(allowed.data["allowed_actions"].values()))

    def test_preflight_requires_current_version_and_publisher_on_every_project(self):
        self.grant(self.user, self.first, ProjectRoleAssignment.Role.PUBLISHER)
        self.grant(self.user, self.second, ProjectRoleAssignment.Role.OPERATOR)
        draft = self.create_draft().data
        blocked = self.client.post(
            f"/api/dcc/issue-drafts/{draft['id']}/preflight/",
            {"version": draft["version"]},
            format="json",
        )
        assignment = ProjectRoleAssignment.objects.get(
            user=self.user, project=self.second, domain=ProjectRoleAssignment.Domain.DCC
        )
        assignment.role = ProjectRoleAssignment.Role.PUBLISHER
        assignment.save()
        with patch("dcc.issue_draft_views.jira_connector_for") as connector_for:
            connector_for.return_value.get_create_fields.return_value = create_metadata()
            allowed = self.client.post(
                f"/api/dcc/issue-drafts/{draft['id']}/preflight/",
                {"version": draft["version"]},
                format="json",
            )

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(allowed.data["ready"])

    def test_patch_updates_only_supplied_draft_fields(self):
        self.grant_all(self.user, ProjectRoleAssignment.Role.OPERATOR)
        draft = self.create_draft().data

        response = self.client.patch(
            f"/api/dcc/issue-drafts/{draft['id']}/",
            {"version": draft["version"], "summary": "Focused review"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"], "Focused review")
        self.assertEqual(response.data["description"], draft["description"])
        self.assertEqual(response.data["project_key"], draft["project_key"])

    def test_publish_enqueues_credential_free_fenced_job_and_never_calls_jira(self):
        self.grant_all(self.user, ProjectRoleAssignment.Role.PUBLISHER)
        approved = self.approve(self.create_draft().data)
        self.assertTrue(approved["allowed_actions"]["publish"])
        url = f"/api/dcc/issue-drafts/{approved['id']}/publish/"

        missing_key = self.client.post(
            url,
            {"version": approved["version"]},
            format="json",
        )
        with patch("dcc.issue_draft_views.jira_connector_for") as connector_for:
            queued = self.client.post(
                url,
                {"version": approved["version"]},
                format="json",
                HTTP_IDEMPOTENCY_KEY="publish-draft-request-1",
            )

        self.assertEqual(missing_key.status_code, 400)
        self.assertEqual(queued.status_code, 201)
        connector_for.assert_not_called()
        job = Job.objects.get(pk=queued.data["id"])
        draft = JiraIssueDraft.objects.get(pk=approved["id"])
        self.assertEqual(job.kind, "dcc.publish_jira_draft")
        self.assertEqual(draft.status, JiraIssueDraftStatus.PUBLISHING)
        self.assertEqual(draft.publication_job, job)
        serialized = json.dumps(job.parameters).lower()
        with job.input_file.open("rb") as source:
            stored_input = source.read().lower()
        for credential_name in ("jsessionid", "password", "credential", "token"):
            self.assertNotIn(credential_name, serialized)
            self.assertNotIn(credential_name.encode(), stored_input)

    def test_publish_idempotency_replays_same_job_after_state_reservation(self):
        self.grant_all(self.user, ProjectRoleAssignment.Role.PUBLISHER)
        approved = self.approve(self.create_draft().data)
        url = f"/api/dcc/issue-drafts/{approved['id']}/publish/"
        headers = {"HTTP_IDEMPOTENCY_KEY": "publish-draft-request-2"}

        first = self.client.post(url, {"version": approved["version"]}, format="json", **headers)
        replay = self.client.post(url, {"version": approved["version"]}, format="json", **headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(Job.objects.filter(kind="dcc.publish_jira_draft").count(), 1)

    def test_assigned_publisher_can_enqueue_but_unassigned_publisher_cannot(self):
        self.grant_all(self.user, ProjectRoleAssignment.Role.OPERATOR)
        draft = self.create_draft(assigned_users=[self.other_user]).data
        approved = self.approve(draft)
        self.grant_all(self.other_user, ProjectRoleAssignment.Role.PUBLISHER)
        outsider = type(self.user).objects.create_user("unassigned-publisher")
        self.grant_all(outsider, ProjectRoleAssignment.Role.PUBLISHER)
        url = f"/api/dcc/issue-drafts/{approved['id']}/publish/"

        self.client.force_authenticate(outsider)
        hidden = self.client.post(
            url,
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="unassigned-publisher-1",
        )
        self.client.force_authenticate(self.other_user)
        queued = self.client.post(
            url,
            {"version": approved["version"]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="assigned-publisher-1",
        )

        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(queued.status_code, 201)
        self.assertEqual(Job.objects.get(pk=queued.data["id"]).owner, self.other_user)

    def test_raw_session_fields_are_rejected_not_persisted(self):
        self.grant_all(self.user, ProjectRoleAssignment.Role.PUBLISHER)
        approved = self.approve(self.create_draft().data)

        response = self.client.post(
            f"/api/dcc/issue-drafts/{approved['id']}/publish/",
            {"version": approved["version"], "JSESSIONID": "never-store-this"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="publish-draft-request-3",
        )
        query_response = self.client.get(
            f"/api/dcc/issue-drafts/{approved['id']}/"
            "?JSESSIONID=never-enter-a-url"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "JIRA_SESSION_CANONICAL_REQUIRED")
        self.assertEqual(query_response.status_code, 400)
        self.assertEqual(
            query_response.data["code"],
            "JIRA_SESSION_CANONICAL_REQUIRED",
        )
        self.assertNotIn("never-enter-a-url", json.dumps(query_response.data))
        self.assertFalse(Job.objects.filter(kind="dcc.publish_jira_draft").exists())

    def test_projectless_draft_fails_closed(self):
        draft = direct_draft(self.user, self.source_job)
        self.client.force_authenticate(self.user)

        response = self.client.get(f"/api/dcc/issue-drafts/{draft.id}/")

        self.assertEqual(response.status_code, 403)


def create_analysis_job(owner):
    payload = json.dumps(
        {
            "document": "review.docx",
            "checks": [
                {
                    "id": "approvals",
                    "title": "Approval information",
                    "score": 0.4,
                    "status": "error",
                    "explanation": "Approval section is weak.",
                    "evidence": [{"text": "Approval evidence", "heading": "Approvals"}],
                }
            ],
        }
    ).encode()
    job = Job.objects.create(
        owner=owner,
        kind="word.analyze",
        title="Analyze",
        status=JobStatus.SUCCEEDED,
        input_name="review.docx",
        input_sha256="1" * 64,
        output_name="analysis.json",
        output_sha256=hashlib.sha256(payload).hexdigest(),
    )
    job.output_file.save("analysis.json", ContentFile(payload), save=True)
    return job


def direct_draft(owner, source_job):
    return JiraIssueDraft.objects.create(
        owner=owner,
        source_job=source_job,
        project_key="CHN",
        summary="Review",
        description="Evidence",
        marker_label="aw-center-projectless",
    )


def create_metadata():
    base = [
        {
            "id": identifier,
            "name": identifier.title(),
            "required": True,
            "schema": {"type": "string"},
            "allowedValues": [],
        }
        for identifier in ("summary", "description", "labels")
    ]
    base.append(
        {
            "id": "customfield_10001",
            "name": "Safety level",
            "required": True,
            "hasDefaultValue": False,
            "schema": {"type": "option"},
            "allowedValues": [{"id": "100", "value": "High"}],
        }
    )
    return base
