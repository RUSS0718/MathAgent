"""Execute bounded Docker isolation counterexamples; never run generated code on host."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path


def docker(*args, timeout=20):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )


def probe(image, name, code, *, restricted=True, timeout=8):
    container = "star-sp01-" + uuid.uuid4().hex[:12]
    args = ["run", "--name", container, "--log-driver", "none"]
    if restricted:
        args += [
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "--memory", "64m", "--memory-swap", "64m", "--cpus", "0.5",
            "--pids-limit", "16", "--ulimit", "cpu=1:2", "--ulimit", "fsize=8192:8192",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=1m,mode=1777",
        ]
    # Both streams are regular files: RLIMIT_FSIZE applies while the child writes,
    # unlike capturing an unbounded Docker stdout pipe and truncating afterward.
    args += [image, "sh", "-c",
             'python -u -c "$1" > /tmp/stdout 2> /tmp/stderr; rc=$?; '
             'wc -c /tmp/stdout /tmp/stderr; cat /tmp/stdout /tmp/stderr; exit "$rc"',
             "spike", code]
    started = time.monotonic()
    process = subprocess.Popen(["docker", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timed_out = False
    try:
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            docker("kill", container)
            out, err = process.communicate(timeout=10)
        inspection = json.loads(docker("inspect", container).stdout)[0]
        top = docker("top", container)
        return {
            "name": name, "restricted": restricted, "timeout": timed_out,
            "exit_code": process.returncode, "seconds": round(time.monotonic() - started, 3),
            "stdout": out.decode(errors="replace"), "stderr": err.decode(errors="replace"),
            "state": inspection["State"], "host_config": inspection["HostConfig"],
            "process_tree_gone": not inspection["State"]["Running"] and top.returncode != 0,
        }
    finally:
        if process.poll() is None:
            docker("kill", container)
            process.communicate(timeout=10)
        docker("rm", "-f", container)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="python:3.11-slim")
    args = parser.parse_args()
    image = json.loads(docker("image", "inspect", args.image).stdout)[0]
    identity = image["Id"]
    cases = [
        ("network", "import socket; socket.create_connection(('1.1.1.1',443),timeout=1)"),
        ("root_file", "open('/sp01-host-canary','w').write('forbidden')"),
        ("host_file", "open('/host/sp01-canary').read()"),
        ("cross_task_file", "open('/other-task/sp01-canary').read()"),
        ("memory", "x=bytearray(256*1024*1024)"),
        ("process_count", "import subprocess; p=[subprocess.Popen(['sleep','30']) for _ in range(40)]"),
        ("cpu", "while True: pass"),
        ("stdout", "import os;\nwhile True: os.write(1,b'x'*1024)"),
        ("stderr", "import os;\nwhile True: os.write(2,b'x'*1024)"),
        ("tree_timeout", "import subprocess,time; subprocess.Popen(['sleep','30']); time.sleep(30)"),
        ("parent_stdout_bypass", "import os; paths=['/proc/1/fd/'+x for x in os.listdir('/proc/1/fd')]; "
         "target=next(p for p in paths if p.endswith('/10') and os.readlink(p).startswith('pipe:')); "
         "fd=os.open(target,os.O_WRONLY); os.write(fd,b'B'*16384)"),
    ]
    results = [probe(identity, name, code) for name, code in cases]
    # Bypass counterexample: writing the same path without --read-only succeeds.
    # No host bind, credentials, or external networking are added to this container.
    control = probe(identity, "root_file_without_guard", cases[1][1], restricted=False)
    assertions = {
        "network_denied": results[0]["exit_code"] != 0 and not results[0]["timeout"],
        "root_read_only": "Read-only file system" in results[1]["stdout"],
        "host_absent": "No such file" in results[2]["stdout"],
        "cross_task_absent": "No such file" in results[3]["stdout"],
        "memory_bounded": results[4]["state"]["OOMKilled"],
        "processes_bounded": "Resource temporarily unavailable" in results[5]["stdout"],
        "cpu_bounded": results[6]["exit_code"] != 0 and not results[6]["timeout"],
        "stdout_bounded_during_execution": "8192 /tmp/stdout" in results[7]["stdout"] and not results[7]["timeout"],
        "stderr_bounded_during_execution": "8192 /tmp/stderr" in results[8]["stdout"] and not results[8]["timeout"],
        "timeout_kills_tree": results[9]["timeout"] and results[9]["process_tree_gone"],
        "arbitrary_stdout_bounded": results[10]["stdout"].count("B") <= 8192,
        "bypass_detected": control["exit_code"] == 0 and results[1]["exit_code"] != 0,
        "all_process_trees_gone": all(r["process_tree_gone"] for r in results),
    }
    report = {
        "mode": "fault-injection", "model_calls": 0, "image_id": identity,
        "repo_digests": image.get("RepoDigests"), "engine": docker("version", "--format", "{{json .Server}}").stdout.strip(),
        "production_output_gate": "blocked: regular-file limits can be bypassed through parent stdout fd",
        "budget": {"containers": 12, "per_container_seconds": 8, "memory_bytes": 67108864,
                   "output_bytes_per_stream": 8192, "external_api_calls": 0},
        "assertions": assertions, "results": results, "bypass_control": control,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"assertions": assertions, "output": str(args.output)}, ensure_ascii=False))
    return 0 if all(assertions.values()) else 1


if __name__ == "__main__":
    raise SystemExit(run())
