from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aipack.config import DEFAULTS, load_config_file, merge_settings


class ConfigTests(unittest.TestCase):
    def test_merge_precedence_replaces_lists(self) -> None:
        merged = merge_settings(
            DEFAULTS,
            {"exclude": ["config/*"], "fmt": "xml"},
            {"exclude": ["preset/*"], "skeletons": True},
            {"exclude": ["cli/*"], "fmt": "md"},
        )

        self.assertEqual(merged["exclude"], ["cli/*"])
        self.assertEqual(merged["fmt"], "md")
        self.assertTrue(merged["skeletons"])

    def test_aipack_toml_wins_over_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aipack.toml").write_text(
                "[tool.aipack]\nfmt = 'md'\nunknown = true\n",
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                "[tool.aipack]\nfmt = 'xml'\n",
                encoding="utf-8",
            )

            config = load_config_file(root)

        self.assertEqual(config["fmt"], "md")
        self.assertNotIn("unknown", config)
        self.assertIn("_config_warning", config)

    def test_empty_and_unknown_config_returns_no_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aipack.toml").write_text("[tool.aipack]\nfuture_option = 1\n", encoding="utf-8")

            self.assertEqual(load_config_file(root), {})


if __name__ == "__main__":
    unittest.main()
