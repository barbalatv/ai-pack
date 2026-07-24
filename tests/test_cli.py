from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from aipack.builder import BundleBuilder
from aipack.cli import pack
from aipack.scanner import FileScanner
from aipack.tree import generate_tree


class TestCliOutput(unittest.TestCase):
    def _make_project(self, files: dict[str, str]) -> Path:
        directory = tempfile.mkdtemp()
        root = Path(directory)
        for rel_path, content in files.items():
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(directory, ignore_errors=True))
        return root

    def test_default_xml_output_path(self) -> None:
        project = self._make_project({"main.py": "x = 1\n"})
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                pack,
                [str(project), "--format", "xml"],
                catch_exceptions=False,
            )

            self.assertEqual(result.exit_code, 0)
            repo_name = project.name
            expected = Path("xml") / f"{repo_name}.xml"
            self.assertTrue(expected.exists(), f"Expected {expected} to exist")
            self.assertIn(
                f"xml/{repo_name}.xml",
                self._combined_output(result).replace("\\", "/"),
            )

    def test_explicit_output_overrides_default(self) -> None:
        project = self._make_project({"main.py": "x = 1\n"})
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                pack,
                [str(project), "--format", "xml", "--output", "custom.xml"],
                catch_exceptions=False,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(Path("custom.xml").exists())
            self.assertFalse(Path("xml").exists())

    def test_default_md_output_path(self) -> None:
        project = self._make_project({"main.py": "x = 1\n"})
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                pack,
                [str(project), "--format", "md"],
                catch_exceptions=False,
            )

            self.assertEqual(result.exit_code, 0)
            repo_name = project.name
            expected = Path("md") / f"{repo_name}.md"
            self.assertTrue(expected.exists(), f"Expected {expected} to exist")

    def test_default_plain_output_path(self) -> None:
        project = self._make_project({"main.py": "x = 1\n"})
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                pack,
                [str(project), "--format", "plain"],
                catch_exceptions=False,
            )

            self.assertEqual(result.exit_code, 0)
            repo_name = project.name
            expected = Path("plain") / f"{repo_name}.txt"
            self.assertTrue(expected.exists(), f"Expected {expected} to exist")

    def test_default_chunk_output_path(self) -> None:
        project = self._make_project({"main.py": "x = 1\n"})
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                pack,
                [str(project), "--format", "plain", "--chunk-size", "10000"],
                catch_exceptions=False,
            )

            self.assertEqual(result.exit_code, 0)
            repo_name = project.name
            expected = Path("plain") / f"{repo_name}_001.txt"
            self.assertTrue(expected.exists(), f"Expected {expected} to exist")

    def test_auto_shrink_guards(self) -> None:
        project = self._make_project({"main.py": "x = 1\n"})
        runner = CliRunner()

        missing_limit = runner.invoke(pack, [str(project), "--auto-shrink", "--lang", "en"])
        conflict = runner.invoke(
            pack,
            [str(project), "--auto-shrink", "--max-tokens", "100", "--chunk-size", "50", "--lang", "en"],
        )

        self.assertNotEqual(missing_limit.exit_code, 0)
        self.assertIn("--auto-shrink requires --max-tokens", self._combined_output(missing_limit))
        self.assertNotEqual(conflict.exit_code, 0)
        self.assertIn("--auto-shrink cannot be combined", self._combined_output(conflict))

    def test_token_budget_error_uses_exit_code_two(self) -> None:
        project = self._make_project({"main.py": "x = 1\n" * 1000})
        runner = CliRunner()

        result = runner.invoke(pack, [str(project), "--max-tokens", "1", "--lang", "en"])

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Bundle exceeds --max-tokens", self._combined_output(result))

    def test_explicit_no_skeletons_overrides_docs_preset(self) -> None:
        project = self._make_project(
            {"app.py": "def run():\n    return 'implementation'\n"}
        )
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                pack,
                [
                    str(project),
                    "--preset",
                    "docs",
                    "--no-skeletons",
                    "--output",
                    "bundle.txt",
                ],
                catch_exceptions=False,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertIn("return 'implementation'", Path("bundle.txt").read_text(encoding="utf-8"))

    def test_default_cli_bundle_matches_builder_without_new_flags(self) -> None:
        project = self._make_project(
            {"app.py": "def run():\n    return 'implementation'\n"}
        )
        runner = CliRunner()
        fixed_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with patch("aipack.builder.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_time
            scanner = FileScanner(project, [], [], "500kb", None)
            builder = BundleBuilder()
            files = builder.sort_files(scanner.scan())
            tree = generate_tree(project, [file.abs_path for file in files])
            expected = builder.build_plain(project, files, tree, False, [])

            with runner.isolated_filesystem():
                result = runner.invoke(pack, [str(project)], catch_exceptions=False)
                output = Path("plain") / f"{project.name}.txt"
                self.assertEqual(result.exit_code, 0)
                self.assertEqual(output.read_text(encoding="utf-8"), expected)

    @staticmethod
    def _combined_output(result) -> str:
        try:
            stderr = result.stderr or ""
        except ValueError:
            stderr = ""
        return result.output + stderr


if __name__ == "__main__":
    unittest.main()
