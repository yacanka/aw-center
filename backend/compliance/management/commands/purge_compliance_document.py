"""Explicit, fenced, and durably audited compliance-document purge."""

from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from compliance.purging import DocumentPurgeError, purge_document


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
        try:
            purge_document(
                document_id=document_id,
                expected_version=expected_version,
                operator=operator,
                reason=reason,
            )
        except DocumentPurgeError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS(f"Purged compliance document {document_id}."))
