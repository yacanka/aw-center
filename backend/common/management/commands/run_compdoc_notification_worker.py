"""Run the periodic Compliance Documents notification scanner."""

import signal
import time
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from common.compdoc_notification_scan import scan_enabled_profiles

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    """Process opted-in overdue, due-soon, and DocProof revision notifications."""

    help = "Run the Compliance Documents notification scanner."

    def add_arguments(self, parser):
        """Register bounded worker controls."""

        parser.add_argument("--once", action="store_true")
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=settings.COMPDOC_NOTIFICATION_POLL_SECONDS,
        )
        parser.add_argument("--project")

    def handle(self, *args, **options):
        """Scan until stopped or complete one explicit pass."""

        self.stopping = False
        self._install_signal_handlers()
        while not self.stopping:
            self._run_scan(options["project"])
            if options["once"]:
                return
            time.sleep(max(10, options["poll_interval"]))

    def _run_scan(self, project):
        try:
            result = scan_enabled_profiles(project)
            self.stdout.write(
                "CompDoc notifications: "
                f"processed={result['processed']} sent={result['sent']} failed={result['failed']}"
            )
        except Exception:
            LOGGER.exception("CompDoc notification scan failed.")
            self.stderr.write("CompDoc notification scan failed; the worker will retry.")

    def _install_signal_handlers(self):
        def stop_worker(*_args):
            self.stopping = True

        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)
