import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.test import SimpleTestCase

from jobs.artifacts import (
    _fsync_directory,
    publish_staged_job_output,
    remove_temporary_artifact,
)


class DirectorySyncTests(SimpleTestCase):
    def test_windows_skips_unsupported_directory_handle_sync(self):
        artifact = SimpleNamespace(
            staging_path=Path("private-artifacts/.staging/result.part"),
            final_path=Path("private-artifacts/jobs/result.docx"),
        )
        with (
            patch("jobs.artifacts.sys.platform", "win32"),
            patch("pathlib.Path.mkdir"),
            patch("jobs.artifacts.os.replace") as replace,
            patch("jobs.artifacts.os.open") as open_directory,
        ):
            publish_staged_job_output(artifact)

        replace.assert_called_once_with(artifact.staging_path, artifact.final_path)
        open_directory.assert_not_called()

    def test_supported_platform_syncs_and_closes_directory(self):
        with (
            patch("jobs.artifacts.sys.platform", "linux"),
            patch("jobs.artifacts.os.open", return_value=17) as open_directory,
            patch("jobs.artifacts.os.fsync") as fsync,
            patch("jobs.artifacts.os.close") as close,
        ):
            _fsync_directory(Path("private-artifacts"))

        open_directory.assert_called_once()
        fsync.assert_called_once_with(17)
        close.assert_called_once_with(17)


class TemporaryArtifactCleanupTests(SimpleTestCase):
    def test_transient_windows_lock_is_retried(self):
        with (
            patch.object(Path, "unlink", side_effect=[PermissionError(), None]) as unlink,
            patch("jobs.artifacts.time.sleep") as sleep,
        ):
            removed = remove_temporary_artifact(Path("temporary.docx"))

        self.assertTrue(removed)
        self.assertEqual(
            unlink.call_args_list,
            [call(missing_ok=True), call(missing_ok=True)],
        )
        sleep.assert_called_once_with(0.1)

    def test_persistent_cleanup_lock_cannot_fail_completed_job(self):
        with (
            patch.object(Path, "unlink", side_effect=PermissionError()) as unlink,
            patch("jobs.artifacts.time.sleep"),
            self.assertLogs("jobs.artifacts", "WARNING") as logs,
        ):
            removed = remove_temporary_artifact(Path("temporary.docx"))

        self.assertFalse(removed)
        self.assertEqual(unlink.call_count, 6)
        self.assertNotIn("temporary.docx", " ".join(logs.output))


class PosixDirectorySyncTests(SimpleTestCase):
    """Keep POSIX directory durability and storage failures observable."""

    def setUp(self):
        self.artifact_os = SimpleNamespace(**vars(os))
        platform_patcher = patch("jobs.artifacts.sys", SimpleNamespace(platform="linux"))
        platform_patcher.start()
        self.addCleanup(platform_patcher.stop)
        self.artifact_os.open = Mock(return_value=42)
        self.artifact_os.fsync = Mock()
        self.artifact_os.close = Mock()
        patcher = patch("jobs.artifacts.os", self.artifact_os)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_posix_directory_is_synced_and_closed(self):
        _fsync_directory(Path("artifact-directory"))

        self.artifact_os.fsync.assert_called_once_with(42)
        self.artifact_os.close.assert_called_once_with(42)

    def test_posix_sync_failure_propagates_and_closes_descriptor(self):
        self.artifact_os.fsync.side_effect = OSError("sync failed")

        with self.assertRaises(OSError):
            _fsync_directory(Path("artifact-directory"))

        self.artifact_os.close.assert_called_once_with(42)

    def test_posix_permission_failure_is_not_suppressed(self):
        self.artifact_os.open.side_effect = PermissionError("Permission denied")

        with self.assertRaises(PermissionError):
            _fsync_directory(Path("artifact-directory"))

        self.artifact_os.fsync.assert_not_called()
        self.artifact_os.close.assert_not_called()
