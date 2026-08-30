"""Explicit, fenced, and durably audited compliance-document purge."""

from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from compliance.models import ComplianceDocument, DocumentPurgeAudit


class Command(BaseCommand):
    """Permanently delete exactly one archived document after operator confirmation."""

    help = "Permanently purge one archived compliance document and retain audit evidence."

    def add_arguments(self, parser):
        parser.add_argument("--document-id", required=True, type=UUID)
        parser.add_argument("--confirm-document-id", required=True, type=UUID)
        parser.add_argument("--expected-version", required=True, type=int)
        parser.add_argument("--operator", required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **options):
        document_id = options["document_id"]
        if options["confirm_document_id"] != document_id:
            raise CommandError("The confirmation document ID does not match.")
        expected_version = options["expected_version"]
        if expected_version < 1:
            raise CommandError("Expected version must be positive.")
        reason = str(options["reason"] or "").strip()
        if not 3 <= len(reason) <= 255:
            raise CommandError("Reason must contain between 3 and 255 characters.")

        user_model = get_user_model()
        try:
            operator = user_model.objects.get(username=options["operator"], is_active=True)
        except user_model.DoesNotExist as error:
            raise CommandError("The purge operator is unavailable.") from error
        if not operator.is_superuser:
            raise CommandError("Only an active superuser may purge compliance documents.")

        with transaction.atomic():
            try:
                document = (
                    ComplianceDocument.objects.select_for_update()
                    .select_related("project")
                    .get(pk=document_id)
                )
            except ComplianceDocument.DoesNotExist as error:
                raise CommandError("The compliance document does not exist.") from error
            if not document.is_archived:
                raise CommandError("Archive the compliance document before purging it.")
            if document.version != expected_version:
                raise CommandError("The compliance document version changed before purge.")

            project = document.project
            document_version = document.version
            document._history_user = operator
            document._change_reason = reason[:100]
            document.delete()
            DocumentPurgeAudit.objects.create(
                document_id=document_id,
                project=project,
                document_version=document_version,
                purged_by=operator,
                purged_by_username=operator.get_username(),
                reason=reason,
            )

        self.stdout.write(self.style.SUCCESS(f"Purged compliance document {document_id}."))
