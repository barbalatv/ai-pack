from __future__ import annotations

import unittest

from aipack.pyast import extract_python_structure, render_symbol_map, skeletonize_python


SAMPLE = '''import os
from pathlib import Path

VALUE = 42

class Service:
    """Service docs."""

    def start(self, path: Path) -> str:
        """Start docs."""
        return str(path)

    async def stop(self) -> None:
        await cleanup()

def helper(value: int) -> bool:
    return value > 0
'''


class PyAstTests(unittest.TestCase):
    def test_extracts_imports_symbols_and_methods(self) -> None:
        structure = extract_python_structure(SAMPLE)

        self.assertIsNone(structure.parse_error)
        self.assertEqual(structure.imports, ["import os", "from pathlib import Path"])
        self.assertEqual([symbol.name for symbol in structure.symbols], ["Service", "helper"])
        service = structure.symbols[0]
        self.assertEqual([child.name for child in service.children], ["start", "stop"])
        self.assertEqual(service.children[0].signature, "def start(self, path: Path) -> str")
        self.assertEqual(service.children[1].signature, "async def stop(self) -> None")

        rendered = render_symbol_map({"src/service.py": structure})
        self.assertIn("src/service.py", rendered)
        self.assertIn("  class Service", rendered)
        self.assertIn("    def start(self, path: Path) -> str", rendered)

    def test_skeleton_preserves_constants_and_docstrings(self) -> None:
        skeleton = skeletonize_python(SAMPLE)

        self.assertIn("VALUE = 42", skeleton)
        self.assertIn('"""Start docs."""', skeleton)
        self.assertIn("def helper(value: int) -> bool:\n    ...", skeleton)
        self.assertNotIn("return value > 0", skeleton)
        self.assertNotIn("await cleanup()", skeleton)

    def test_syntax_error_falls_back_without_raising(self) -> None:
        invalid = "def broken(:\n    pass\n"

        structure = extract_python_structure(invalid)

        self.assertIsNotNone(structure.parse_error)
        self.assertEqual(skeletonize_python(invalid), invalid)


if __name__ == "__main__":
    unittest.main()
