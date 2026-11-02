"""Real loopback provider and Docker; no solver, ledger or Job outcomes mocked."""

import json
import os
import sqlite3
import threading
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter, InternStreamAdapter
from showcase.star_experiment_registration import digest
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

ANSWERS = {
    "short_a": "Adding two pairs gives 4. Final answer: 4",
    "short_b": "Common denominators give three quarters. Final answer: 3/4",
    "finite": "The three listed objects exhaust the domain. Final answer: 3",
    "bound": "A square is nonnegative, with equality at zero.",
    "sum": "Separate the two terms and add. Final answer: 5",
}
ENUMERATION = "print(3)\n"


def synthetic_registration():
    from showcase.star_experiment_registration import CONDITIONS, E1, E2, ROUND, VERSION
    questions = {}
    for key, text in {"short_a": "Add two and two; explain.",
                      "short_b": "Add one half and one quarter; explain.",
                      "finite": "Count the objects A, B, C exhaustively.",
                      "bound": "Prove a real square is nonnegative, including equality.",
                      "sum": "Add two and three with justification."}.items():
        questions[key] = dict(source="synthetic-test", original=text, prompt=text,
            obligations=["result", "explanation"], original_sha256=digest(text), prompt_sha256=digest(text))
    order = [("E1", q, t) for q in ("short_a", "short_b") for t in ("nonstream", "stream")]
    order += [("E2", q, "nonstream") for _ in range(2) for q in ("finite", "bound", "sum")]
    return dict(version=VERSION, questions=questions, conditions=dict(CONDITIONS), round_limits=dict(ROUND),
        source_checked="synthetic", review_rules={"review": "independent-oracle-secret: independent obligation review required."},
        independent_oracles=dict(short_a="4", short_b="3/4", finite="3", bound=None, sum="5"),
        schedule=[dict(index=i, stage=s, question=q, transport=t, limits=dict(E1 if s=="E1" else E2))
                  for i,(s,q,t) in enumerate(order)])


def independent_review(key, question, bundle):
    return dict(reviewer="deterministic-test-reviewer", reason="Controlled fixture checked against registered obligations; not a live review.",
                question_sha256=question["prompt_sha256"],
                answer_sha256=digest(bundle["report"].get("answer", "")),
                obligations=dict.fromkeys(question["obligations"], "pass"))


def saved_batch(folder):
    class Seed(StarJobFixture, unittest.TestCase):
        pass
    seed = Seed()
    try:
        seed.open_star([SOLVED, POLISH, ACCEPT])
        job_id = seed.create_job()
        job = seed.terminal(job_id)
        folder.mkdir()
        (folder / "data").mkdir()
        with closing(sqlite3.connect(Path(seed.data_dir) / "showcase.sqlite3")) as source:
            with closing(sqlite3.connect(folder / "data/showcase.sqlite3")) as target:
                source.backup(target)
        for name, value in [("job", job), ("report", seed.report(job_id)),
                            ("evidence", seed.client.get(f"/api/runs/{job_id}/evidence").get_json()),
                            ("role-contexts", seed.outbound), ("acceptance", {"proof_delivered": False})]:
            (folder / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
        hashes = {p.name: digest(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")}
        (folder / "hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
    finally:
        seed.doCleanups()


class LoopbackProvider:
    def __init__(self, scenario="matrix"):
        self.scenario, self.requests, self.run_keys = scenario, [], {}
        self.release = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                wire = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                context = json.loads(wire["messages"][-1]["content"])
                outer.requests.append((wire, context))
                if outer.scenario == "unknown" and len(outer.requests) == 1:
                    self.connection.close()
                    return
                if outer.scenario == "late":
                    outer.release.wait(20)
                reply = outer.respond(context)
                content = json.dumps(reply, ensure_ascii=False)
                if wire.get("stream"):
                    package = {"choices": [{"delta": {"content": content}, "finish_reason": "stop"}],
                               "usage": outer.usage(), "model": "intern-s2"}
                    body = ("data: " + json.dumps(package) + "\n\ndata: [DONE]\n\n").encode()
                else:
                    body = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                                       "usage": outer.usage(), "model": "intern-s2"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream" if wire.get("stream") else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def usage(self):
        return dict(prompt_tokens=7000 if self.scenario == "inefficient" else 7,
                    completion_tokens=3, total_tokens=7003 if self.scenario == "inefficient" else 10)

    def respond(self, context):
        if self.scenario == "protocol":
            return {"assessment": "IMPOSSIBLE_ENUM"}
        run_id, role = context["run_id"], context["role"]
        if run_id not in self.run_keys:
            text = json.dumps(context, ensure_ascii=False)
            key = next((k for k, q in synthetic_registration()["questions"].items() if q["prompt"] in text), None)
            if key is None:
                # JSON escaping can differ; use an original statement fragment.
                key = next(k for k, q in synthetic_registration()["questions"].items() if q["original"][:25] in text)
            self.run_keys[run_id] = key
        key = self.run_keys[run_id]
        answer = ANSWERS[key]
        nonfast = key == "finite" and self.scenario != "all_fast"
        if role == "explore":
            return {"assessment": "NEED_PLAN" if nonfast else "SOLVED", "worked": [], "failed": [],
                    "candidates": [], **({} if nonfast else {"solution_candidate": answer})}
        if role == "explore_polish":
            return {"solution_candidate": answer}
        if role == "planner":
            return {"version": 1, "steps": [{"step_id": "proof", "title": "Prove completeness", "objective": "Derive the result"}]}
        if role == "reasoner":
            claim = {"statement": answer, "label": "easy-verify"}
            if key == "finite":
                claim["tool_request"] = dict(tool="python_math", arguments={"code": ENUMERATION},
                                             scope="finite_computation", expected_output="3\n")
            return {"argument": answer, "claims": [claim], "blocked": False}
        if role == "step_verifier":
            return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
        if role == "final_generator":
            return {"final_response": answer}
        if role == "whole_solution_verifier":
            if self.scenario == "math_reject" and key == "finite":
                return {"verdict": "REJECT", "reason": "Completeness proof has a mathematical gap"}
            return {"verdict": "ACCEPT", "reason": "All registered requirements addressed"}
        raise AssertionError("Unexpected real product request role " + role)

    def adapters(self):
        with patch.dict(os.environ, {"INTERN_API_KEY": "loopback-no-paid", "INTERN_MODEL": "intern-s2"}):
            adapters = {}
            for name, cls in (("nonstream", InternModelAdapter), ("stream", InternStreamAdapter)):
                client = InternChatClient(timeout=180, retry=3, thinking_mode=True)
                client.api_base = f"http://127.0.0.1:{self.server.server_port}"
                adapters[name] = cls(client, max_tokens=8192, thinking_mode=True, temperature=.2)
            return adapters

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
