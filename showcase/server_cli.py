"""CLI configuration for the explicit Showcase service."""

import argparse
from typing import Any


def parse_server_args(argv=None):
    """Preserve legacy flags and optionally assemble the Faithful service."""
    parser = argparse.ArgumentParser(description="Local v0.2 Flask Showcase API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--mode", choices=("fake", "live"), default="fake")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--star-limited", action="store_true", help="Enable explicit limited STAR selection")
    parser.add_argument("--star-full", action="store_true", help="Enable full STAR presets after isolated runtime preflight; requires exact image configuration")
    parser.add_argument("--faithful-memory-review", action="store_true", help="Expose Faithful memory controls and review")
    parser.add_argument("--faithful-population-memory", action="store_true", help="Allow explicitly enabled session observations as advisory context in STAR Runs")
    parser.add_argument("--faithful-intervention", action="store_true", help="Expose authenticated Faithful Intervention controls")
    parser.add_argument("--faithful-system-view", action="store_true", help="Enable the opt-in read-only F7 system view API")
    parser.add_argument(
        "--experiment-idempotency-lookup",
        action="store_true",
        help="Enable the experiment CLI's idempotency lookup Job route",
    )
    parser.add_argument("--faithful-config", help="Trusted faithful-service-v1 JSON file (requires live)")
    parser.add_argument("--check-runtime", action="store_true", help="Report configured capability admission without serving or solving")
    args = parser.parse_args(argv)
    if args.check_runtime and not args.faithful_config:
        parser.error("--check-runtime requires --faithful-config")
    if args.faithful_config and args.mode != "live":
        parser.error("--faithful-config requires --mode live")
    config: dict[str, Any] = {"SHOWCASE_MODE": args.mode, "SHOWCASE_STAR_ENABLED": args.star_limited,
                              "SHOWCASE_STAR_FULL_ENABLED": args.star_full,
                              "SHOWCASE_FAITHFUL_MEMORY_ENABLED": (
                                  args.faithful_memory_review or args.faithful_population_memory
                              ),
                              "SHOWCASE_POPULATION_MEMORY_ENABLED": args.faithful_population_memory,
                              "SHOWCASE_FAITHFUL_INTERVENTION_ENABLED": args.faithful_intervention,
                              "SHOWCASE_F7_SYSTEM_VIEW_ENABLED": args.faithful_system_view,
                              "SHOWCASE_EXPERIMENT_IDEMPOTENCY_LOOKUP_ENABLED": args.experiment_idempotency_lookup}
    if args.data_dir:
        config["SHOWCASE_DATA_DIR"] = args.data_dir
    if args.faithful_config:
        from .faithful_service_config import load_faithful_config

        try:
            config.update(load_faithful_config(args.faithful_config))
        except (OSError, ValueError, TypeError, KeyError):
            parser.error("faithful configuration invalid; check version, fields and dependency files")
    return args, config
