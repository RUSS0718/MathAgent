"""Check that Flask serves the built workbench and ordinary session API together."""

import re
import tempfile
from contextlib import ExitStack
from pathlib import Path

from showcase.flask_app import create_app


def main() -> None:
    with tempfile.TemporaryDirectory() as data, ExitStack() as stores:
        app = create_app(
            {"SHOWCASE_DATA_DIR": data, "SHOWCASE_WORKER_ENABLED": False},
            database_path=Path(data) / "showcase.sqlite3",
        )
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            stores.callback(app.extensions[key].close)
        with app.test_client() as client:
            dashboard = client.get("/dashboard")
            if dashboard.status_code != 200:
                raise RuntimeError(f"Dashboard returned {dashboard.status_code}")
            assets = re.findall(
                r'(?:src|href)="(/dashboard-assets/workbench/assets/[^"]+)"',
                dashboard.get_data(as_text=True),
            )
            for suffix in (".js", ".css"):
                if not any(asset.endswith(suffix) for asset in assets):
                    raise RuntimeError(f"Dashboard lacks a built workbench {suffix} asset")
            for asset in assets:
                with client.get(asset) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"Workbench asset returned {response.status_code}: {asset}")
            auth = client.get("/api/check_auth").get_json()
            permissions = auth.get("permissions", []) if auth else []
            if "dashboard.access" not in permissions or "reviewer.access" in permissions:
                raise RuntimeError("Dashboard did not create an ordinary workspace session")
            sessions = client.get("/api/sessions")
            if sessions.status_code != 200 or sessions.get_json() != []:
                raise RuntimeError("Ordinary session list is unavailable or unexpectedly populated")
    print("workbench_smoke=PASS")


if __name__ == "__main__":
    main()
