"""Log Job failure locations without exception messages or source text."""

import logging
from pathlib import Path


def record_job_failure(job_id, error):
    """Retain the first exception's type and frames before public categorization."""
    cause = error
    seen = set()
    sqlite_errorname = None
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        sqlite_errorname = getattr(cause, "sqlite_errorname", None)
        if sqlite_errorname is not None:
            break
        cause = cause.__cause__
    frames = []
    trace = error.__traceback__
    while trace is not None:
        frames.append({"file": Path(trace.tb_frame.f_code.co_filename).name,
                       "function": trace.tb_frame.f_code.co_name, "line": trace.tb_lineno})
        trace = trace.tb_next
    logging.getLogger(__name__).error(
        "job_failure job_id=%s exception_type=%s sqlite_errorname=%s cause_type=%s frames=%s",
        job_id, type(error).__name__, sqlite_errorname,
        type(error.__cause__).__name__ if error.__cause__ is not None else None, frames,
    )
