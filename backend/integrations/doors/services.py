import sys
from collections.abc import Callable
from contextlib import contextmanager
from datetime import timedelta
from typing import TypeVar

from django.conf import settings
from django.utils import timezone

from integrations.doors import DoorsClient, DoorsClientConfig, DoorsConnectionError
from .exceptions import DoorsConfigurationError

Result = TypeVar("Result")


def build_client_config() -> DoorsClientConfig:
    """Reject invalid settings without including credentials in exceptions."""
    try:
        return _client_config()
    except (ValueError, TypeError):
        raise DoorsConfigurationError() from None


def _client_config() -> DoorsClientConfig:
    """Build an IBM Rational DOORS client config from Django settings."""
    return DoorsClientConfig(
        executable_path=settings.DOORS_EXECUTABLE,
        database=settings.DOORS_DATABASE,
        ole_program_id=settings.DOORS_OLE_PROG_ID,
        username=settings.DOORS_USERNAME,
        password=settings.DOORS_PASSWORD,
        prefer_active_instance=settings.DOORS_PREFER_ACTIVE_INSTANCE,
        auto_start_client=settings.DOORS_AUTO_START_CLIENT,
        startup_timeout_seconds=settings.DOORS_STARTUP_TIMEOUT_SECONDS,
        run_timeout_seconds=settings.DOORS_RUN_TIMEOUT_SECONDS,
        max_result_bytes=settings.DOORS_MAX_RESULT_BYTES,
        result_mode=settings.DOORS_RESULT_MODE,
    )


@contextmanager
def initialized_com():
    """Initialize COM for the current Django worker thread."""
    if sys.platform != "win32":
        raise DoorsConnectionError("DOORS OLE automation requires Windows.")
    try:
        import pythoncom
    except ImportError as error:
        raise DoorsConnectionError("pywin32 is required for DOORS OLE automation.") from error
    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def execute_with_client(operation: Callable[[DoorsClient], Result]) -> Result:
    """Execute a DOORS operation within a COM-initialized worker thread."""
    with initialized_com():
        client = DoorsClient(build_client_config())
        try:
            return operation(client)
        finally:
            # Release the apartment-bound proxy before CoUninitialize, without Quit.
            client.transport.application = None


def integration_status() -> dict[str, object]:
    """Return readiness for the single supported Windows worker architecture."""

    from jobs.models import WorkerHeartbeat

    stale_seconds = max(5, int(settings.JOB_WORKER_STALE_SECONDS))
    active_workers = WorkerHeartbeat.objects.filter(
        worker_id__startswith="doors-worker:",
        heartbeat_at__gte=timezone.now() - timedelta(seconds=stale_seconds),
    ).count()
    platform_supported = sys.platform == "win32"
    configured = bool(settings.DOORS_ENABLED and platform_supported)
    if configured:
        try:
            build_client_config()
        except DoorsConfigurationError:
            configured = False
    return {
        "configured": configured,
        "platform_supported": platform_supported,
        "available": bool(configured and active_workers),
        "active_workers": active_workers if configured else 0,
        "transport": "windows-worker",
    }
