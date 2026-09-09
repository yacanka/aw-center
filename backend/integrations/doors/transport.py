"""Bounded Windows OLE transport for DOORS."""

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from functools import cached_property
from uuid import uuid4

from .config import RESULT_MODE_APPLICATION, DoorsClientConfig
from .exceptions import DoorsConnectionError, DoorsDxlError
from .escape import dxl_quote
from .startup import registered_executable

CONNECTION_LOCK = threading.Lock()
APPLICATION_RESULT_PREFIX = "AW_DOORS_RESULT|"
FILE_RESULT_PREFIXES = ("AW_DOORS_OK|", "AW_DOORS_ERR|")


@dataclass(frozen=True, slots=True)
class DxlExecution:
    """Represent the line-oriented result of one DXL run."""

    status: str
    lines: tuple[str, ...]


class DoorsOleTransport:
    """Execute DXL through an active IBM Rational DOORS OLE client."""

    def __init__(self, config: DoorsClientConfig) -> None:
        self.config = config
        self.application = None

    @cached_property
    def executable(self) -> Path:
        """Allow ProgID-only configuration while retaining explicit path overrides."""
        return self.config.executable if self.config.executable_path else registered_executable(
            self.config.ole_program_id
        )

    def connect(self) -> "DoorsOleTransport":
        """Connect to an active client or explicitly start one."""
        automation = self.load_automation()
        with CONNECTION_LOCK:
            # ROT lookup alone does not detect several desktop clients. Check
            # this session before accepting a proxy or launching another client.
            self.is_client_running()
            if self.config.prefer_active_instance:
                self.application = self.get_active_application(automation)
            if self.application is None:
                self.connect_or_start(automation)
            elif not self.application_ready(self.application):
                self.application = self.wait_for_application(automation)
        if self.application is None:
            raise DoorsConnectionError("An authenticated DOORS desktop client is required.")
        return self

    def connect_or_start(self, automation) -> None:
        """Connect to a running process or start one only when none exists."""
        if self.is_client_running():
            self.application = self.wait_for_application(automation)
            return
        if self.config.auto_start_client:
            self.start_client(automation)

    @staticmethod
    def load_automation():
        """Load the Windows-only COM automation dependency."""
        try:
            import win32com.client
        except ImportError as error:
            raise DoorsConnectionError("pywin32 is required for DOORS OLE automation.") from error
        return win32com.client

    def get_active_application(self, automation):
        """Return an active DOORS application when one exists."""
        try:
            return automation.GetActiveObject(self.config.ole_program_id)
        except Exception:
            return self.dispatch_running_application(automation)

    def dispatch_running_application(self, automation):
        """Bind through Dispatch only when the DOORS process already exists."""
        if not self.is_client_running():
            return None
        try:
            return automation.Dispatch(self.config.ole_program_id)
        except Exception:
            return None

    def is_client_running(self) -> bool:
        """Return whether the configured DOORS executable is running."""
        process_name = self.executable.name.casefold()
        try:
            inspector = self.load_process_inspector()()
            session_id = inspector.Win32_Process(ProcessId=os.getpid())[0].SessionId
            processes = inspector.Win32_Process(SessionId=session_id)
            matches = [process for process in processes if str(process.Name).casefold() == process_name]
            if len(matches) > 1:
                raise DoorsConnectionError(
                    "Multiple DOORS clients are open in this Windows session. Keep one client open.",
                    "DOORS_MULTIPLE_CLIENTS",
                )
            return bool(matches)
        except DoorsConnectionError:
            raise
        except Exception:
            raise DoorsConnectionError("Unable to inspect running DOORS processes.") from None

    @staticmethod
    def load_process_inspector():
        """Load the Windows process inspector used to prevent duplicate clients."""
        try:
            from wmi import WMI
        except ImportError as error:
            raise DoorsConnectionError("WMI is required for DOORS process inspection.") from error
        return WMI

    def start_client(self, automation) -> None:
        """Start the configured executable without shell interpolation."""
        if not self.executable.is_file():
            raise DoorsConnectionError(
                "The configured DOORS executable does not exist.", "DOORS_EXECUTABLE_UNAVAILABLE"
            )
        try:
            # IBM's GUI startup switches perform login. Never log this argv or its
            # exception: it may contain a password. Do not use batch/automation mode.
            subprocess.Popen(
                self.start_command(), close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError:
            raise DoorsConnectionError("The DOORS desktop client could not be started.") from None
        self.application = self.wait_for_application(automation)

    def start_command(self) -> list[str]:
        """Return shell-free DOORS startup arguments."""
        command = [str(self.executable)]
        if self.config.database:
            command.extend(["-d", self.config.database])
        if self.config.username:
            command.extend(["-user", self.config.username, "-password", self.config.password])
        return command

    def wait_for_application(self, automation):
        """Wait a bounded time for the DOORS OLE object."""
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            application = self.get_active_application(automation)
            if application is not None and self.application_ready(application):
                return application
            time.sleep(0.5)
        raise DoorsConnectionError(
            "DOORS did not become ready before timeout. Check login, database, license and desktop dialogs.",
            "DOORS_STARTUP_TIMEOUT",
        )

    @staticmethod
    def application_ready(application) -> bool:
        """Probe authenticated DXL execution before sending any business operation."""
        marker = "AW_DOORS_READY|" + uuid4().hex
        try:
            application.Result = ""
            application.runStr(f"oleSetResult({dxl_quote(marker)})")
            return str(application.Result) == marker
        except Exception:
            return False

    def run_dxl(
        self, dxl: str, result_file: Path | None, result_mode: str, result_token: str = ""
    ) -> DxlExecution:
        """Run generated DXL and read its configured result transport."""
        if self.application is None:
            self.connect()
        deadline = time.monotonic() + self.config.run_timeout_seconds
        correlation = str(result_file) if result_file else result_token or RESULT_MODE_APPLICATION
        self.invoke(dxl, correlation)
        if result_mode == RESULT_MODE_APPLICATION:
            return self.read_application_execution(deadline, result_token)
        return self.read_file_execution(result_file, deadline)

    def read_file_execution(self, result_file: Path | None, deadline=None) -> DxlExecution:
        """Wait for and read one bounded file-backed result."""
        if result_file is None:
            raise DoorsDxlError("A result file is required for file result mode.")
        expected = f"AW_DOORS_OK|{result_file}"
        status = self.wait_for_result(result_file, FILE_RESULT_PREFIXES, deadline)
        if status != expected:
            raise DoorsDxlError("DXL did not confirm completion of its result file.")
        if not result_file.is_file():
            raise DoorsDxlError("DXL did not produce a result before timeout.")
        return DxlExecution(status, self.read_result_lines(result_file))

    def read_application_execution(self, deadline=None, result_token="") -> DxlExecution:
        """Read a DXL payload returned through DOORS Application.Result."""
        prefix = APPLICATION_RESULT_PREFIX + (result_token + "|" if result_token else "")
        status = self.wait_for_result(None, (prefix,), deadline)
        if not status.startswith(prefix):
            raise DoorsDxlError("DXL did not set Application.Result before timeout.")
        payload = status.removeprefix(prefix)
        return DxlExecution(status, self.decode_result_lines(payload.encode("utf-8")))

    def read_result_lines(self, result_file: Path) -> tuple[str, ...]:
        """Read a DXL result without exceeding its byte limit."""
        with result_file.open("rb") as result_stream:
            content = result_stream.read(self.config.max_result_bytes + 1)
        return self.decode_result_lines(content)

    def decode_result_lines(self, content: bytes) -> tuple[str, ...]:
        """Decode a line result after enforcing the shared byte limit."""
        if len(content) > self.config.max_result_bytes:
            raise DoorsDxlError("DXL result exceeded the configured size limit.")
        try:
            # Only LF delimits rows; splitlines also splits legitimate Unicode
            # separators inside attribute values, silently corrupting exports.
            return tuple(
                line.removesuffix("\r")
                for line in content.decode("utf-8-sig").rstrip("\r\n").split("\n")
            ) if content else ()
        except UnicodeError:
            raise DoorsDxlError("DXL returned an invalid UTF-8 result.") from None

    def invoke(self, dxl: str, correlation: str) -> None:
        """Invoke OLE runStr with a non-secret correlation token."""
        try:
            self.application.Result = f"AW_DOORS_RUNNING|{correlation}"
            self.application.runStr(dxl)
        except Exception as error:
            raise DoorsDxlError("DOORS OLE runStr failed.") from error

    def wait_for_result(self, result_file: Path | None, prefixes: tuple[str, ...], deadline=None) -> str:
        """Wait for the footer, never for a file opened before execution began."""
        if deadline is None:
            deadline = time.monotonic() + self.config.run_timeout_seconds
        while time.monotonic() < deadline:
            status = self.read_status()
            if result_file is not None and status == f"AW_DOORS_ERR|{result_file}":
                raise DoorsDxlError("DXL could not open its result file.")
            if status.startswith(prefixes) and (
                result_file is None or status == f"AW_DOORS_OK|{result_file}"
            ):
                return status
            time.sleep(0.1)
        return ""

    def read_status(self) -> str:
        """Read the current OLE result status safely."""
        try:
            return str(self.application.Result)
        except Exception:
            return ""
