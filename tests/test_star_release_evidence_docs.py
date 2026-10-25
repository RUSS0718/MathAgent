"""Public documentation evidence boundaries for maintenance issue #85."""
from pathlib import Path
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
            "当前最终门禁尚未运行",
            "维护债务",
            "提供方假设",
        ):
            with self.subTest(required=required):
                self.assertIn(required, release)
        self.assertNotIn("产品侧全部已知阻断缺陷已修复并有 live 逐项验证", release)
        self.assertNotIn("产品侧已无已知阻断缺陷", release)


if __name__ == "__main__":
    unittest.main()
