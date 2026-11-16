"""Report service admission without confusing configuration with live acceptance."""

import json
import secrets
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
        # This trusted local diagnostic owns the app and explicitly enters the
        # same reviewer boundary as technical clients; ordinary HTTP stays scoped.
        secret = app.config.get("SHOWCASE_REVIEWER_SECRET") or secrets.token_urlsafe(32)
        app.config["SHOWCASE_REVIEWER_SECRET"] = secret
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        granted = client.post("/api/reviewer/grant", json={"secret": secret},
                              headers={"X-CSRF-Token": csrf})
        if granted.status_code != 200:
            raise RuntimeError("runtime_check_reviewer_admission_failed")
        capabilities = client.get("/api/capabilities").get_json()
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
