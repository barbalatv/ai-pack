from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner

from aipack.cli import pack


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

    @staticmethod
    def _combined_output(result) -> str:
        try:
            stderr = result.stderr or ""
        except ValueError:
            stderr = ""
        return result.output + stderr


if __name__ == "__main__":
    unittest.main()
