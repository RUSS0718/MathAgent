"""Empty answer identities cannot receive mathematical verdicts."""

import unittest
from hashlib import sha256

from showcase.faithful_review_artifact import validate_answer_verdict


class FaithfulReviewArtifactTest(unittest.TestCase):
    def test_missing_answer_requires_unresolved(self):
        for run_id, answer_hash in ((None, None), ("run", None), ("run", ""),
                                    ("run", sha256(b"").hexdigest())):
            identity = dict(run_id=run_id, answer_sha256=answer_hash)
            validate_answer_verdict(identity, "unresolved")
            for verdict in ("pass", "fail"):
                with self.subTest(identity=identity, verdict=verdict), self.assertRaises(ValueError):
                    validate_answer_verdict(identity, verdict)

    def test_nonempty_answer_retains_all_verdicts(self):
        identity = dict(run_id="run", answer_sha256=sha256(b"answer").hexdigest())
        for verdict in ("pass", "fail", "unresolved"):
            validate_answer_verdict(identity, verdict)
