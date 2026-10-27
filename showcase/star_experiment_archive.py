"""Append-only experiment evidence and exact source identity, without prompts."""

import hashlib
import json
import subprocess
from pathlib import Path

from .star_experiment_registration import digest


def source_identity():
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    # Include uncommitted and new implementation files, never read tests/test.md or runtime data.
    names = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "--",
        "showcase", "tests", "scripts/run_star_readiness_97.py", "llm_client.py",
        "scripts/check_showcase_release.py", "scripts/run_unittest_report.py",
        "llm_response.py", "pyproject.toml", "uv.lock"],
        cwd=root).decode("utf-8").splitlines()
    files = sorted({
        name for name in names
        if name != "tests/test.md"
        and (name.endswith(".py") or name in {"pyproject.toml", "uv.lock"})
    })
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    return dict(revision=revision, source_sha256=digest(hashes))


class ExperimentArchive:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=False)  # An interrupted round is never restarted.
        self.hashes = {}

    def put(self, name, value):
        data = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
        with (self.path / name).open("xb") as stream:
            stream.write(data)
        self.hashes[name] = hashlib.sha256(data).hexdigest()
        return self.hashes[name]

    def finish(self, result):
        self.put("result.json", result)
        self.put("hashes.json", dict(self.hashes))
        return result
