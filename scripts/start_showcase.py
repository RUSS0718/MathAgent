"""Start the local Showcase workbench or its JupyterLab example."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "showcase" / "frontend" / "chat-frontend"
HOST = "127.0.0.1"
UV_RUN = ["uv", "run", "--locked", "--extra", "showcase"]


def start_web(args: argparse.Namespace) -> None:
    """Build the Vue workbench and serve it with the Showcase backend."""
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise FileNotFoundError("Web mode requires Node.js and npm on PATH.")
    subprocess.run(
        [npm, "ci", "--include=dev", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True
    )
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)

    data_dir = args.data_dir or f"artifacts/showcase-{'local' if args.mode == 'fake' else 'live'}"
    command = [
        *UV_RUN,
        "python",
        "showcase_server.py",
        "--host",
        HOST,
        "--port",
        str(args.port),
        "--mode",
        args.mode,
        "--data-dir",
        data_dir,
    ]
    if args.faithful_config:
        command.extend(["--faithful-config", args.faithful_config])
    print(f"Showcase ({args.mode}): http://{HOST}:{args.port}/dashboard", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def start_notebook(args: argparse.Namespace) -> None:
    """Open a writable copy of the example in a local JupyterLab server."""
    output_dir = ROOT / "artifacts" / "showcase-notebook"
    output_dir.mkdir(parents=True, exist_ok=True)
    notebook_dir = Path(tempfile.mkdtemp(prefix="run-", dir=output_dir))
    notebook = notebook_dir / "showcase.ipynb"
    shutil.copyfile(ROOT / "examples" / notebook.name, notebook)
    subprocess.run(
        [
            *UV_RUN,
            "--with",
            "jupyterlab==4.6.6",
            "python",
            "-m",
            "jupyterlab",
            f"--ServerApp.ip={HOST}",
            f"--ServerApp.port={args.port}",
            "--ServerApp.port_retries=0",
            f"--ServerApp.root_dir={notebook_dir}",
            f"--LabApp.default_url=/lab/tree/{notebook.name}",
        ],
        cwd=ROOT,
        env={**os.environ, "MATHAGENT_SHOWCASE_MODE": args.mode},
        check=True,
    )


def main() -> int:
    """Parse the launch mode and forward the service's exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("web", help="Build and serve the Vue workbench")
    web.add_argument("--port", type=int, default=8090)
    web.add_argument("--data-dir", help="Showcase storage directory (relative to the repository)")
    web.add_argument("--faithful-config", help="Faithful service JSON file (requires live mode)")
    notebook = commands.add_parser("notebook", help="Open the Showcase example in JupyterLab")
    notebook.add_argument("--port", type=int, default=8888)
    for command in (web, notebook):
        command.add_argument("--mode", choices=("live", "fake"), default="live")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.command == "web" and args.faithful_config and args.mode != "live":
        web.error("--faithful-config requires --mode live")
    try:
        launch = start_web if args.command == "web" else start_notebook
        launch(args)
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except OSError as exc:
        print(f"Showcase startup failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
