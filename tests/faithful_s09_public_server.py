"""Trusted local S09 public-chain fixture with a finite scripted provider.

This is an executable acceptance fixture, not an official entry point. It runs
the real Flask Job/report/Evidence path, the real formal core producer, and an
explicitly selected unavailable or Docker executor. No paid provider is called.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from showcase.adapters import InternModelAdapter  # noqa: E402
from showcase.flask_app import create_app  # noqa: E402
from showcase.formal import LeanTacticProver, ReviewAuthority, normalize_target  # noqa: E402
from showcase.run_budget import RunBudgetLimits  # noqa: E402
from showcase.solver_harness.specification import normalize_problem_spec  # noqa: E402
from showcase.tools import ToolRegistry  # noqa: E402
from tests.star_product_support import ACCEPT, POLISH, SOLVED  # noqa: E402

PROBLEM = "For every rational x, x + x = 2 * x."
SPEC = normalize_problem_spec({
    "specification_version": 1,
    "original_problem": PROBLEM,
    "domain": "rationals",
    "quantifiers": ["forall x"],
    "assumptions": [],
    "directions": ["equality"],
    "output_requirements": [],
    "root_obligations": [{
        "obligation_id": "root:identity",
        "obligation_type": "universal",
        "statement": "x + x = 2 * x",
        "direction": "equality",
    }],
    "auxiliary_goals": [],
})
TARGET = normalize_target({
    "domain": "rationals", "variables": ["x"], "lhs": "x + x", "rhs": "2 * x",
    "quantifiers": ["forall x"], "assumptions": [], "direction": "equality",
})
FORMAL_POLICY = {
    "enabled": True,
    "requested_backend": "lean_tactic_prover",
    "allowed_backends": ["lean_tactic_prover"],
    "require_formal": False,
    "timeout_seconds": 30,
    "max_output_bytes": 16_000,
    "resource_limits": {"memory_mb": 512, "cpu_count": 1},
    "allowed_axioms": ["propext", "Classical.choice", "Quot.sound"],
    "environment": {},
    "target": TARGET,
}


class UnavailableExecutor:
    """Finite fixture because Docker Lean availability is represented honestly."""

    def execute(self, source, *, run_id, call_id, **kwargs):
        return {
            "status": "unavailable", "executed": False, "cleanup_verified": True,
            "environment": {}, "duration_seconds": 0.0,
            "observed_output_bytes": 0, "stdout": "", "stderr": "",
            "reason": "lean_fixture_unavailable",
        }


class ScriptedProvider(BaseHTTPRequestHandler):
    answer = "1+1=2"
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        return

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        context = json.loads(body["messages"][-1]["content"])
        role = context.get("role")
        reply = copy.deepcopy(SOLVED if role == "explore" else POLISH if role == "explore_polish" else ACCEPT)
        if role in {"explore", "explore_polish"}:
            reply["solution_candidate"] = self.answer
        payload = {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}],
            "model": "intern-s2",
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def build_app(*, data_dir: str, executor=None, independent_review=False):
    registry = ToolRegistry()
    registry.register_polynomial_check()
    policy = copy.deepcopy(FORMAL_POLICY)
    authority = None
    if executor is not None:
        policy.update(max_output_bytes=executor.max_output_bytes,
                      timeout_seconds=executor.timeout_seconds,
                      environment={"deployment_manifest_sha256": executor.environment_hash})
    if independent_review:
        from showcase.formal_correspondence import CHECKER_VERSION

        authority = ReviewAuthority({CHECKER_VERSION: secrets.token_hex(32)},
                                    {CHECKER_VERSION: "independent_service"})
    app = create_app({
        "TESTING": True,
        "SHOWCASE_DATA_DIR": data_dir,
        "SHOWCASE_JOB_DELAY_SECONDS": 0.01,
        "SHOWCASE_STAR_ENABLED": True,
        "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
        "SHOWCASE_STAR_FEATURES": {
            "problem_spec": True,
            "final_generation": True,
            "final_solution_review": True,
        },
        "SHOWCASE_STAR_REGISTRY": registry,
        "SHOWCASE_STAR_BUDGET": RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8, max_tool_calls=2,
            max_tokens=100_000, max_runtime_seconds=1_100,
        ),
        "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
            InternChatClient(retry=1), max_tokens=256,
        ),
        "SHOWCASE_FORMAL_VERIFICATION_CONFIG": policy,
        "SHOWCASE_FORMAL_BACKEND": LeanTacticProver(executor or UnavailableExecutor(),
                                                   review_authority=authority),
    })

    @app.get("/__test__/s09/formal-fixture")
    def formal_fixture():
        return app.response_class(
            json.dumps({"problem": PROBLEM, "specification": SPEC,
                        "formalPolicy": policy}, ensure_ascii=False),
            mimetype="application/json",
        )

    return app


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="S09 public HTTP acceptance fixture")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--provider-port", type=int, default=8092)
    parser.add_argument("--data-dir", type=Path, default=Path("artifacts/s09-public"))
    parser.add_argument("--formal-manifest", type=Path)
    parser.add_argument("--independent-review", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.formal_manifest:
        ScriptedProvider.answer = "x + x = 2 * x"
    args.data_dir.mkdir(parents=True, exist_ok=True)
    provider = ThreadingHTTPServer((args.host, args.provider_port), ScriptedProvider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    os.environ["INTERN_API_KEY"] = "local-s09-fixture"
    os.environ["INTERN_API_BASE"] = (
        f"http://{args.host}:{args.provider_port}/v1/chat/completions"
    )
    executor = None
    if args.formal_manifest:
        from showcase.formal_docker import LeanDockerExecutor

        manifest = json.loads(args.formal_manifest.read_text(encoding="utf-8"))
        executor = LeanDockerExecutor(manifest=manifest, max_output_bytes=262144)
    app = build_app(data_dir=str(args.data_dir), executor=executor,
                    independent_review=args.independent_review)
    print(json.dumps({
        "status": "ready", "base_url": f"http://{args.host}:{args.port}",
        "health": f"http://{args.host}:{args.port}/health",
        "provider_port": args.provider_port,
    }), flush=True)
    try:
        app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    finally:
        provider.shutdown()
        provider.server_close()


if __name__ == "__main__":
    main()
