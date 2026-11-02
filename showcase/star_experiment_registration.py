"""Spec #87 preregistration. Solver prompts contain no independent answers."""

import hashlib
import json
from pathlib import Path

VERSION = "rob87-round-v1"
E1 = dict(max_model_calls=6, max_http_attempts=8, max_tool_calls=1,
          max_tokens=32768, max_runtime_seconds=300)
E2 = dict(max_model_calls=12, max_http_attempts=16, max_tool_calls=3,
          max_tokens=65536, max_runtime_seconds=600)
ROUND = dict(runs=10, logical_calls=96, http_attempts=128, tool_calls=22,
             charged_tokens=524288, wall_time_seconds=4800, preflights=12,
             tools_including_environment=34)
CONDITIONS = dict(model="intern-s2", timeout=180, max_tokens=8192,
                  retry=3, thinking_mode=True, temperature=0.2,
                  solver_mode="star_reference", verification_mode="auto")
def digest(value):
    data = value.encode("utf-8") if isinstance(value, str) else json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()



def registration(source, *, expected_sha256):
    """Load an explicitly trusted frozen document; never discover paths or answers."""
    record = json.loads(Path(source).read_text(encoding="utf-8")) if isinstance(source, (str, Path)) else json.loads(json.dumps(source))
    if digest(record) != expected_sha256:
        raise ValueError("experiment_registration_identity_mismatch")
    try:
        valid = (record["version"] == VERSION and record["conditions"] == CONDITIONS
                 and record["round_limits"] == ROUND and bool(record["source_checked"])
                 and bool(record["review_rules"]))
        questions, schedule = record["questions"], record["schedule"]
        ids = list(questions)
        valid = valid and len(ids) == 5 and len(schedule) == 10
        first = [schedule[i]["question"] for i in (0, 2)]
        second = [schedule[i]["question"] for i in (4, 5, 6)]
        valid = valid and len(set(first + second)) == 5 and set(first + second) == set(ids)
        order = [("E1", q, t) for q in first for t in ("nonstream", "stream")]
        order += [("E2", q, "nonstream") for _ in range(2) for q in second]
        for i, (stage, key, transport) in enumerate(order):
            valid = valid and schedule[i] == dict(index=i, stage=stage, question=key,
                transport=transport, limits=E1 if stage == "E1" else E2)
        for question in questions.values():
            text = question["original"] + ("\n" + question["addition"] if "addition" in question else "")
            obligations = question["obligations"]
            valid = valid and (isinstance(question["source"], str) and bool(question["source"].strip())
                and isinstance(text, str) and bool(text.strip()) and question["prompt"] == text
                and question["original_sha256"] == digest(question["original"])
                and question["prompt_sha256"] == digest(text)
                and isinstance(obligations, list) and bool(obligations)
                and all(isinstance(o, str) and o.strip() for o in obligations)
                and len(set(obligations)) == len(obligations))
        oracles = record["independent_oracles"]
        valid = valid and set(oracles) == set(ids) and all(v is None or isinstance(v, str) and v.strip() for v in oracles.values())
    except (KeyError, TypeError, IndexError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("experiment_registration_invalid")
    return record
