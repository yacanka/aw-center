from django.core.management.base import BaseCommand, CommandError

from awcenter.frontend_artifact import FrontendArtifactError, verify_frontend_artifact


class Command(BaseCommand):
    """Block deployment when Django cannot serve the built Vite artifact."""

    help = "Verify the Vite shell, referenced assets, and Django SPA fallback."

    def handle(self, *args, **options):
        """Run the deployment artifact verifier and print a bounded summary."""

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
