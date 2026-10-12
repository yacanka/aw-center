"""OS-owned descendant containment for disposable executor processes."""

import os
import signal
import sys
from time import monotonic, sleep


def establish_executor_session():
    """Put POSIX executor descendants in a group separate from the worker."""

    if sys.platform != "win32":
        os.setsid()


class ExecutorProcessTree:
    """Own one POSIX process group or non-inheritable Windows Job Object."""

    def __init__(self, process):
        self.pid = process.pid
        self.stopped = False
        self.windows_job = None
        if sys.platform == "win32":
            self.windows_job = _WindowsJob(process.sentinel)

    def terminate(self):
        if self.stopped:
            return True
        if self.windows_job is not None:
            self.windows_job.terminate()
            self.stopped = True
            return True
        return self._signal_group(signal.SIGTERM)

    def kill(self):
        if self.stopped:
            return
        if self.windows_job is not None:
            self.windows_job.terminate()
        else:
            self._signal_group(signal.SIGKILL)
        self.stopped = True

    def close(self):
        if self.windows_job is not None:
            self.windows_job.close()
        else:
            self.kill()

    def wait_for_exit(self, timeout=5):
        """Bound publication waiting until the owned tree has no processes."""

        deadline = monotonic() + timeout
        while self._has_processes():
            if monotonic() >= deadline:
                return False
            sleep(0.01)
        return True

    def _has_processes(self):
        if self.windows_job is not None:
            return self.windows_job.has_processes()
        try:
            os.killpg(self.pid, 0)
        except ProcessLookupError:
            return False
        return True

    def _signal_group(self, value):
        try:
            os.killpg(self.pid, value)
        except ProcessLookupError:
            # Bootstrap may not have established its group yet, or it is empty.
            return False
        return True


class _WindowsJob:
    """Keep the only Job handle in the parent; closing it kills descendants."""

    def __init__(self, process_handle):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_functions(wintypes)
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = _windows_limits(ctypes, wintypes)
            if not self.kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.AssignProcessToJobObject(self.handle, process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def terminate(self):
        if self.handle and not self.kernel.TerminateJobObject(self.handle, 1):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):
                raise self.ctypes.WinError(self.ctypes.get_last_error())

    def has_processes(self):
        from ctypes import wintypes

        class Accounting(self.ctypes.Structure):
            _fields_ = [
                (name, self.ctypes.c_int64) for name in (
                    "TotalUserTime", "TotalKernelTime",
                    "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime",
                )
            ] + [(name, wintypes.DWORD) for name in (
                "TotalPageFaultCount", "TotalProcesses", "ActiveProcesses",
                "TotalTerminatedProcesses",
            )]

        info = Accounting()
        if not self.kernel.QueryInformationJobObject(
            self.handle, 1, self.ctypes.byref(info), self.ctypes.sizeof(info), None
        ):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return info.ActiveProcesses != 0

    def _configure_functions(self, types):
        self.kernel.CreateJobObjectW.argtypes = [types.LPVOID, types.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = types.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            types.HANDLE, types.INT, types.LPVOID, types.DWORD,
        ]
        self.kernel.SetInformationJobObject.restype = types.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [types.HANDLE, types.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = types.BOOL
        self.kernel.TerminateJobObject.argtypes = [types.HANDLE, types.UINT]
        self.kernel.TerminateJobObject.restype = types.BOOL
        self.kernel.CloseHandle.argtypes = [types.HANDLE]
        self.kernel.CloseHandle.restype = types.BOOL
        self.kernel.QueryInformationJobObject.argtypes = [
            types.HANDLE, types.INT, types.LPVOID, types.DWORD, types.LPVOID,
        ]
        self.kernel.QueryInformationJobObject.restype = types.BOOL


def _windows_limits(ctypes, types):
    # Native layout from JOBOBJECT_EXTENDED_LIMIT_INFORMATION. SIZE_T and
    # ULONG_PTR follow pointer width; DWORD remains 32-bit on Windows x64.
    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", types.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", types.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", types.DWORD),
            ("SchedulingClass", types.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    return limits
