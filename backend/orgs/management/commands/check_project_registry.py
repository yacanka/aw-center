"""Validate database projects against the central project registry."""

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from orgs.models import Project
from projects.registry import PROJECT_DEFINITIONS, get_enabled_project_definitions


class Command(BaseCommand):
    """Report registry/database project slug alignment without mutating data."""

    help = "Checks orgs.Project rows against enabled project registry definitions."

    def handle(self, *args, **options):
        """Run a read-only registry alignment check."""
        database_slugs = self.get_database_slugs()
        missing_slugs = self.get_missing_enabled_slugs(database_slugs)
        unknown_slugs = self.get_unknown_database_slugs(database_slugs)

        self.write_warning_lines(unknown_slugs)

        if missing_slugs:
            raise CommandError(self.build_missing_message(missing_slugs))

        self.stdout.write(self.style.SUCCESS("Project registry alignment check passed."))

    @staticmethod
    def get_database_slugs():
        """Return existing orgs.Project slugs or fail when tables are unavailable."""
        try:
            return set(Project.objects.values_list("slug", flat=True))
        except (OperationalError, ProgrammingError) as error:
            raise CommandError("orgs.Project table is unavailable; run migrations first.") from error

    @staticmethod
    def get_missing_enabled_slugs(database_slugs):
        """Return enabled registry slugs absent from orgs.Project."""
        enabled_slugs = {definition.slug for definition in get_enabled_project_definitions()}
        return sorted(enabled_slugs - database_slugs)

    @staticmethod
    def get_unknown_database_slugs(database_slugs):
        """Return database project slugs absent from the registry."""
        registry_slugs = set(PROJECT_DEFINITIONS)
        return sorted(database_slugs - registry_slugs)

    def write_warning_lines(self, unknown_slugs):
        """Write non-destructive warnings for database-only project slugs."""
        if not unknown_slugs:
            return

        message = "Active orgs.Project rows missing from registry: "
        self.stderr.write(self.style.WARNING(message + ", ".join(unknown_slugs)))

    @staticmethod
    def build_missing_message(missing_slugs):
        """Return the failure message for missing enabled registry projects."""
        return "Enabled registry projects missing from orgs.Project: " + ", ".join(missing_slugs)
