from __future__ import annotations

import ctypes
import json
import os
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

from showcase.experiment_execution_state import save_execution_status


@unittest.skipUnless(os.name == "nt", "requires Windows file-sharing semantics")
class ExperimentRunnerStatusReplaceTest(unittest.TestCase):
    def test_transient_read_lock_allows_status_to_be_replaced(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            status_path = directory / "status.json"
            status_path.write_text('{"phase":"registered"}', encoding="utf-8")
            # Omitting FILE_SHARE_DELETE makes the open handle block atomic replacement.
            handle = create_file(
                str(status_path),
                0x80000000,
                0x00000001 | 0x00000002,
                None,
                3,
                0x00000080,
                None,
            )
            self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
            original_replace = os.replace
            replace_errors = []
            handle_open = True

            def release_after_locked_replace(source, destination):
                nonlocal handle_open
                try:
                    return original_replace(source, destination)
                except PermissionError as error:
                    replace_errors.append(error.winerror)
                    if handle_open:
                        self.assertTrue(close_handle(handle))
                        handle_open = False
                    raise

            try:
                with patch(
                    "showcase.experiment_runner.os.replace",
                    side_effect=release_after_locked_replace,
                ):
                    save_execution_status(
                        directory,
                        {"run_id": "run-01", "phase": "completed", "completed": 1},
                    )
            finally:
                if handle_open:
                    close_handle(handle)

            self.assertEqual([5], replace_errors)
            self.assertEqual("completed", json.loads(status_path.read_text())["phase"])

    def test_permanent_replace_failure_preserves_existing_status(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            status_path = directory / "status.json"
            previous_status = b'{"phase":"running"}'
            status_path.write_bytes(previous_status)
            error = PermissionError(5, "access denied")
            error.winerror = 5

            with patch("showcase.experiment_runner.os.replace", side_effect=error):
                with self.assertRaises(PermissionError):
                    save_execution_status(
                        directory,
                        {"run_id": "run-01", "phase": "completed", "completed": 1},
                    )

            self.assertEqual(previous_status, status_path.read_bytes())
            self.assertEqual([], list(directory.glob(".status-*")))
