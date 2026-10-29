"""Owner-only visible-reply vault, separate from downloadable tool artifacts."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


class RestrictedReplies:
    """Persist UTF-8 bytes with Run/call/problem binding; never publish file paths."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self._secured = False

    def _secure(self):
        if self.directory.is_symlink():
            raise ValueError("restricted_directory_symlink")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "nt":
            # Replace the DACL (including explicit inherited grants), then verify it.
            script = """
$ErrorActionPreference = 'Stop'
$path = $env:MATHAGENT_PRIVATE_REPLY_DIR
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($id in @($sid, [System.Security.Principal.SecurityIdentifier]'S-1-5-18')) {
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($id, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
  $acl.AddAccessRule($rule)
}
[System.IO.Directory]::SetAccessControl($path, $acl)
$actual = [System.IO.Directory]::GetAccessControl($path)
if (-not $actual.AreAccessRulesProtected) { throw 'unprotected' }
foreach ($entry in $actual.Access) {
  $entrySid = $entry.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
  if ($entrySid -notin @($sid.Value, 'S-1-5-18') -or $entry.AccessControlType -ne 'Allow') { throw 'unexpected_acl' }
}
"""
            try:
                subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                               env={**os.environ, "MATHAGENT_PRIVATE_REPLY_DIR": str(self.directory.resolve())},
                               capture_output=True, check=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except subprocess.SubprocessError:
                raise OSError("restricted_directory_acl_failed") from None
        else:
            self.directory.chmod(0o700)
            if self.directory.stat().st_mode & 0o077:
                raise ValueError("restricted_directory_permissions")
        self._secured = True

    def put(self, request, text):
        """Write bytes once under an opaque binding digest; storage errors fail closed."""
        if not self._secured:
            self._secure()
        payload = text.encode("utf-8")
        ref = {key: request[key] for key in ("run_id", "call_id", "problem_hash", "role")}
        ref["sha256"] = hashlib.sha256(payload).hexdigest()
        path = self._path(ref)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            self.read(ref, request)
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        return ref

    def _path(self, ref):
        identity = json.dumps(ref, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return self.directory / (hashlib.sha256(identity).hexdigest() + ".reply")

    def read(self, ref, request):
        """Require same task/role and original call identity as well as byte integrity."""
        if set(ref) != {"run_id", "call_id", "problem_hash", "role", "sha256"}:
            raise ValueError("invalid_reply_reference")
        if any(ref[key] != request[key] for key in ("run_id", "problem_hash", "role")):
            raise ValueError("reply_identity_mismatch")
        if request["call_id"] not in {ref["call_id"], ref["call_id"] + ":serialization-1"}:
            raise ValueError("reply_call_mismatch")
        if not self._secured:
            self._secure()
        path = self._path(ref)
        if path.is_symlink():
            raise ValueError("reply_symlink")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != ref["sha256"]:
            raise ValueError("reply_integrity_mismatch")
        return payload.decode("utf-8")
