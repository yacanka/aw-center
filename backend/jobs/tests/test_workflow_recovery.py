from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from jobs.models import WorkflowRun, WorkflowStatus
from jobs.workflow_controls import reconcile_active_workflows

from .base import JobTestCase
from .test_workflows import RECIPE
from .test_document_jobs import word_upload


class WorkflowRecoveryTests(JobTestCase):
    """Verify bounded worker polling and interrupted initialization recovery."""

    def test_idle_recovery_scan_has_bounded_query_cost(self):
        """Worker polling does not add one recovery query per active workflow."""

        for index in range(5):
            self.client.post(
                "/jobs/workflows/",
                {"recipe": RECIPE, "translate_type": "tr2en", "file": word_upload()},
                format="multipart", HTTP_IDEMPOTENCY_KEY=f"workflow-query-{index}",
            )

        with CaptureQueriesContext(connection) as queries:
            reconcile_active_workflows()

        self.assertLessEqual(len(queries), 2)

    def test_interrupted_initialization_becomes_actionable_failure(self):
        """A stale workflow without its first job cannot remain queued forever."""

        workflow = WorkflowRun.objects.create(
            owner=self.user, recipe=RECIPE, title="Interrupted workflow",
            parameters={"translate_type": "tr2en"}, input_name="document.docx",
            input_sha256="0" * 64, total_steps=2, message="Workflow queued.",
        )
        WorkflowRun.objects.filter(pk=workflow.pk).update(
            created_at=timezone.now() - timedelta(minutes=1)
        )

        reconcile_active_workflows()

        workflow.refresh_from_db()
        self.assertEqual(workflow.status, WorkflowStatus.FAILED)
        self.assertEqual(workflow.error_code, "WORKFLOW_INITIALIZATION_FAILED")
        self.assertTrue(workflow.events.filter(code="WORKFLOW_INITIALIZATION_FAILED").exists())
