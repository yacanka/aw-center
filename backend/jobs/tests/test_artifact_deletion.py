"""Exercise committed and rolled-back deletion against real private files."""

import os
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from jobs.models import Job, JobStatus
from jobs.retention import cleanup_expired_jobs
from jobs.services import create_job


class JobArtifactDeletionTests(TransactionTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings_override = override_settings(PRIVATE_MEDIA_ROOT=Path(temporary.name))
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.owner = get_user_model().objects.create_user(username="artifact-owner")
        self.job, _ = create_job(
            self.owner, "media.convert", "Convert", {},
            SimpleUploadedFile("sample.jpg", b"\xff\xd8\xffpayload", content_type="image/jpeg"),
        )
        self.job.output_file.save("result.txt", ContentFile(b"output"))
        self.storage = self.job.input_file.storage
        self.names = (self.job.input_file.name, self.job.output_file.name)
        self.job_id = self.job.pk

    def assert_artifacts_exist(self):
        for name in self.names:
            self.assertTrue(self.storage.exists(name))

    def test_rollback_restores_job_without_losing_either_artifact(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.job.delete()
                self.assert_artifacts_exist()
                raise RuntimeError("rollback fixture")

        self.assertTrue(Job.objects.filter(pk=self.job_id).exists())
        self.assert_artifacts_exist()

    def test_commit_deletes_captured_artifacts_and_preserves_unrelated_files(self):
        unrelated = self.storage.save("unrelated.txt", ContentFile(b"keep"))
        with transaction.atomic():
            self.job.delete()
            self.assert_artifacts_exist()
            self.job.input_file.name = unrelated
            self.job.output_file.name = unrelated

        self.assertFalse(Job.objects.filter(pk=self.job_id).exists())
        for name in self.names:
            self.assertFalse(self.storage.exists(name))
        self.assertTrue(self.storage.exists(unrelated))

    def test_savepoint_rollback_discards_cleanup_even_when_outer_transaction_commits(self):
        with transaction.atomic():
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self.job.delete()
                    raise RuntimeError("savepoint rollback fixture")
            self.assertTrue(Job.objects.filter(pk=self.job_id).exists())

        self.assert_artifacts_exist()

    def test_owner_cascade_rollback_keeps_job_artifacts(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.owner.delete()
                raise RuntimeError("cascade rollback fixture")

        self.assertTrue(Job.objects.filter(pk=self.job_id).exists())
        self.assert_artifacts_exist()

    def test_failed_input_delete_does_not_block_output_and_cleanup_retries_later(self):
        real_delete = self.storage.delete

        def locked_input(name):
            if name == self.names[0]:
                raise PermissionError("private storage path fixture")
            real_delete(name)

        with patch.object(self.storage, "delete", side_effect=locked_input):
            with self.assertLogs("jobs.signals", level="WARNING") as logs:
                self.job.delete()
        self.assertNotIn("private storage path fixture", " ".join(logs.output))
        self.assertFalse(Job.objects.filter(pk=self.job_id).exists())
        self.assertTrue(self.storage.exists(self.names[0]))
        self.assertFalse(self.storage.exists(self.names[1]))

        cleanup_expired_jobs()
        self.assertTrue(self.storage.exists(self.names[0]))

        old = (timezone.now() - timedelta(days=2)).timestamp()
        os.utime(self.storage.path(self.names[0]), (old, old))
        cleanup_expired_jobs()
        self.assertFalse(self.storage.exists(self.names[0]))

    def test_cleanup_preserves_old_referenced_inputs(self):
        old = (timezone.now() - timedelta(days=2)).timestamp()
        for name in self.names:
            os.utime(self.storage.path(name), (old, old))
        cleanup_expired_jobs()
        self.assert_artifacts_exist()

    def test_retention_rollback_preserves_expired_job_and_both_artifacts(self):
        old = timezone.now() - timedelta(days=2)
        self.job.status = JobStatus.FAILED
        self.job.completed_at = old
        self.job.save(update_fields=["status", "completed_at"])
        for name in self.names:
            os.utime(self.storage.path(name), (old.timestamp(), old.timestamp()))

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                cleanup_expired_jobs(days=1)
                self.assert_artifacts_exist()
                raise RuntimeError("retention rollback fixture")

        self.assertTrue(Job.objects.filter(pk=self.job_id).exists())
        self.assert_artifacts_exist()

    def test_retention_commit_cleans_files_only_after_outer_transaction(self):
        self.job.status = JobStatus.FAILED
        self.job.completed_at = timezone.now() - timedelta(days=2)
        self.job.save(update_fields=["status", "completed_at"])

        with transaction.atomic():
            cleanup_expired_jobs(days=1)
            self.assert_artifacts_exist()

        self.assertFalse(Job.objects.filter(pk=self.job_id).exists())
        for name in self.names:
            self.assertFalse(self.storage.exists(name))
