"""Run ingress-gating first-production release smoke scenarios."""

from django.core.management.base import BaseCommand, CommandError

from awcenter.release_smoke import (
    ReleaseSmokeError,
    run_core_smoke,
    run_notification_smoke,
)


class Command(BaseCommand):
    help = "Run one exact-cleanup smoke stage before first production ingress opens."

    def add_arguments(self, parser):
        parser.add_argument("--stage", choices=("core", "notification"), required=True)
        parser.add_argument("--operator-username", required=True)
        parser.add_argument("--project", default="hys")
        parser.add_argument("--notification-recipient")
        parser.add_argument("--confirm-fresh-install", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_fresh_install"]:
            raise CommandError("Pass --confirm-fresh-install after verifying the database is unused.")
        try:
            if options["stage"] == "core":
                result = run_core_smoke(
                    operator_username=options["operator_username"],
                    project_slug=options["project"],
                )
            else:
                recipient = str(options.get("notification_recipient") or "").strip()
                if not recipient:
                    raise CommandError("--notification-recipient is required for notification smoke.")
                result = run_notification_smoke(
                    operator_username=options["operator_username"],
                    recipient=recipient,
                )
        except ReleaseSmokeError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                "Release smoke passed: "
                + ", ".join(f"{key}={value}" for key, value in result.items())
            )
        )
