"""Report service admission without confusing configuration with live acceptance."""

import json
import tempfile
from pathlib import Path


def run_runtime_check(config):
    """Use a fresh database so readiness cannot recover or mutate existing Jobs."""
    from .flask_app import create_app

    with tempfile.TemporaryDirectory(prefix="faithful-check-") as directory:
        return check_runtime(create_app({**config, "SHOWCASE_DATA_DIR": directory,
                                         "SHOWCASE_DATABASE_PATH": str(Path(directory) / "check.sqlite3"),
                                         "SHOWCASE_WORKER_ENABLED": False}))


def check_runtime(app):
    """Inspect public capabilities; never dispatch a mathematical task."""
    try:
        capabilities = app.test_client().get("/api/capabilities").get_json()
        requested = {"star_reference"}
        if app.config.get("SHOWCASE_STAR_POPULATION_ENABLED"):
            requested.add("star_population")
        modes = [{key: value for key, value in item.items() if key != "last_preflight"}
                 for item in capabilities["solver_modes"] if item["solver_mode"] in requested]
        ready = (capabilities["faithful"]["ready"] and len(modes) == len(requested)
                 and all(item["enabled"] for item in modes))
        print(json.dumps({
            "scope": "configuration_and_runtime_admission",
            "ready": ready,
            "solver_modes": modes,
            "features": app.config["SHOWCASE_STAR_FULL_FEATURES"],
            "presentation": capabilities["presentation"],
            "system_view": capabilities["faithful_system_view"],
            "formal": "configured_not_probed" if app.config.get("SHOWCASE_FORMAL_BACKEND")
                      else "not_configured",
            "faithful": capabilities["faithful"],
            "input_requires": ["problem"],
            "provider_live_acceptance": "not_run",
        }, ensure_ascii=False))
        return 0 if ready else 1
    finally:
        for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            app.extensions[key].close()
