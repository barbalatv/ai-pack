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

            self.assertEqual(self._rel_paths(files), ["included.py"])
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
