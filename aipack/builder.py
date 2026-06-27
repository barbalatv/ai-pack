from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scanner import ScannedFile


LANG_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "css",
    ".md": "markdown",
    ".r": "r",
    ".m": "matlab",
    ".lua": "lua",
    ".vim": "vim",
    ".tf": "terraform",
}


PRIORITY_PATTERNS = [
    (["README.md", "README.rst", "README.txt"], 0),
    (
        [
            "main.py",
            "app.py",
            "__main__.py",
            "index.js",
            "index.ts",
            "server.py",
            "server.js",
            "manage.py",
            "cli.py",
        ],
        1,
    ),
    ([".yaml", ".yml", ".toml", ".ini", ".cfg", ".json"], 2),
    (["test_", "_test.", "spec.", ".test.", ".spec."], 4),
]


class BundleBuilder:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def sort_files(self, files: list[ScannedFile]) -> list[ScannedFile]:
        """Sort by priority, then path depth, then alphabetically."""
        return sorted(
            files,
            key=lambda file: (
                self._priority(file.rel_path),
                len(file.rel_path.parts),
                file.rel_path.as_posix().lower(),
            ),
        )

    def read_file_content(self, file: ScannedFile) -> str:
        """
        Read file with encoding detection.

        Try UTF-8 first, then chardet, then open with errors='replace'.
        Never raise on encoding errors.
        """
        try:
            return file.abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            pass
        except OSError as exc:
            self.warnings.append(f"[read] Could not read {file.rel_path.as_posix()}: {exc}")
            return ""

        try:
            raw = file.abs_path.read_bytes()
        except OSError as exc:
            self.warnings.append(f"[read] Could not read {file.rel_path.as_posix()}: {exc}")
            return ""

        encoding = None
        try:
            import chardet

            detected = chardet.detect(raw)
            if detected.get("confidence", 0) >= 0.5:
                encoding = detected.get("encoding")
        except ImportError:
            encoding = None

        if encoding:
            try:
                self.warnings.append(
                    f"[read] Used encoding fallback for {file.rel_path.as_posix()}: {encoding}"
                )
                return raw.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                pass

        self.warnings.append(
            f"[read] Used replacement decoding for {file.rel_path.as_posix()}"
        )
        return raw.decode("utf-8", errors="replace")

    def strip_comments(self, content: str, lang: str) -> str:
        return content

    def build_plain(
        self,
        root: Path,
        files: list[ScannedFile],
        tree: str,
        strip_comments_flag: bool,
        warnings: list[Any],
    ) -> str:
        root = Path(root).resolve()
        files = self.sort_files(files)
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        file_sections: list[str] = []

        for file in files:
            content = self.read_file_content(file)
            lang = self._language_for(file.rel_path)
            if strip_comments_flag:
                content = self.strip_comments(content, lang)
            line_count = len(content.splitlines())
            file_sections.append(
                "\n".join(
                    [
                        "=" * 64,
                        f"FILE: {file.rel_path.as_posix()}",
                        f"Size: {self._format_kb(file.size_bytes)} KB | Lines: {line_count} | Lang: {lang}",
                        "=" * 64,
                        "",
                        content.rstrip("\n"),
                        "",
                    ]
                )
            )

        bundle = self._build_plain_with_token_count(
            root=root,
            files=files,
            tree=tree,
            generated_at=generated_at,
            file_sections=file_sections,
            token_count=0,
        )
        token_count = _estimate_tokens(bundle)
        bundle = self._build_plain_with_token_count(
            root=root,
            files=files,
            tree=tree,
            generated_at=generated_at,
            file_sections=file_sections,
            token_count=token_count,
        )
        token_count = _estimate_tokens(bundle)
        return self._build_plain_with_token_count(
            root=root,
            files=files,
            tree=tree,
            generated_at=generated_at,
            file_sections=file_sections,
            token_count=token_count,
        )

    def build_xml(self, root, files, tree, strip_comments_flag, warnings) -> str:
        raise NotImplementedError("XML format is not implemented yet")

    def build_md(self, root, files, tree, strip_comments_flag, warnings) -> str:
        raise NotImplementedError("Markdown format is not implemented yet")

    def split_into_chunks(
        self, bundle: str, chunk_size_tokens: int, output_base: str
    ) -> list[tuple[str, str]]:
        raise NotImplementedError("Chunking is not implemented yet")

    def _build_plain_with_token_count(
        self,
        root: Path,
        files: list[ScannedFile],
        tree: str,
        generated_at: str,
        file_sections: list[str],
        token_count: int,
    ) -> str:
        sections = [
            "=" * 64,
            f"PROJECT BUNDLE: {root.name}",
            f"Generated: {generated_at} | Root: {root}",
            f"Files: {len(files)} | Estimated tokens: {_format_token_count(token_count)} (cl100k_base)",
            "=" * 64,
            "",
        ]
        if tree:
            sections.extend(["[PROJECT STRUCTURE]", tree, ""])
        sections.extend(file_sections)
        sections.extend(
            [
                "=" * 64,
                f"END OF BUNDLE | {len(files)} files | {_format_token_count(token_count)} tokens",
                "=" * 64,
                "",
            ]
        )
        return "\n".join(sections)

    def _priority(self, path: Path) -> int:
        rel = path.as_posix()
        name = path.name
        for patterns, priority in PRIORITY_PATTERNS:
            for pattern in patterns:
                if pattern.startswith(".") and name.endswith(pattern):
                    return priority
                if pattern in name or pattern == rel:
                    return priority
        return 3

    @staticmethod
    def _language_for(path: Path) -> str:
        return LANG_MAP.get(path.suffix.lower(), "text")

    @staticmethod
    def _format_kb(size_bytes: int) -> str:
        return f"{size_bytes / 1024:.1f}"


def _estimate_tokens(text: str) -> int:
    try:
        from .counter import estimate_tokens

        return estimate_tokens(text)
    except Exception:
        return max(1, len(text) // 4)


def _format_token_count(n: int) -> str:
    try:
        from .counter import format_token_count

        return format_token_count(n)
    except Exception:
        return f"~{n:,}"
