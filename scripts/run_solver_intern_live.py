"""Run the explicit six-call Solver Intern live evidence probe; default stays offline."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--followup",
        action="store_true",
        help="Use the smaller 4-call, 1-tool, 120-second follow-up cap",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Explicit local credential configuration; contents are never printed",
    )
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"status": "not_run", "mode": "offline", "http_attempts": 0}))
        return 0
    if args.env_file is not None:
        from dotenv import load_dotenv

        load_dotenv(args.env_file, override=True)
    from showcase.adapters import InternModelAdapter
    from showcase.solver_harness.intern_evidence import run_evidence

    adapter = InternModelAdapter(
        max_tokens=1024, client_timeout=30, client_retry=1, thinking_mode=False, temperature=0.0
    )
    folder, report = run_evidence(
        adapter, ROOT / "artifacts", execution_source="provider_live", followup=args.followup
    )
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "status": report["status"],
                "final_status": report["final_status"],
                "invocations": len(report["invocations"]),
                "budget": report["budget"],
                "evidence_path": str(folder / "evidence.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
