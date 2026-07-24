"""Python-only structural helpers used by skeleton and symbol-map modes."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class SymbolEntry:
    kind: str
    name: str
    signature: str
    docstring: str | None
    lineno: int
    children: list["SymbolEntry"] = field(default_factory=list)


@dataclass
class ModuleStructure:
    imports: list[str]
    symbols: list[SymbolEntry]
    parse_error: str | None = None


def extract_python_structure(source: str) -> ModuleStructure:
    """Extract imports, top-level symbols, and direct class methods.

    Structural extraction is deliberately best-effort. A malformed Python file
    remains bundleable; its parsing failure is reported to callers instead of
    propagating an exception.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ModuleStructure([], [], parse_error=str(exc))

    imports: list[str] = []
    symbols: list[SymbolEntry] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.unparse(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_symbol_from_callable(node))
        elif isinstance(node, ast.ClassDef):
            children = [
                _symbol_from_callable(child)
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            symbols.append(
                SymbolEntry(
                    kind="class",
                    name=node.name,
                    signature=_class_signature(node),
                    docstring=ast.get_docstring(node),
                    lineno=node.lineno,
                    children=children,
                )
            )

    return ModuleStructure(imports, symbols)


def skeletonize_python(source: str) -> str:
    """Replace Python callable bodies with docstrings (when present) and ``...``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    transformed = _SkeletonTransformer().visit(tree)
    ast.fix_missing_locations(transformed)
    return ast.unparse(transformed) + "\n"


def render_symbol_map(entries: dict[str, ModuleStructure]) -> str:
    """Render a compact, deterministic map of imports, classes, and functions."""
    blocks: list[str] = []
    for path in sorted(entries):
        structure = entries[path]
        if structure.parse_error or not (structure.imports or structure.symbols):
            continue
        lines = [path]
        lines.extend(f"  {statement}" for statement in structure.imports)
        for symbol in structure.symbols:
            lines.append(f"  {symbol.signature}")
            lines.extend(f"    {child.signature}" for child in symbol.children)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _symbol_from_callable(node: ast.FunctionDef | ast.AsyncFunctionDef) -> SymbolEntry:
    kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
    prefix = "async def" if kind == "async_function" else "def"
    signature = f"{prefix} {node.name}({ast.unparse(node.args)})"
    if node.returns is not None:
        signature += f" -> {ast.unparse(node.returns)}"
    return SymbolEntry(
        kind=kind,
        name=node.name,
        signature=signature,
        docstring=ast.get_docstring(node),
        lineno=node.lineno,
    )


def _class_signature(node: ast.ClassDef) -> str:
    bases = [ast.unparse(base) for base in node.bases]
    bases.extend(ast.unparse(keyword) for keyword in node.keywords)
    suffix = f"({', '.join(bases)})" if bases else ""
    return f"class {node.name}{suffix}"


class _SkeletonTransformer(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._skeletonize_callable(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return self._skeletonize_callable(node)

    @staticmethod
    def _skeletonize_callable(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        docstring_node = _docstring_node(node)
        ellipsis = ast.copy_location(ast.Expr(value=ast.Constant(value=Ellipsis)), node)
        node.body = [docstring_node, ellipsis] if docstring_node is not None else [ellipsis]
        return node


def _docstring_node(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Expr | None:
    if not node.body:
        return None
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first
    return None
