from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_tree(root: Path, included_files: list[Path]) -> str:
    """
    Generate a tree showing only files that made it into the bundle.

    Directories with no included files are omitted entirely.
    """
    root = Path(root).resolve()
    tree: dict[str, Any] = {}

    for file_path in included_files:
        rel_path = _relative_path(root, Path(file_path))
        parts = rel_path.parts
        if not parts:
            continue
        node = tree
        for directory in parts[:-1]:
            node = node.setdefault(directory, {})
        node[parts[-1]] = None

    return "\n".join(_render_node(tree, ""))


def _relative_path(root: Path, file_path: Path) -> Path:
    try:
        if file_path.is_absolute():
            return file_path.resolve().relative_to(root)
        return file_path
    except ValueError:
        return file_path


def _render_node(node: dict[str, Any], prefix: str) -> list[str]:
    lines: list[str] = []
    entries = sorted(node.items(), key=lambda item: (item[1] is None, item[0].lower()))

    for index, (name, child) in enumerate(entries):
        is_last = index == len(entries) - 1
        connector = "└── " if is_last else "├── "

        if child is None:
            lines.append(f"{prefix}{connector}{name}")
            continue

        lines.append(f"{prefix}{connector}{name}/")
        extension = "    " if is_last else "│   "
        lines.extend(_render_node(child, prefix + extension))

    return lines
