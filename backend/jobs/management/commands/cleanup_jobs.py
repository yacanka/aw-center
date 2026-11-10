from django.core.management.base import BaseCommand

from jobs.retention import cleanup_expired_jobs


class Command(BaseCommand):
    """Delete expired previews, terminal jobs, and their private artifacts."""

    help = "Delete expired confirmation previews and retained terminal job artifacts."

    def add_arguments(self, parser):
        """Register an optional retention override."""

        parser.add_argument("--days", type=int)

    def handle(self, *args, **options):
        """Apply one bounded retention pass."""

        result = cleanup_expired_jobs(options["days"])
        self.stdout.write(
            f"Deleted {result.expired_previews} expired unconfirmed job previews."
        )
        self.stdout.write(
            f"Deleted {result.deleted_objects} expired job records and related events."
        )
        self.stdout.write(
            f"Deleted {result.deleted_staging_files} orphan staging artifacts."
        )
        self.stdout.write(
            f"Deleted {result.deleted_orphan_outputs} unreferenced output artifacts."
        )
