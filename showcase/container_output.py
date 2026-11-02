"""Drain hostile Docker output under one byte cap before decoding or storing."""

import subprocess
import threading
import time


def supervise(process, *, limit, timeout, kill, canceled=lambda: False):
    lock = threading.Lock()
    exceeded = threading.Event()
    retained = {"stdout": bytearray(), "stderr": bytearray()}
    observed = [0]

    def drain(name, pipe):
        try:
            while chunk := pipe.read1(4096):
                with lock:
                    remaining = max(0, limit - sum(map(len, retained.values())))
                    retained[name].extend(chunk[:remaining])
                    observed[0] += len(chunk)
                    if len(chunk) > remaining:
                        exceeded.set()
        finally:
            pipe.close()

    readers = [threading.Thread(target=drain, args=(name, getattr(process, name)), daemon=True)
               for name in retained]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    reason = None
    while process.poll() is None or any(reader.is_alive() for reader in readers):
        if exceeded.is_set():
            reason = "output_limit"
        elif canceled():
            reason = "canceled"
        elif time.monotonic() >= deadline:
            reason = "timeout"
        if reason:
            kill()
            break
        time.sleep(.01)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    for reader in readers:
        reader.join(timeout=5)
    with lock:
        return {"stdout": bytes(retained["stdout"]), "stderr": bytes(retained["stderr"]),
                "observed_output_bytes": observed[0], "reason": reason or ("output_limit" if exceeded.is_set() else None)}
