#!/usr/bin/env bash
set -euo pipefail

command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
uv sync --locked --all-groups
uv run pre-commit install --install-hooks
uv run ruff check ricl_runtime tests
uv run python -m unittest discover -s tests
printf '%s\n' "RiCL Runtime development environment is ready."
