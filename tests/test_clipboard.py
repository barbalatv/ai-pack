from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from aipack.clipboard import copy_to_clipboard


class ClipboardTests(unittest.TestCase):
    def test_success_uses_pyperclip_without_real_clipboard(self) -> None:
        copied: list[str] = []
        fake_pyperclip = types.SimpleNamespace(copy=copied.append)

        with patch.dict(sys.modules, {"pyperclip": fake_pyperclip}):
            success, reason = copy_to_clipboard("bundle")

        self.assertTrue(success)
        self.assertIsNone(reason)
        self.assertEqual(copied, ["bundle"])

    def test_backend_error_is_reported_without_raising(self) -> None:
        def fail_copy(_: str) -> None:
            raise RuntimeError("no display")

        fake_pyperclip = types.SimpleNamespace(copy=fail_copy)
        with patch.dict(sys.modules, {"pyperclip": fake_pyperclip}):
            success, reason = copy_to_clipboard("bundle")

        self.assertFalse(success)
        self.assertEqual(reason, "no display")

    def test_missing_optional_dependency_is_reported(self) -> None:
        original_import = __import__

        def import_without_pyperclip(name, *args, **kwargs):
            if name == "pyperclip":
                raise ImportError("missing")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_pyperclip):
            success, reason = copy_to_clipboard("bundle")

        self.assertFalse(success)
        self.assertIn("pyperclip not installed", reason or "")


if __name__ == "__main__":
    unittest.main()
