"""Immutable, prompt-free registration for the socket-free #102 runner."""
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d"
PARAMETERS = dict(model="intern-s2", thinking_mode=True, temperature=0.2,
                  max_tokens=16384, retry=1)
SINGLE = dict(tokens=65536, logical=1, http=1, tools=0)
STOP = ["unknown", "cancel", "restart", "missing_usage", "archive_failure", "deadline"]
PHASES = {
    "P": dict(requests=36, tokens=2359296, wait=32400, batch=36000),
    "O": dict(requests=3, tokens=196608, wait=5400, batch=7200),
    "T": dict(requests=24, tokens=1572864, wait=32400, batch=36000),
    "T-3600": dict(requests=4, tokens=262144, wait=14400, batch=16200),
    "R": dict(requests=16, tokens=1048576, wait=28800, batch=32400),
    "S": dict(requests=8, tokens=524288, wait=14400, batch=16200),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("diagnostic_identity_invalid")
    return value


def source_identity():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()
    names = git("ls-files", "-co", "--exclude-standard", "--", "*.py", "pyproject.toml", "uv.lock")
    files = sorted({n for n in names.splitlines() if n != "tests/test.md"
                    and not any(p in {".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
                                      "artifacts", "build", "dist"} for p in Path(n).parts)})
    hashes = {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in files}
    runner = "scripts/run_star_diagnostic_102.py"
    return dict(sha=git("rev-parse", "HEAD"), dirty=bool(git("status", "--porcelain",
                "--untracked-files=normal", "--", ".", ":(exclude)tests/test.md")),
                files_sha256=digest(hashes), runner_sha256=hashes.get(runner), runner=runner)


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _exact(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError("diagnostic_schema_invalid")


def _request(request, phase):
    _exact(request, "question prompt schema arm question_id timeout_seconds")
    for name in ("question", "prompt"):
        if not isinstance(request[name], str) or not request[name].strip():
            raise ValueError("diagnostic_input_missing")
    if not isinstance(request["schema"], dict) or not request["schema"]:
        raise ValueError("diagnostic_schema_missing")
    identifier(request["arm"])
    identifier(request["question_id"])
    wait = request["timeout_seconds"]
    allowed = {"P": {900}, "O": {1800}, "T": {900, 1800}, "T-3600": {3600}, "S": {1800}}
    if type(wait) is not int or (wait not in allowed.get(phase, range(1, 1801))):
        raise ValueError("diagnostic_wait_invalid")
    # Include the full wire-envelope estimate; never shorten a question/proof.
    size = len(json.dumps(dict(question=request["question"], prompt=request["prompt"],
                              schema=request["schema"], **PARAMETERS),
                          ensure_ascii=False).encode("utf-8"))
    if size + PARAMETERS["max_tokens"] > SINGLE["tokens"]:
        raise ValueError("diagnostic_input_too_long")
    return size


def freeze(plan, directory):
    _exact(plan, "registration_id phase seed window conditions_met requests")
    identifier(plan["registration_id"])
    phase = plan["phase"]
    if phase not in PHASES or type(plan["seed"]) is not int:
        raise ValueError("diagnostic_phase_or_seed_invalid")
    _exact(plan["window"], "start end")
    start, end = plan["window"]["start"], plan["window"]["end"]
    if (any(type(n) not in {float, int} or not math.isfinite(n) for n in (start, end))
            or not 0 < end - start <= PHASES[phase]["batch"]):
        raise ValueError("diagnostic_window_invalid")
    if type(plan["conditions_met"]) is not bool:
        raise ValueError("diagnostic_conditions_invalid")
    if not isinstance(plan["requests"], list) or not 1 <= len(plan["requests"]) <= PHASES[phase]["requests"]:
        raise ValueError("diagnostic_request_limit")
    requests = []
    for request in plan["requests"]:
        size = _request(request, phase)
        uid = uuid4().hex
        requests.append(dict(run_id=uid, session_id=uuid4().hex, workspace_id=uuid4().hex,
                             question_id=request["question_id"], arm=request["arm"],
                             question_sha256=digest(request["question"]),
                             prompt_sha256=digest(request["prompt"]),
                             schema_sha256=digest(request["schema"]), input_estimate=size,
                             timeout_seconds=request["timeout_seconds"],
                             shadow_seconds=900 if request["timeout_seconds"] == 1800 else None))
    if sum(r["timeout_seconds"] for r in requests) > PHASES[phase]["wait"]:
        raise ValueError("diagnostic_wait_limit")
    result = dict(version=1, registration_id=plan["registration_id"], phase=phase,
                  seed=plan["seed"], window=plan["window"], conditions_met=plan["conditions_met"],
                  source=source_identity(), upstream=UPSTREAM, parameters=PARAMETERS,
                  single=SINGLE, budget=PHASES[phase], stop=STOP, requests=requests)
    result["sha256"] = digest(result)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    private = directory / "private"
    private.mkdir()
    write_new(private / "inputs.json", plan["requests"])
    write_new(directory / "manifest.json", result)
    return result


def validate(manifest, *, check_source=False):
    _exact(manifest, "version registration_id phase seed window conditions_met source upstream parameters single budget stop requests sha256")
    if digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"]:
        raise ValueError("diagnostic_manifest_changed")
    if (manifest["version"] != 1 or manifest["upstream"] != UPSTREAM
            or manifest["parameters"] != PARAMETERS or manifest["single"] != SINGLE
            or manifest["stop"] != STOP or manifest["budget"] != PHASES.get(manifest["phase"])):
        raise ValueError("diagnostic_contract_changed")
    identifier(manifest["registration_id"])
    phase = manifest["phase"]
    if type(manifest["seed"]) is not int or type(manifest["conditions_met"]) is not bool:
        raise ValueError("diagnostic_manifest_invalid")
    _exact(manifest["window"], "start end")
    start, end = manifest["window"]["start"], manifest["window"]["end"]
    if (any(type(n) not in {int, float} or not math.isfinite(n) for n in (start, end))
            or not 0 < end - start <= PHASES[phase]["batch"]):
        raise ValueError("diagnostic_window_invalid")
    if not isinstance(manifest["requests"], list) or not 1 <= len(manifest["requests"]) <= PHASES[phase]["requests"]:
        raise ValueError("diagnostic_request_limit")
    _exact(manifest["source"], "sha dirty files_sha256 runner_sha256 runner")
    identities = []
    for request in manifest["requests"]:
        _exact(request, "run_id session_id workspace_id question_id arm question_sha256 prompt_sha256 schema_sha256 input_estimate timeout_seconds shadow_seconds")
        for key in ("run_id", "session_id", "workspace_id"):
            identities.append(identifier(request[key]))
        for key in ("question_id", "arm"):
            identifier(request[key])
        for key in ("question_sha256", "prompt_sha256", "schema_sha256"):
            if not isinstance(request[key], str) or not re.fullmatch("[0-9a-f]{64}", request[key]):
                raise ValueError("diagnostic_hash_invalid")
        size = request["input_estimate"]
        wait = request["timeout_seconds"]
        allowed = {"P": {900}, "O": {1800}, "T": {900, 1800}, "T-3600": {3600}, "S": {1800}}
        if (type(size) is not int or not 0 < size <= 49152 or type(wait) is not int
                or wait not in allowed.get(phase, range(1, 1801))
                or request["shadow_seconds"] != (900 if wait == 1800 else None)):
            raise ValueError("diagnostic_request_limit")
    if sum(r["timeout_seconds"] for r in manifest["requests"]) > PHASES[phase]["wait"]:
        raise ValueError("diagnostic_wait_limit")
    if len(set(identities)) != len(identities):
        raise ValueError("diagnostic_identity_reused")
    if check_source and manifest["source"] != source_identity():
        raise ValueError("diagnostic_source_changed")
    return manifest


def dry_run(manifest):
    validate(manifest)
    return dict(phase=manifest["phase"], phase_limits=PHASES, single=SINGLE,
                planned=len(manifest["requests"]), status="ready" if manifest["conditions_met"] else "not_started",
                charged_reserved_ceiling=len(manifest["requests"]) * 65536,
                request_wait_ceiling=sum(r["timeout_seconds"] for r in manifest["requests"]),
                shadow_is_new_request=False,
                p_inclusion=dict(total_ceiling=36, included_control=3, remaining_ceiling=33,
                                 continuation="same registration and cumulative ledger"),
                sha256=manifest["sha256"])
