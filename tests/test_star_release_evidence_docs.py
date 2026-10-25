"""Public documentation evidence boundaries for maintenance issue #85."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StarReleaseEvidenceDocsTest(unittest.TestCase):
    def test_current_status_is_separate_from_historical_evidence(self):
        index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        release = (ROOT / "docs/evals/star-product-align10-release.md").read_text(encoding="utf-8")
        self.assertIn("## 当前 ALIGN 状态", index)
        self.assertIn("## 历史 SP 集成语境", index)
        self.assertLess(index.index("## 当前 ALIGN 状态"), index.index("## 历史 SP 集成语境"))
        for required in (
            "## 当前维护证据边界（#85，第一部分）",
            "历史 raw 当前缺失",
            "发现数不等于执行数",
            "75102759beb5ffec1aad94d5f6cbcd5f4383c19a",
            "f1512e24b20ebc20cb344cda749a119746676efe",
            "不是运行 SHA 的独立证明",
            "47dc52241b0cac29e1e3c321f24cbea78e1dce89",
            "618 通过 / 30 skip",
            "FAILED (failures=2)",
            "不推断 0 skip",
            "本轮未重跑浏览器",
            "16472",
            "### 30 项镜像门控逐项归因",
            "维护债务",
            "提供方假设",
        ):
            with self.subTest(required=required):
                self.assertIn(required, release)
        self.assertNotIn("产品侧全部已知阻断缺陷已修复并有 live 逐项验证", release)
        self.assertNotIn("产品侧已无已知阻断缺陷", release)
        summary = json.loads((ROOT / "docs/evals/star-maintenance-evidence-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(len(set(summary["image_skips"])), 30)
        for name in summary["image_skips"]:
            self.assertIn(f"`{name}`", release)
        self.assertEqual(summary["docker_before_test_fix"]["failed"], 2)
        self.assertIsNone(summary["release_after_fix"]["detailed_counts"])
        self.assertEqual(summary["AC18"], "incomplete")
        for artifact in summary["artifacts"]:
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
