"""Synchronize organization projects from the central project registry."""

from dataclasses import dataclass

from django.core.management.base import BaseCommand

from orgs.models import Project
from projects.registry import PROJECT_DEFINITIONS
from projects.types import ProjectDefinition


@dataclass(frozen=True)
class SyncSummary:
    """Collect the synchronization outcome counters."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_disabled: int = 0


class Command(BaseCommand):
    """Create missing org projects from registry metadata."""

    help = "Create missing orgs.Project rows from the project registry."

    def add_arguments(self, parser):
        """Register command-line flags for safe synchronization."""
        parser.add_argument(
            "--update-display-name",
            action="store_true",
            help="Update existing Project.name values from registry display names.",
        )
        parser.add_argument(
            "--include-disabled",
            action="store_true",
            help="Also create registry projects marked as disabled.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show planned changes without writing to the database.",
        )

    def handle(self, *args, **options):
        """Synchronize registry project definitions into orgs.Project."""
        summary = SyncSummary()
        for definition in PROJECT_DEFINITIONS.values():
            summary = self._sync_definition(definition, summary, options)
        self._write_summary(summary, options["dry_run"])

    def _sync_definition(self, definition, summary, options):
        if not definition.enabled and not options["include_disabled"]:
            self._write_skip(definition)
            return self._replace(summary, skipped_disabled=summary.skipped_disabled + 1)

        project = Project.objects.filter(slug=definition.slug).first()
        if project is None:
            return self._create_project(definition, summary, options["dry_run"])
        return self._sync_existing_project(project, definition, summary, options)

    def _create_project(self, definition, summary, dry_run):
        if not dry_run:
            Project.objects.create(slug=definition.slug, name=definition.display_name)
        self.stdout.write(f"CREATE {definition.slug}: {definition.display_name}")
        return self._replace(summary, created=summary.created + 1)

    def _sync_existing_project(self, project, definition, summary, options):
        if project.name == definition.display_name:
            self.stdout.write(f"UNCHANGED {definition.slug}: {project.name}")
            return self._replace(summary, unchanged=summary.unchanged + 1)
        if not options["update_display_name"]:
            self.stdout.write(f"UNCHANGED {definition.slug}: existing name preserved")
            return self._replace(summary, unchanged=summary.unchanged + 1)
        return self._update_project(project, definition, summary, options["dry_run"])

    def _update_project(self, project, definition, summary, dry_run):
        old_name = project.name
        if not dry_run:
            project.name = definition.display_name
            project.save(update_fields=["name"])
        self.stdout.write(f"UPDATE {definition.slug}: {old_name} -> {definition.display_name}")
        return self._replace(summary, updated=summary.updated + 1)

    def _write_skip(self, definition: ProjectDefinition):
        self.stdout.write(f"SKIP disabled {definition.slug}: {definition.display_name}")

    def _write_summary(self, summary: SyncSummary, dry_run: bool):
        prefix = "DRY RUN " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}created={summary.created} updated={summary.updated} "
                f"unchanged={summary.unchanged} skipped_disabled={summary.skipped_disabled}"
            )
        )

    def _replace(self, summary, **changes):
        values = {
            "created": summary.created,
            "updated": summary.updated,
            "unchanged": summary.unchanged,
            "skipped_disabled": summary.skipped_disabled,
        }
        values.update(changes)
        return SyncSummary(**values)
