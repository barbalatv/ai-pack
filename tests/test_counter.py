from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from aipack.counter import estimate_tokens


class CounterTests(unittest.TestCase):
    def test_falls_back_when_tiktoken_raises_non_import_error(self) -> None:
        with patch("tiktoken.get_encoding", side_effect=OSError("network unreachable")):
            self.assertEqual(estimate_tokens("x" * 40), 10)

    def test_falls_back_when_tiktoken_not_installed(self) -> None:
        with patch.dict(sys.modules, {"tiktoken": None}):
            self.assertGreaterEqual(estimate_tokens("hello"), 1)


if __name__ == "__main__":
    unittest.main()
