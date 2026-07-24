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

        expected_keys = {
            "total_found",
            "filtered_hardcoded",
            "filtered_gitignore",
            "filtered_size",
            "filtered_security",
            "filtered_binary",
            "filtered_diff",
            "filtered_user_exclude",
            "filtered_user_include",
            "filtered_errors",
        }
        self.assertEqual(set(result.stats.keys()), expected_keys)

    def test_user_exclude_reflected_in_stats(self) -> None:
        root = self._make_project(
            {
                "src/main.py": "x = 1\n",
                "tests/test_main.py": "assert True\n",
            }
        )

        result = pack_project(root, exclude=["tests/*"])

        self.assertEqual(result.stats["filtered_user_exclude"], 1)
        self.assertEqual(result.files_included, 1)

    def test_file_token_map(self) -> None:
        root = self._make_project(
            {
                "main.py": "print('hello')\n",
                "utils.py": "x = 1\n",
            }
        )

        result = pack_project(root)

        self.assertIn("main.py", result.file_token_map)
        self.assertIn("utils.py", result.file_token_map)
        self.assertTrue(all(v > 0 for v in result.file_token_map.values()))
        self.assertGreaterEqual(
            result.file_token_map["main.py"] + result.file_token_map["utils.py"],
            2,
        )

    def test_secret_snippet_not_in_xml_bundle(self) -> None:
        secret = "sk-abcdefghijklmnopqrstuvwxyz012345678901234567"
        root = self._make_project(
            {
                "config.py": (f'api_key = "{secret}"\n'),
            }
        )

        result = pack_project(root, fmt="xml")

        self.assertGreater(len(result.secret_warnings), 0)
        self.assertIn(secret, result.bundle)
        self.assertIn("<security_warning ", result.bundle)
        self.assertNotIn(">sk-", result.bundle)

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

    def test_redact_reports_count_and_preserves_assignment_context(self) -> None:
        secret = "a" * 24
        root = self._make_project({"config.py": f'API_KEY = "{secret}"\n'})

        result = pack_project(root, fmt="plain", redact=True)

        self.assertEqual(result.redacted_count, 1)
        self.assertIn('API_KEY = "[REDACTED]"', result.bundle)
        self.assertNotIn(secret, result.bundle)

    def test_skeletons_and_symbol_map(self) -> None:
        root = self._make_project(
            {
                "app.py": (
                    "class Service:\n"
                    "    def run(self) -> str:\n"
                    "        return 'implementation'\n"
                )
            }
        )

        result = pack_project(root, fmt="plain", skeletons=True, symbol_map=True)

        self.assertIn("[PYTHON SYMBOL MAP]", result.bundle)
        self.assertIn("class Service", result.bundle)
        self.assertIn("def run(self) -> str", result.bundle)
        self.assertNotIn("return 'implementation'", result.bundle)

    def test_config_is_loaded_and_explicit_api_values_win(self) -> None:
        root = self._make_project(
            {
                "aipack.toml": "[tool.aipack]\nfmt = 'md'\nskeletons = true\n",
                "app.py": "def run():\n    return 'implementation'\n",
            }
        )

        configured = pack_project(root)
        overridden = pack_project(root, fmt="plain", skeletons=False)

        self.assertIn("# Project Bundle", configured.bundle)
        self.assertNotIn("return 'implementation'", configured.bundle)
        self.assertIn("PROJECT BUNDLE", overridden.bundle)
        self.assertIn("return 'implementation'", overridden.bundle)

    def test_auto_shrink_requires_max_tokens(self) -> None:
        root = self._make_project({"main.py": "x = 1\n"})

        with self.assertRaisesRegex(ValueError, "--auto-shrink requires --max-tokens"):
            pack_project(root, auto_shrink=True)

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
