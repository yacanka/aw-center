import sys
from collections.abc import Callable
from contextlib import contextmanager
from typing import TypeVar

from django.conf import settings

from integrations.doors import DoorsClient, DoorsClientConfig, DoorsConnectionError

Result = TypeVar("Result")


def build_client_config() -> DoorsClientConfig:
    """Build an IBM Rational DOORS client config from Django settings."""
    return DoorsClientConfig(
        executable_path=settings.DOORS_EXECUTABLE,
        database=settings.DOORS_DATABASE,
        ole_program_id=settings.DOORS_OLE_PROG_ID,
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
        return operation(DoorsClient(build_client_config()))


def integration_status() -> dict[str, object]:
    """Return fail-closed readiness for the host-local runner topology."""

    from automations.runner_protocol import runner_status

    runner = runner_status()
    return {
        "configured": bool(settings.DOORS_ENABLED and runner["configured"]),
        "platform_supported": bool(runner["available"]),
        "available": bool(settings.DOORS_ENABLED and runner["available"]),
        "execution_mode": "loopback_token",
        "runner": runner,
    }
