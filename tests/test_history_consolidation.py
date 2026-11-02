"""Verify consolidated history at the repository's provenance boundary."""

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*arguments):
    """Read committed Git metadata without inspecting user-owned files."""
    return subprocess.check_output(["git", *arguments], cwd=ROOT).decode("utf-8").strip()


class HistoryConsolidationTest(unittest.TestCase):
    """Keep equivalent source checkpoints and delivery differences auditable."""

    def setUp(self):
        self.mapping = json.loads(
            (ROOT / "docs/engineering/integration-history-map.json").read_text(encoding="utf-8")
        )

    def test_rebuilt_checkpoints_match_original_trees(self):
        self.assertEqual(8, len(self.mapping["stages"]))
        self.assertEqual(
            self.mapping["original_tip"],
            git("rev-parse", self.mapping["archive_ref"] + "^{commit}"),
        )
        for stage in self.mapping["stages"][:7]:
            with self.subTest(stage=stage["name"]):
                self.assertEqual(
                    git("rev-parse", stage["original_tip"] + "^{tree}"),
                    git("rev-parse", stage["new_checkpoint"] + "^{tree}"),
                )
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", stage["new_checkpoint"], "HEAD"],
                    cwd=ROOT,
                    check=True,
                )

    def test_release_anchor_is_an_equivalent_current_ancestor(self):
        matrix = json.loads(
            (ROOT / "docs/evals/showcase-solver-v1.2-matrix.json").read_text(encoding="utf-8")
        )
        original = matrix["historical_source_commit"]
        current = matrix["source_commit"]
        self.assertEqual(self.mapping["stages"][0]["original_tip"], original)
        self.assertEqual(self.mapping["stages"][0]["new_checkpoint"], current)
        self.assertEqual(
            git("rev-parse", original + "^{tree}"), git("rev-parse", current + "^{tree}")
        )
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", current, "HEAD"], cwd=ROOT, check=True
        )
        old_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", original, "HEAD"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(1, old_ancestor.returncode)

    def test_final_delivery_only_changes_approved_migration_files(self):
        tip = git("log", "-1", "--format=%H", "--", "docs/engineering/integration-history-map.json")
        changed = set(git("diff", "--name-only", self.mapping["original_tip"], tip).splitlines())
        self.assertEqual(
            {
                "llm_client.py",
                "docs/evals/showcase-solver-v1.2-matrix.json",
                "docs/engineering/integration-history-map.json",
                "docs/engineering/integration-history.md",
                "tests/test_history_consolidation.py",
                "tests/test_python_executor_docker.py",
            },
            changed,
        )
