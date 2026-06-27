"""Tests for the pack_project() Python API."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aipack.api import PackResult, pack_project


class PackProjectApiTests(unittest.TestCase):
    def test_returns_pack_result(self) -> None:
        root = self._make_project({"main.py": "print('hello')\n"})

        result = pack_project(root)

        self.assertIsInstance(result, PackResult)
        self.assertEqual(result.files_included, 1)
        self.assertGreater(result.token_count, 0)
        self.assertGreater(result.bundle_size_bytes, 0)

    def test_fmt_xml_default(self) -> None:
        root = self._make_project({"app.py": "x = 1\n"})

        result = pack_project(root, fmt="xml")

        self.assertIn("<project_bundle", result.bundle)
        self.assertIn("<file path=", result.bundle)

    def test_fmt_plain(self) -> None:
        root = self._make_project({"app.py": "x = 1\n"})

        result = pack_project(root, fmt="plain")

        self.assertIn("PROJECT BUNDLE", result.bundle)
        self.assertIn("FILE: app.py", result.bundle)

    def test_fmt_md(self) -> None:
        root = self._make_project({"app.py": "x = 1\n"})

        result = pack_project(root, fmt="md")

        self.assertIn("# Project Bundle", result.bundle)
        self.assertIn("## app.py", result.bundle)

    def test_max_tokens_raises(self) -> None:
        root = self._make_project({"main.py": "x = 1\n" * 1000})

        with self.assertRaisesRegex(ValueError, "max_tokens"):
            pack_project(root, max_tokens=1)

    def test_exclude_pattern(self) -> None:
        root = self._make_project(
            {
                "src/main.py": "x = 1\n",
                "tests/test_main.py": "assert True\n",
            }
        )

        result = pack_project(root, exclude=["tests/*"])

        self.assertEqual(result.files_included, 1)
        self.assertNotIn("tests/test_main.py", result.bundle)

    def test_security_blacklist_excluded(self) -> None:
        root = self._make_project(
            {
                "main.py": "print('ok')\n",
                ".env": "SECRET_KEY=abc123\n",
            }
        )

        result = pack_project(root)

        self.assertEqual(result.files_included, 1)
        self.assertGreater(len(result.warnings), 0)
        self.assertTrue(any(".env" in warning for warning in result.warnings))

    def test_stats_keys(self) -> None:
        root = self._make_project({"main.py": "x = 1\n"})

        result = pack_project(root)

        self.assertIn("total_found", result.stats)
        self.assertIn("filtered_gitignore", result.stats)

    def test_no_tree(self) -> None:
        root = self._make_project({"main.py": "x = 1\n"})

        result = pack_project(root, no_tree=True, fmt="plain")

        self.assertNotIn("PROJECT STRUCTURE", result.bundle)

    def test_token_placeholder_text_is_preserved_in_file_content(self) -> None:
        source = "\n".join(
            [
                'TOKEN_COUNT_PLACEHOLDER = "__TOKEN_COUNT__"',
                "Estimated tokens: __TOKEN_COUNT__ (cl100k_base)",
                'body = " | __TOKEN_COUNT__ tokens"',
                'xml_attr = "estimated_tokens=\\"__TOKEN_COUNT__\\""',
                "",
            ]
        )
        root = self._make_project({"main.py": source})

        plain = pack_project(root, fmt="plain")
        markdown = pack_project(root, fmt="md")
        xml = pack_project(root, fmt="xml")

        self.assertIn('TOKEN_COUNT_PLACEHOLDER = "__TOKEN_COUNT__"', plain.bundle)
        self.assertIn("Estimated tokens: __TOKEN_COUNT__ (cl100k_base)", plain.bundle)
        self.assertIn('body = " | __TOKEN_COUNT__ tokens"', plain.bundle)
        self.assertNotIn(
            "END OF BUNDLE | 1 files | __TOKEN_COUNT__ tokens", plain.bundle
        )

        self.assertIn('TOKEN_COUNT_PLACEHOLDER = "__TOKEN_COUNT__"', markdown.bundle)
        self.assertIn("Estimated tokens: __TOKEN_COUNT__ (cl100k_base)", markdown.bundle)
        self.assertIn('body = " | __TOKEN_COUNT__ tokens"', markdown.bundle)
        self.assertNotIn(
            "End of bundle: 1 files | __TOKEN_COUNT__ tokens", markdown.bundle
        )

        self.assertIn(
            "TOKEN_COUNT_PLACEHOLDER = &quot;__TOKEN_COUNT__&quot;", xml.bundle
        )
        self.assertIn(
            "Estimated tokens: __TOKEN_COUNT__ (cl100k_base)", xml.bundle
        )
        self.assertIn("body = &quot; | __TOKEN_COUNT__ tokens&quot;", xml.bundle)
        self.assertIn(
            "xml_attr = &quot;estimated_tokens=\\&quot;__TOKEN_COUNT__\\&quot;&quot;",
            xml.bundle,
        )
        self.assertNotIn('estimated_tokens="__TOKEN_COUNT__"', xml.bundle)

    def _make_project(self, files: dict[str, str]) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        for rel_path, content in files.items():
            abs_path = root / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
        return root


if __name__ == "__main__":
    unittest.main()
