"""Optional real Lean acceptance using the already validated S09 environment."""

import copy
import json
import os
import secrets
from pathlib import Path

from product_server import counts

from showcase.formal import LeanTacticProver, ReviewAuthority
from showcase.formal_correspondence import CHECKER_VERSION
from showcase.formal_docker import LeanDockerExecutor
from showcase.tools import ToolRegistry
from tests.faithful_s09_public_server import FORMAL_POLICY, PROBLEM, SPEC, ScriptedProvider


class CountedFormalProvider(ScriptedProvider):
    """Count real loopback HTTP requests while retaining S09's finite replies."""

    def do_POST(self):
        counts["f7-formal"] += 1
        super().do_POST()


def formal_fixture():
    """Return opt-in existing formal configuration, never simulate a Lean grade."""
    manifest_path = os.environ.get("F7_FORMAL_MANIFEST")
    if not manifest_path:
        return None
    expected = os.environ["F7_FORMAL_GRADE"]
    if expected not in {"L2", "L3"}:
        raise ValueError("f7_formal_grade_invalid")
    executor = LeanDockerExecutor(
        manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8")),
        max_output_bytes=262144,
    )
    authority = ReviewAuthority({CHECKER_VERSION: secrets.token_hex(32)},
                                {CHECKER_VERSION: "independent_service"}) if expected == "L3" else None
    policy = copy.deepcopy(FORMAL_POLICY)
    policy.update(max_output_bytes=executor.max_output_bytes,
                  environment={"deployment_manifest_sha256": executor.environment_hash})
    registry = ToolRegistry()
    registry.register_polynomial_check()
    return {
        "provider": CountedFormalProvider,
        "config": {"SHOWCASE_FORMAL_VERIFICATION_CONFIG": policy,
                   "SHOWCASE_FORMAL_BACKEND": LeanTacticProver(executor, review_authority=authority),
                   "SHOWCASE_STAR_REGISTRY": registry},
        "payload": {"message": PROBLEM, "problem_spec": SPEC, "formal_policy": policy},
    }
