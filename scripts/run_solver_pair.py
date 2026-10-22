"""Generate an offline paired Solver report; this command never enables live calls."""

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--pair-id")
    args = parser.parse_args(argv)
    from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort
    from showcase.solver_harness.paired import PairedRunner

    pair_id = args.pair_id or f"offline-pair-{uuid.uuid4().hex}"
    folder = ROOT / "artifacts" / f"paired-{uuid.uuid4().hex}"
    folder.mkdir(parents=True, exist_ok=False)
    database = args.database or folder / "solver.sqlite3"
    base = {
        "profile": "paired-offline",
        "max_model_calls": 2,
        "max_tool_calls": 0,
        "max_total_duration_seconds": 60,
        "features": {"skills": False},
    }
    conditions = {
        "models": {
            role: {"model_id": "scripted", "revision": "fixture-1"}
            for role in ("reasoner", "verifier")
        },
        "transport": {
            "max_output_tokens": 1024,
            "timeout_seconds": 30,
            "physical_attempts_per_call": 1,
        },
    }

    def ports():
        return {
            "model_port": ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "4"}]),
            "verifier_port": ScriptedVerifierPort([{"verdict": "ACCEPT"}]),
            "source": "scripted",
        }

    with PairedRunner(database_path=database) as runner:
        report = runner.run_pair(
            "Compute 2+2",
            pair_id=pair_id,
            control_config=base,
            variant_config={**base, "features": {"skills": True}},
            conditions=conditions,
            control_ports=ports(),
            variant_ports=ports(),
        )
    path = folder / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "pair_id": pair_id,
                "status": report["status"],
                "live_gate": report["live_gate"],
                "report": str(path),
                "database": str(database),
                "execution_source": "scripted",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
