"""Registry adapter gives the container supervisor ownership of bounded cleanup."""

from contextlib import contextmanager
from contextvars import ContextVar

from .graph import ToolExecutionResult
from .python_executor import DockerPythonExecutor
from .run_budget import current_budget
from .run_control import RunStopped, check_control

_request = ContextVar("container_tool_request", default=None)


@contextmanager
def tool_request(request):
    token = _request.set(request)
    try:
        yield
    finally:
        _request.reset(token)


class ContainerPythonTool:
    owns_execution_limits = True

    def __init__(self, executor):
        self.executor = executor

    def invoke(self, arguments):
        request = _request.get()
        budget = current_budget()
        if request is None or budget is None or request["run_id"] != budget.run_id:
            return ToolExecutionResult(status="rejected", error_category="container_run_required")

        def canceled():
            try:
                check_control()
                return False
            except RunStopped:
                return True

        executor = DockerPythonExecutor(image=self.executor.image,
            artifact_root=self.executor.artifacts.root,
            timeout_seconds=min(self.executor.timeout_seconds, request["timeout_seconds"], budget.remaining_seconds()),
            max_output_bytes=min(self.executor.max_output_bytes, request["max_output_bytes"]))
        value = executor.execute(arguments["code"], run_id=request["run_id"],
            call_id=request["call_id"], input_payload=dict(arguments), canceled=canceled)
        status = "success" if value["status"] == "success" else "timeout" if value["status"] == "timeout" else "error"
        return ToolExecutionResult(status=status, value=value,
            result_summary="Container mathematical Python: " + value["status"],
            error_category=None if status == "success" else value["status"],
            duration_seconds=value.get("duration_seconds", 0))
