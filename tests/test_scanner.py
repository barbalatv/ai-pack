from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aipack.scanner import FileScanner


class FileScannerTests(unittest.TestCase):
    def test_hardcoded_excludes_and_security_blacklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "src" / "app.py", "print('hello')\n")
            self._write(root / ".env", "SECRET=abc\n")
            self._write(root / "node_modules" / "pkg" / "index.js", "console.log(1)\n")
            self._write_bytes(root / "logo.png", b"not really a png")

            scanner = FileScanner(root, [], [], "500kb", None)
            files = scanner.scan()

            self.assertEqual(self._rel_paths(files), ["src/app.py"])
            self.assertEqual(scanner.stats.filtered_security_blacklist, 1)
            self.assertGreaterEqual(scanner.stats.filtered_hardcoded, 1)

    def test_gitignore_user_exclude_and_size_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / ".gitignore", "ignored.txt\n")
            self._write(root / "included.py", "print('ok')\n")
            self._write(root / "ignored.txt", "ignored\n")
            self._write(root / "notes.md", "skip me\n")
            self._write(root / "large.py", "x" * 32)

            scanner = FileScanner(root, ["notes.md"], [], "20b", None)
            files = scanner.scan()

            self.assertEqual(self._rel_paths(files), [".gitignore", "included.py"])
            self.assertEqual(scanner.stats.filtered_gitignore, 1)
            self.assertEqual(scanner.stats.filtered_user_exclude, 1)
            self.assertEqual(scanner.stats.filtered_size, 1)

    def test_include_only_filters_non_matching_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "a.py", "print('a')\n")
            self._write(root / "b.md", "# b\n")

            scanner = FileScanner(root, [], ["*.py"], "500kb", None)
            files = scanner.scan()

            self.assertEqual(self._rel_paths(files), ["a.py"])
            self.assertEqual(scanner.stats.filtered_user_include, 1)

    def test_binary_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "text.py", "print('text')\n")
            self._write_bytes(root / "data.custom", b"abc\0def")

            scanner = FileScanner(root, [], [], "500kb", None)
            files = scanner.scan()

            self.assertEqual(self._rel_paths(files), ["text.py"])
            self.assertEqual(scanner.stats.filtered_binary, 1)

    def test_symlink_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            self._write(root / "real.py", "x = 1\n")

            target = root.parent / "outside_secret.txt"
            target.write_text("SECRET_KEY=hunter2\n", encoding="utf-8")
            link = root / "local_secret.txt"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"Symlinks are not available: {exc}")

            scanner = FileScanner(root, [], [], "500kb", None)
            files = scanner.scan()

            included_names = [file.rel_path.name for file in files]
            self.assertNotIn("local_secret.txt", included_names)
            self.assertIn("real.py", included_names)
            self.assertGreater(scanner.stats.filtered_errors, 0)
            self.assertTrue(
                any("symlink" in warning.lower() for warning in scanner.stats.warnings)
            )

    def test_env_example_not_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / ".env", "SECRET_KEY=real_secret\n")
            self._write(root / ".env.example", "SECRET_KEY=your_key_here\n")
            self._write(root / ".env.template", "SECRET_KEY=your_key_here\n")
            self._write(root / "main.py", "x = 1\n")

            scanner = FileScanner(root, [], [], "500kb", None)
            files = scanner.scan()

            included_names = {file.rel_path.name for file in files}
            self.assertIn(".env.example", included_names)
            self.assertIn(".env.template", included_names)
            self.assertNotIn(".env", included_names)

    def test_parse_max_size(self) -> None:
        self.assertEqual(FileScanner._parse_max_size("1kb"), 1024)
        self.assertEqual(FileScanner._parse_max_size("1.5kb"), 1536)
        self.assertEqual(FileScanner._parse_max_size("2mb"), 2 * 1024 * 1024)

    @staticmethod
    def _write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _write_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def _rel_paths(files) -> list[str]:
        return sorted(file.rel_path.as_posix() for file in files)


if __name__ == "__main__":
    unittest.main()
