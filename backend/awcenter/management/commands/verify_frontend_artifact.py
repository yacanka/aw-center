from django.core.management.base import BaseCommand, CommandError

from awcenter.frontend_artifact import FrontendArtifactError, verify_frontend_artifact


class Command(BaseCommand):
    help = "Verify the Vite shell, referenced assets, and Django SPA fallback."

    def handle(self, *args, **options):
        try:
            result = verify_frontend_artifact()
        except FrontendArtifactError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Frontend artifact verified: {result['asset_count']} assets, "
                f"{result['index_bytes']} index bytes."
            )
        )
