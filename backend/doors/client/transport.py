import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .config import RESULT_MODE_APPLICATION, DoorsClientConfig
from .exceptions import DoorsConnectionError, DoorsDxlError

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

    def connect(self) -> "DoorsOleTransport":
        """Connect to an active client or explicitly start one."""
        automation = self.load_automation()
        with CONNECTION_LOCK:
            if self.config.prefer_active_instance:
                self.application = self.get_active_application(automation)
            if self.application is None:
                self.connect_or_start(automation)
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
        process_name = self.config.executable.name.casefold()
        try:
            processes = self.load_process_inspector()().Win32_Process()
            return any(str(process.Name).casefold() == process_name for process in processes)
        except Exception as error:
            raise DoorsConnectionError("Unable to inspect running DOORS processes.") from error

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
        if not self.config.executable.is_file():
            raise DoorsConnectionError("The configured DOORS executable does not exist.")
        subprocess.Popen(self.start_command(), close_fds=True)
        self.application = self.wait_for_application(automation)

    def start_command(self) -> list[str]:
        """Return shell-free DOORS startup arguments."""
        command = [str(self.config.executable)]
        if self.config.database:
            command.extend(["-d", self.config.database])
        return command

    def wait_for_application(self, automation):
        """Wait a bounded time for the DOORS OLE object."""
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            application = self.get_active_application(automation)
            if application is not None:
                return application
            time.sleep(0.5)
        raise DoorsConnectionError("DOORS did not expose its OLE object before timeout.")

    def run_dxl(
        self, dxl: str, result_file: Path | None, result_mode: str
    ) -> DxlExecution:
        """Run generated DXL and read its configured result transport."""
        if self.application is None:
            self.connect()
        correlation = str(result_file) if result_file else RESULT_MODE_APPLICATION
        self.invoke(dxl, correlation)
        if result_mode == RESULT_MODE_APPLICATION:
            return self.read_application_execution()
        return self.read_file_execution(result_file)

    def read_file_execution(self, result_file: Path | None) -> DxlExecution:
        """Wait for and read one bounded file-backed result."""
        if result_file is None:
            raise DoorsDxlError("A result file is required for file result mode.")
        status = self.wait_for_result(result_file, FILE_RESULT_PREFIXES)
        if not result_file.is_file():
            raise DoorsDxlError("DXL did not produce a result before timeout.")
        return DxlExecution(status, self.read_result_lines(result_file))

    def read_application_execution(self) -> DxlExecution:
        """Read a DXL payload returned through DOORS Application.Result."""
        status = self.wait_for_result(None, (APPLICATION_RESULT_PREFIX,))
        if not status.startswith(APPLICATION_RESULT_PREFIX):
            raise DoorsDxlError("DXL did not set Application.Result before timeout.")
        payload = status.removeprefix(APPLICATION_RESULT_PREFIX)
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
        return tuple(content.decode("utf-8", errors="replace").splitlines())

    def invoke(self, dxl: str, correlation: str) -> None:
        """Invoke OLE runStr with a non-secret correlation token."""
        try:
            self.application.Result = f"AW_DOORS_RUNNING|{correlation}"
            self.application.runStr(dxl)
        except Exception as error:
            raise DoorsDxlError("DOORS OLE runStr failed.") from error

    def wait_for_result(self, result_file: Path | None, prefixes: tuple[str, ...]) -> str:
        """Wait until DOORS reports completion or creates a result file."""
        deadline = time.monotonic() + self.config.run_timeout_seconds
        while time.monotonic() < deadline:
            status = self.read_status()
            if status.startswith(prefixes):
                return status
            if result_file is not None and result_file.is_file():
                time.sleep(0.1)
                return self.read_status()
            time.sleep(0.1)
        return ""

    def read_status(self) -> str:
        """Read the current OLE result status safely."""
        try:
            return str(self.application.Result)
        except Exception:
            return ""
