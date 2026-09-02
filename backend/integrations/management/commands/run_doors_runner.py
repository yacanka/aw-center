"""Run the host-local Windows DOORS executor."""

import sys
from threading import Event

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from integrations.doors.runner import (
    DoorsRunner,
    DoorsRunnerClient,
    RunnerAuthenticationError,
    RunnerConfig,
    RunnerConfigurationError,
    RunnerProtocolError,
    bounded_float,
    configured_runner_token,
)


class Command(BaseCommand):
    """Poll the loopback data plane and execute DOORS work in Windows children."""

    help = "Run the native, host-local DOORS automation runner."
    # Server deployment checks validate the container-side token. The native
    # runner may intentionally source its copy from Windows Credential Manager.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--base-url", default=settings.DOORS_RUNNER_URL)

    def handle(self, *args, **options):
        if sys.platform != "win32":
            raise CommandError("The DOORS runner can run only on Windows.")
        try:
            config = RunnerConfig(
                base_url=options["base_url"],
                token=configured_runner_token(),
                connect_timeout_seconds=settings.DOORS_RUNNER_CONNECT_TIMEOUT_SECONDS,
                read_timeout_seconds=settings.DOORS_RUNNER_READ_TIMEOUT_SECONDS,
            )
        except RunnerConfigurationError as error:
            raise CommandError(str(error)) from error

        client = DoorsRunnerClient(config)
        runner = DoorsRunner(client)
        try:
            status = client.status()
            poll_interval = bounded_float(status.get("poll_interval_seconds"), 1.0, 30.0)
            if (
                status.get("enabled") is not True
                or status.get("queue") != "doors"
                or status.get("transport") != "loopback_token"
            ):
                raise RunnerProtocolError("The DOORS runner status contract is invalid.")
        except RunnerAuthenticationError as error:
            raise CommandError("The DOORS runner credential was rejected.") from error
        except (requests.RequestException, RunnerProtocolError) as error:
            raise CommandError("The local DOORS runner endpoint is unavailable.") from error

        self.stdout.write("DOORS runner started on the host-local data plane.")
        stopping = Event()
        while not stopping.is_set():
            try:
                processed = runner.poll_once()
            except RunnerAuthenticationError as error:
                raise CommandError("The DOORS runner credential was rejected.") from error
            except KeyboardInterrupt:
                stopping.set()
                continue
            except (requests.RequestException, RunnerProtocolError):
                if options["once"]:
                    raise CommandError("The DOORS runner request failed.")
                stopping.wait(min(30.0, poll_interval * 2))
                continue
            if options["once"]:
                break
            if not processed:
                stopping.wait(poll_interval)
