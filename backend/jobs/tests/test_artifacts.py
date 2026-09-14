from pathlib import Path
from unittest.mock import call, patch

from django.test import SimpleTestCase

from jobs.artifacts import remove_temporary_artifact


class TemporaryArtifactCleanupTests(SimpleTestCase):
    def test_cleanup_retries_a_transient_permission_error(self):
        path = Path("temporary-result.docx")

        with (
            patch.object(
                Path,
                "unlink",
                side_effect=[PermissionError("file is temporarily locked"), None],
            ) as unlink,
            patch("jobs.artifacts.time.sleep") as sleep,
        ):
            remove_temporary_artifact(path)

        self.assertEqual(
            unlink.call_args_list,
            [call(missing_ok=True), call(missing_ok=True)],
        )
        sleep.assert_called_once_with(0.05)

    def test_cleanup_does_not_hide_a_persistent_permission_error(self):
        path = Path("temporary-result.docx")

        with (
            patch.object(
                Path, "unlink", side_effect=PermissionError("still locked")
            ) as unlink,
            patch("jobs.artifacts.time.sleep") as sleep,
            self.assertRaises(PermissionError),
        ):
            remove_temporary_artifact(path)

        self.assertEqual(unlink.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
