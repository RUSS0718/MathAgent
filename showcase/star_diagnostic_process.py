"""OS process identity for honest local monitoring; never infer remote status."""
import os
import subprocess


def process_identity(pid=None):
    pid = os.getpid() if pid is None else pid
    if type(pid) is not int or pid <= 0:
        raise ValueError("diagnostic_process_invalid")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            code = ctypes.get_last_error()
            if code == 87:
                raise ProcessLookupError("diagnostic_process_exited")
            raise OSError("diagnostic_process_unavailable")
        try:
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                            ctypes.byref(kernel), ctypes.byref(user)):
                raise OSError("diagnostic_process_unavailable")
            creation = ((created.dwHighDateTime << 32) + created.dwLowDateTime) / 1e7 - 11644473600
        finally:
            kernel32.CloseHandle(handle)
    else:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True)
        if result.returncode or not result.stdout.strip():
            raise ProcessLookupError("diagnostic_process_exited")
        creation = result.stdout.strip()
    return dict(pid=pid, process_created_at=creation)


def observe_process(record):
    try:
        observed = process_identity(record["pid"])
        return "running" if observed == record else "reused"
    except ProcessLookupError:
        return "exited"
    except (OSError, ValueError, KeyError, TypeError):
        return "unavailable"
