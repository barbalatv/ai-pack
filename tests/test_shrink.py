from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aipack.builder import BundleBuilder
from aipack.counter import estimate_tokens
from aipack.scanner import FileScanner
from aipack.shrink import auto_shrink
from aipack.tree import generate_tree


class AutoShrinkTests(unittest.TestCase):
    def test_omits_tests_visibly_before_lower_priority_files(self) -> None:
        root = self._make_project(
            {
                "README.md": "# Keep this documentation\n",
                "main.py": "def run():\n    return 'keep'\n",
                "tests/test_large.py": "PAYLOAD = '" + ("x" * 40_000) + "'\n",
            }
        )
        builder, files, tree = self._bundle_inputs(root)
        test_file = next(file for file in files if file.rel_path.as_posix() == "tests/test_large.py")
        target = builder.build_plain(
            root,
            files,
            tree,
            False,
            [],
            skeletonize=True,
            omitted={test_file.abs_path: "auto-shrink"},
        )

        bundle, report = auto_shrink(
            builder,
            root,
            files,
            tree,
            "plain",
            [],
            estimate_tokens(target),
            False,
            False,
        )

        self.assertIn("strip_comments", report.steps_applied)
        self.assertIn("skeletons", report.steps_applied)
        self.assertIn("omit_tests", report.steps_applied)
        self.assertIn(("tests/test_large.py", "auto-shrink"), report.omitted_files)
        self.assertIn("FILE: tests/test_large.py [OMITTED - auto-shrink: token budget]", bundle)
        self.assertIn("# Keep this documentation", bundle)
        self.assertIn("def run():", bundle)

    def test_raises_when_priority_zero_file_cannot_be_omitted(self) -> None:
        root = self._make_project({"README.md": "x" * 20_000})
        builder, files, tree = self._bundle_inputs(root)

        with self.assertRaisesRegex(ValueError, "auto-shrink"):
            auto_shrink(builder, root, files, tree, "plain", [], 1, False, False)

    def _bundle_inputs(self, root: Path):
        scanner = FileScanner(root, [], [], "500kb", None)
        builder = BundleBuilder()
        files = builder.sort_files(scanner.scan())
        tree = generate_tree(root, [file.abs_path for file in files])
        return builder, files, tree

    def _make_project(self, files: dict[str, str]) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        for rel_path, content in files.items():
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root


if __name__ == "__main__":
    unittest.main()
