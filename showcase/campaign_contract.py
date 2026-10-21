"""Immutable input and identity contract for explicit paired experiments."""

import hashlib
import json
import re
import subprocess
from dataclasses import asdict
from pathlib import Path

from .run_budget import RunBudgetLimits
from .workspace import WorkspaceError


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def validate_campaign(body):
    allowed = {
        "schema_version",
        "dataset_version",
        "problems",
        "model",
        "allow_network",
        "budget",
        "conditions",
        "strategies",
    }
    if (
        not isinstance(body, dict)
        or set(body) - allowed
        or type(body.get("schema_version")) is not int
        or body.get("schema_version") != 1
    ):
        raise WorkspaceError("campaign_invalid")
    version = body.get("dataset_version")
    problems = body.get("problems")
    if not isinstance(version, str) or not re.fullmatch(r"[\w.-]{1,100}", version):
        raise WorkspaceError("dataset_version_invalid")
    if not isinstance(problems, list) or not 1 <= len(problems) <= 100:
        raise WorkspaceError("campaign_problems_invalid")
    ids = set()
    for item in problems:
        if not isinstance(item, dict) or set(item) != {"id", "problem"}:
            raise WorkspaceError("campaign_problem_invalid")
        identifier, problem = item["id"], item["problem"]
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[\w.-]{1,100}", identifier)
            or identifier in ids
        ):
            raise WorkspaceError("campaign_problem_id_invalid")
        if not isinstance(problem, str) or not problem.strip() or len(problem) > 20_000:
            raise WorkspaceError("campaign_problem_invalid")
        ids.add(identifier)
    if (
        body.get("model", "intern-s2") != "intern-s2"
        or type(body.get("allow_network", False)) is not bool
    ):
        raise WorkspaceError("campaign_model_or_network_invalid")
    try:
        limits = RunBudgetLimits(**body["budget"])
        if set(body["budget"]) != set(asdict(limits)):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise WorkspaceError("campaign_budget_invalid") from None
    conditions = body.get("conditions", {"thinking_mode": True, "max_tokens": 256})
    if not isinstance(conditions, dict) or set(conditions) != {"thinking_mode", "max_tokens"}:
        raise WorkspaceError("campaign_conditions_invalid")
    if (
        conditions["thinking_mode"] is not True
        or type(conditions["max_tokens"]) is not int
        or not 1 <= conditions["max_tokens"] <= 16384
    ):
        raise WorkspaceError("campaign_conditions_invalid")
    strategies = body.get("strategies", {"baseline": {}, "candidate": {}})
    if not isinstance(strategies, dict) or set(strategies) != {"baseline", "candidate"}:
        raise WorkspaceError("campaign_strategies_invalid")
    for arm, strategy in strategies.items():
        if not isinstance(strategy, dict) or set(strategy) - {"verification_mode"}:
            raise WorkspaceError("campaign_strategy_unavailable")
        if not isinstance(strategy.get("verification_mode", "auto"), str) or strategy.get(
            "verification_mode", "auto"
        ) not in {"auto", "required", "off"}:
            raise WorkspaceError("verification_mode_invalid")
        strategies[arm] = {"verification_mode": strategy.get("verification_mode", "auto")}
    common = {
        "dataset_version": version,
        "data_hash": digest(problems),
        "model": "intern-s2",
        "allow_network": body.get("allow_network", False),
        "budget": asdict(limits),
        "conditions": conditions,
    }
    return {"schema_version": 1, "common": common, "strategies": strategies, "problems": problems}


def source_identity():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    )
    baseline = json.loads((root / "BASELINE.json").read_text(encoding="utf-8"))
    return {
        "commit": result.stdout.strip(),
        "baseline_commit": baseline["source_commit"],
        "baseline_hash": hashlib.sha256((root / "BASELINE.json").read_bytes()).hexdigest(),
        "baseline_files": baseline["files"],
    }
