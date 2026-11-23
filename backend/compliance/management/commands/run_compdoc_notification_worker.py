"""Run the periodic Compliance Documents notification scanner."""

import logging
import os
import signal
from pathlib import Path
from threading import Event

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from compliance.models import NotificationLog
from compliance.notifications import scan_notifications
from integrations.jira.reminder_notifications import process_dcc_reminder_deliveries
from integrations.jira.workflow_models import JiraReminderDelivery
from users.models import PasswordResetDelivery
from users.password_reset_notifications import process_password_reset_deliveries

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    """Process durable outbound notification queues."""

    help = "Run password-reset, DCC reminder, and Compliance Documents notification queues."

    def add_arguments(self, parser):
        """Register bounded worker controls."""

        parser.add_argument("--once", action="store_true")
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=settings.COMPDOC_NOTIFICATION_POLL_SECONDS,
        )
        parser.add_argument("--project")
        parser.add_argument("--heartbeat-file")

    def handle(self, *args, **options):
        """Scan until stopped or complete one explicit pass."""

        self.stop_event = Event()
        self._install_signal_handlers()
        heartbeat_file = options["heartbeat_file"]
        if heartbeat_file:
            Path(heartbeat_file).unlink(missing_ok=True)
        ready_file = os.environ.get("AWCENTER_NOTIFICATION_READY_FILE")
        if ready_file:
            self._signal_startup(Path(ready_file))
        while not self.stop_event.is_set():
            succeeded = self._run_scan(options["project"])
            if succeeded and heartbeat_file:
                Path(heartbeat_file).touch()
            if options["once"]:
                return
            self.stop_event.wait(max(10, options["poll_interval"]))

    def _signal_startup(self, ready_file):
        ready_file.unlink(missing_ok=True)
        # Use read-only probes so startup doesn't wait for queued deliveries or SMTP.
        try:
            for queue in (PasswordResetDelivery, JiraReminderDelivery, NotificationLog):
                queue.objects.exists()
        except DatabaseError:
            raise CommandError("Notification queue database is unavailable. Check its schema and access.") from None
        ready_file.touch()

    def _run_scan(self, project):
        try:
            reset_result = process_password_reset_deliveries()
            dcc_result = process_dcc_reminder_deliveries()
            compliance_result = scan_notifications(project_slug=project)
            self.stdout.write(
                "Notifications: "
                f"password_reset_processed={reset_result['processed']} "
                f"password_reset_sent={reset_result['sent']} "
                f"password_reset_failed={reset_result['failed']} "
                f"dcc_processed={dcc_result['processed']} "
                f"dcc_sent={dcc_result['sent']} "
                f"dcc_failed={dcc_result['failed']} "
                f"compliance_processed={compliance_result['processed']} "
                f"compliance_sent={compliance_result['sent']} "
                f"compliance_failed={compliance_result['failed']}"
            )
            return True
        except Exception:
            LOGGER.exception("CompDoc notification scan failed.")
            self.stderr.write("CompDoc notification scan failed; the worker will retry.")
            return False

    def _install_signal_handlers(self):
        def stop_worker(*_args):
            self.stop_event.set()

        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)
