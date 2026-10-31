"""Issue #98: strict non-streaming completion requires a metered transport."""

import os
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter


class StrictCompletionContractTest(unittest.TestCase):
    def test_unmetered_strict_completion_does_not_send_or_silently_accept(self):
        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "unconfirmed"}}]}

            def close(self):
                pass

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            client = InternChatClient(timeout=2, retry=1)
        with patch("llm_client.requests.post", return_value=Reply()) as post:
            with self.assertRaises(AdapterError) as caught:
                InternModelAdapter(client).complete(
                    [{"role": "user", "content": "offline"}],
                    metadata={"strict_completion": True})
        self.assertEqual("run_budget_exhausted", caught.exception.category)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
