$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv is required. Install it from https://docs.astral.sh/uv/"
}

uv sync --locked --all-groups
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run pre-commit install --install-hooks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run ruff check ricl_runtime tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "RiCL Runtime development environment is ready."
