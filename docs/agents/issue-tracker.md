# Issue tracker

Use GitHub Issues in [RUSS0718/RiCL](https://github.com/RUSS0718/RiCL/issues). Pass `-R RUSS0718/RiCL` when using the GitHub CLI for issue operations.

## Check issue status

```powershell
uv run python scripts/check_issues.py 236 243 246
```

The script reads public issue status and prints one JSON summary without credentials. Use the GitHub connector or an authenticated GitHub CLI to comment or change issue state.
