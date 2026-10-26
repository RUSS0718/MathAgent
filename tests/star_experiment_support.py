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
from showcase.star_experiment_registration import digest, registration
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

ANSWERS = {
    "multiply": "17×23=17×(20+3)=340+51=391，因此结果是391。",
    "fractions": "3/4+1/6=9/12+2/12=11/12，通分后相加。",
    "digit_cancel": "Enumerating all two-digit n<d and nonzero canceled digits gives 16/64, 19/95, 26/65, 49/98. Their reduced product is 1/100; the denominator is 100.",
    "partitions": "Let c[j,n]=c[j-1,n]+c[j,n-j] with c[j,0]=1. The largest allowed part separates disjoint cases and gives every unordered partition exactly once. Evaluate to c[100,100]=190569292; remove the single part [100], giving 190569291.",
    "sharp": "Write F=xy+yz+zx-2xyz. Since x,y,z≤1, F≥(xy+yz+zx)/3≥0, with equality at a vertex. On the boundary F≤1/4. At an interior stationary point, subtracting the Lagrange equations gives (x-y)(1-2z)=0 and its cyclic versions. If variables differ, another coordinate must be 1/2; the remaining equations contradict strict positivity. Thus x=y=z=1/3 is the only interior stationary point, giving F=7/27. Compactness proves the upper bound; equality holds at (1/3,1/3,1/3).",
}


ENUMERATION = """from fractions import Fraction
from math import prod
found=set()
for n in range(10,100):
    for d in range(n+1,100):
        for c in '123456789':
            if c in str(n) and c in str(d):
                a=str(n).replace(c,'',1)
                b=str(d).replace(c,'',1)
                if int(b) and Fraction(n,d)==Fraction(int(a),int(b)):
                    found.add(Fraction(n,d))
print(prod(found).denominator)
"""


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
            key = next((k for k, q in registration()["questions"].items() if q["prompt"] in text), None)
            if key is None:
                # JSON escaping can differ; use an original statement fragment.
                key = next(k for k, q in registration()["questions"].items() if q["original"][:25] in text)
            self.run_keys[run_id] = key
        key = self.run_keys[run_id]
        answer = ANSWERS[key]
        nonfast = key == "digit_cancel" and self.scenario != "all_fast"
        if role == "explore":
            return {"assessment": "NEED_PLAN" if nonfast else "SOLVED", "worked": [], "failed": [],
                    "candidates": [], **({} if nonfast else {"solution_candidate": answer})}
        if role == "explore_polish":
            return {"solution_candidate": answer}
        if role == "planner":
            return {"version": 1, "steps": [{"step_id": "proof", "title": "Prove completeness", "objective": "Derive the result"}]}
        if role == "reasoner":
            claim = {"statement": answer, "label": "easy-verify"}
            if key == "digit_cancel":
                claim["tool_request"] = dict(tool="python_math", arguments={"code": ENUMERATION},
                                             scope="finite_computation", expected_output="100\n")
            return {"argument": answer, "claims": [claim], "blocked": False}
        if role == "step_verifier":
            return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
        if role == "final_generator":
            return {"final_response": answer}
        if role == "whole_solution_verifier":
            if self.scenario == "math_reject" and key == "digit_cancel":
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
        self.server.shutdown()
        self.server.server_close()
