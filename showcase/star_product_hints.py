"""Bounded private Job hints and public categorical provenance."""

from .solver_harness.star_routing import is_valid_hint


def validate_hint(hint, solver_mode):
    if hint is None:
        return
    from .workspace import WorkspaceError

    if solver_mode != "star_limited" or not is_valid_hint(hint):
        raise WorkspaceError("solver_hint_invalid", status=400)


def migrate_hints(connection, columns):
    if "solver_hint" not in columns:
        connection.execute("ALTER TABLE workspace_jobs ADD COLUMN solver_hint TEXT")
