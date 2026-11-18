"""Reuse S03 public Job/report/replay contracts with S04 explicitly enabled."""

import os
from copy import deepcopy
from unittest.mock import patch

import test_faithful_s03_job as s03
from test_faithful_s03_job import (
    CAPACITY_POLICY,
    ENDPOINT,
    FEATURES,
    REPLIES,
)

from showcase.run_budget import RunBudgetLimits


class FaithfulS04PublicJobTest(s03.FaithfulS03PublicJobTest):
    def open_spec_job(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "computation"
        self.open_star(
            replies,
            SHOWCASE_STAR_FEATURES={**FEATURES, "progress_scheduling": True},
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8, max_http_attempts=8, max_tool_calls=0,
                max_tokens=100_000, max_runtime_seconds=1_100,
            ),
        )
