"""Retention removes abandoned execution scratch without touching live claims."""

import os
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from jobs.models import JobStatus
from jobs.retention import cleanup_expired_jobs
from jobs.services import create_job
from jobs.worker import claim_next_job


class ExecutionScratchRetentionTests(TransactionTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        override = override_settings(PRIVATE_MEDIA_ROOT=self.root / "private")
        override.enable()
        self.addCleanup(override.disable)
        self.owner = get_user_model().objects.create_user("scratch-retention-owner")
        create_job(self.owner, "test.scratch", "Scratch", {}, ContentFile(b"{}", name="input.json"))
        self.job = claim_next_job("scratch-retention-worker", ["test.scratch"])

    def scratch_directory(self, *, token=None, old=True):
        directory = (
            self.root / "private/.scratch/jobs" / str(self.owner.pk)
            / str(self.job.pk) / (token or self.job.execution_token.hex)
        )
        directory.mkdir(parents=True)
        (directory / "input.json").write_bytes(b"private test payload")
        if old:
            timestamp = (timezone.now() - timedelta(days=2)).timestamp()
            os.utime(directory, (timestamp, timestamp))
        return directory

    def test_cleanup_removes_old_scratch_after_job_disappears(self):
        directory = self.scratch_directory()
        self.job.delete()

        cleanup_expired_jobs()

        self.assertFalse(directory.exists())

    def test_cleanup_preserves_current_claim_even_when_lease_is_expired(self):
        directory = self.scratch_directory()
        self.job.lease_expires_at = timezone.now() - timedelta(days=1)
        self.job.save(update_fields=["lease_expires_at"])

        cleanup_expired_jobs()

        self.assertEqual((directory / "input.json").read_bytes(), b"private test payload")

    def test_cleanup_removes_replaced_claim_and_preserves_current_claim(self):
        stale = self.scratch_directory(token=uuid4().hex)
        active = self.scratch_directory()

        cleanup_expired_jobs()

        self.assertFalse(stale.exists())
        self.assertTrue((active / "input.json").exists())

    def test_cleanup_preserves_recent_unreferenced_scratch(self):
        directory = self.scratch_directory(old=False)
        self.job.status = JobStatus.FAILED
        self.job.save(update_fields=["status"])

        cleanup_expired_jobs()

        self.assertTrue((directory / "input.json").exists())

    def test_cleanup_ignores_unrecognized_directory_names(self):
        directory = self.scratch_directory(token="unrelated-directory")

        cleanup_expired_jobs()

        self.assertTrue((directory / "input.json").exists())

    def test_cleanup_does_not_follow_symlinks_outside_scratch(self):
        outside = self.root / "unrelated"
        outside.mkdir()
        payload = outside / "keep.txt"
        payload.write_bytes(b"keep unrelated data")
        directory = self.scratch_directory(token=uuid4().hex)
        (directory / "input.json").unlink()
        directory.rmdir()
        try:
            directory.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating directory symlinks is unavailable on this host.")

        cleanup_expired_jobs()

        self.assertTrue(directory.is_symlink())
        self.assertEqual(payload.read_bytes(), b"keep unrelated data")
