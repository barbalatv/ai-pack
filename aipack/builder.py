from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import re
from typing import Any

from .scanner import ScannedFile


TOKEN_COUNT_PLACEHOLDER = "__TOKEN_COUNT__"

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
        self._content_cache: dict[Path, str] = {}

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
        cache_key = file.abs_path.resolve()
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]

        try:
            content = file.abs_path.read_text(encoding="utf-8")
            self._content_cache[cache_key] = content
            return content
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
                content = raw.decode(encoding)
                self._content_cache[cache_key] = content
                return content
            except (LookupError, UnicodeDecodeError):
                pass

        self.warnings.append(
            f"[read] Used replacement decoding for {file.rel_path.as_posix()}"
        )
        content = raw.decode("utf-8", errors="replace")
        self._content_cache[cache_key] = content
        return content

    def strip_comments(self, content: str, lang: str) -> str:
        """
        Strip lines where the entire line content is a comment.

        Inline comments and block comments are intentionally preserved.
        """
        hash_comment_langs = {"python", "bash", "yaml"}
        slash_comment_langs = {
            "javascript",
            "typescript",
            "jsx",
            "tsx",
            "rust",
            "go",
            "java",
            "cpp",
            "c",
            "csharp",
            "swift",
            "kotlin",
        }
        keep_lines: list[str] = []
        for line in content.splitlines():
            stripped = line.lstrip()
            if lang in hash_comment_langs and stripped.startswith("#"):
                if stripped.startswith("#!") or self._is_semantic_hash_comment(stripped):
                    keep_lines.append(line)
                continue
            if lang in slash_comment_langs and stripped.startswith("//"):
                continue
            keep_lines.append(line)

        result = "\n".join(keep_lines)
        if content.endswith("\n"):
            result += "\n"
        return result

    def build_plain(
        self,
        root: Path,
        files: list[ScannedFile],
        tree: str,
        strip_comments_flag: bool,
        warnings: list[Any],
    ) -> str:
        root = Path(root).resolve()
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
            token_count=TOKEN_COUNT_PLACEHOLDER,
        )
        return _replace_plain_token_placeholder(bundle)

    def build_xml(self, root, files, tree, strip_comments_flag, warnings) -> str:
        root = Path(root).resolve()
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        file_entries = []

        for file in files:
            content = self.read_file_content(file)
            lang = self._language_for(file.rel_path)
            if strip_comments_flag:
                content = self.strip_comments(content, lang)
            file_entries.append((file, content, lang))

        bundle = self._build_xml_with_token_count(
            root,
            files,
            tree,
            generated_at,
            file_entries,
            warnings,
            TOKEN_COUNT_PLACEHOLDER,
        )
        return _replace_xml_token_placeholder(bundle)

    def build_md(self, root, files, tree, strip_comments_flag, warnings) -> str:
        root = Path(root).resolve()
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        file_sections: list[str] = []

        for file in files:
            content = self.read_file_content(file)
            lang = self._language_for(file.rel_path)
            if strip_comments_flag:
                content = self.strip_comments(content, lang)
            line_count = len(content.splitlines())
            fence = self._fence_for(content)
            file_sections.append(
                "\n".join(
                    [
                        f"## {file.rel_path.as_posix()}",
                        f"*Size: {self._format_kb(file.size_bytes)} KB | Lines: {line_count} | Lang: {lang}*",
                        f"{fence}{lang}",
                        content.rstrip("\n"),
                        fence,
                        "",
                    ]
                )
            )

        bundle = self._build_md_with_token_count(
            root,
            files,
            tree,
            generated_at,
            file_sections,
            warnings,
            TOKEN_COUNT_PLACEHOLDER,
        )
        return _replace_md_token_placeholder(bundle)

    def split_into_chunks(
        self, bundle: str, chunk_size_tokens: int, output_base: str
    ) -> list[tuple[str, str]]:
        """
        Split a plain-text bundle into chunks without cutting file sections.
        """
        if chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens must be greater than zero")

        preamble, file_sections = self._split_plain_file_sections(bundle)
        if not file_sections:
            return [(self._chunk_filename(output_base, 1), bundle)]

        chunk_sections: list[list[str]] = []
        current: list[str] = []

        for section in file_sections:
            candidate = current + [section]
            candidate_text = self._render_chunk(1, 1, preamble, candidate)
            if current and _estimate_tokens(candidate_text) > chunk_size_tokens:
                chunk_sections.append(current)
                current = [section]
            else:
                current = candidate

            single_text = self._render_chunk(1, 1, preamble, current)
            if len(current) == 1 and _estimate_tokens(single_text) > chunk_size_tokens:
                raise ValueError(
                    "A single file section exceeds the requested chunk size; "
                    "increase --chunk-size or lower --max-size."
                )

        if current:
            chunk_sections.append(current)

        total = len(chunk_sections)
        return [
            (
                self._chunk_filename(output_base, index),
                self._render_chunk(index, total, preamble, sections),
            )
            for index, sections in enumerate(chunk_sections, start=1)
        ]

    def _build_plain_with_token_count(
        self,
        root: Path,
        files: list[ScannedFile],
        tree: str,
        generated_at: str,
        file_sections: list[str],
        token_count: str,
    ) -> str:
        sections = [
            "=" * 64,
            f"PROJECT BUNDLE: {root.name}",
            f"Generated: {generated_at} | Root: {root}",
            f"Files: {len(files)} | Estimated tokens: {token_count} (cl100k_base)",
            "=" * 64,
            "",
        ]
        if tree:
            sections.extend(["[PROJECT STRUCTURE]", tree, ""])
        sections.extend(file_sections)
        sections.extend(
            [
                "=" * 64,
                f"END OF BUNDLE | {len(files)} files | {token_count} tokens",
                "=" * 64,
                "",
            ]
        )
        return "\n".join(sections)

    def _split_plain_file_sections(self, bundle: str) -> tuple[str, list[str]]:
        pattern = re.compile(
            r"(?ms)^={64}\nFILE: .*?(?=^={64}\n(?:FILE: |END OF BUNDLE))"
        )
        matches = list(pattern.finditer(bundle))
        if not matches:
            return bundle, []
        preamble = bundle[: matches[0].start()].rstrip() + "\n\n"
        return preamble, [match.group(0).rstrip() + "\n" for match in matches]

    def _render_chunk(
        self, index: int, total: int, preamble: str, file_sections: list[str]
    ) -> str:
        body = "\n".join(section.rstrip() for section in file_sections)
        chunk = "\n".join(
            [
                "=" * 64,
                f"CHUNK {index} of {total}",
                "=" * 64,
                "",
                preamble.rstrip(),
                "",
                body.rstrip(),
                "",
                "=" * 64,
                f"END OF CHUNK {index} of {total} | {_format_token_count(_estimate_tokens(body))} body tokens",
                "=" * 64,
                "",
            ]
        )
        return chunk

    @staticmethod
    def _chunk_filename(output_base: str, index: int) -> str:
        base = Path(output_base)
        suffix = base.suffix or ".txt"
        stem = base.stem if base.suffix else base.name
        return str(base.with_name(f"{stem}.part{index:03d}{suffix}"))

    def _build_xml_with_token_count(
        self,
        root: Path,
        files: list[ScannedFile],
        tree: str,
        generated_at: str,
        file_entries: list[tuple[ScannedFile, str, str]],
        warnings: list[Any],
        token_count: str,
    ) -> str:
        lines = [
            (
                f'<project_bundle name="{escape(root.name, quote=True)}" '
                f'root="{escape(str(root), quote=True)}" '
                f'generated_at="{escape(generated_at, quote=True)}" '
                f'files="{len(files)}" estimated_tokens="{token_count}">'
            )
        ]
        if tree:
            lines.extend(
                [
                    "  <project_structure>",
                    escape(tree),
                    "  </project_structure>",
                ]
            )
        if warnings:
            lines.append("  <security_warnings>")
            for warning in warnings:
                lines.append(
                    f'    <security_warning path="{escape(warning.filepath, quote=True)}" '
                    f'line="{warning.line_number}" '
                    f'type="{escape(warning.secret_type, quote=True)}" />'
                )
            lines.append("  </security_warnings>")
        for file, content, lang in file_entries:
            lines.extend(
                [
                    f'  <file path="{escape(file.rel_path.as_posix(), quote=True)}" lang="{escape(lang, quote=True)}">',
                    "    <content>",
                    escape(content.rstrip("\n")),
                    "    </content>",
                    "  </file>",
                ]
            )
        lines.append("</project_bundle>")
        lines.append("")
        return "\n".join(lines)

    def _build_md_with_token_count(
        self,
        root: Path,
        files: list[ScannedFile],
        tree: str,
        generated_at: str,
        file_sections: list[str],
        warnings: list[Any],
        token_count: str,
    ) -> str:
        sections = [
            f"# Project Bundle: {root.name}",
            f"> Generated: {generated_at} | Root: `{root}` | Files: {len(files)} | {token_count} tokens",
            "",
        ]
        if tree:
            sections.extend(["## Project Structure", "```", tree, "```", ""])
        if warnings:
            sections.append("## Security Warnings")
            for warning in warnings:
                sections.append(
                    f"- `{warning.filepath}` line {warning.line_number}: possible {warning.secret_type} detected"
                )
            sections.append("")
        sections.extend(file_sections)
        sections.extend(
            [
                "---",
                f"End of bundle: {len(files)} files | {token_count} tokens",
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

    @staticmethod
    def _fence_for(content: str) -> str:
        longest = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("`"):
                longest = max(longest, len(stripped) - len(stripped.lstrip("`")))
        return "`" * max(3, longest + 1)

    @staticmethod
    def _is_semantic_hash_comment(stripped_line: str) -> bool:
        lowered = stripped_line.lower()
        semantic_prefixes = (
            "# type:",
            "# pyright:",
            "# mypy:",
            "# noqa",
            "# pylint:",
            "# ruff:",
            "# pragma:",
            "# fmt:",
        )
        return lowered.startswith(semantic_prefixes)


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


def _replace_xml_token_placeholder(bundle: str) -> str:
    token_count = _estimate_tokens(bundle)
    return bundle.replace(
        f'estimated_tokens="{TOKEN_COUNT_PLACEHOLDER}"',
        f'estimated_tokens="{_format_token_count(token_count)}"',
        1,
    )


def _replace_plain_token_placeholder(bundle: str) -> str:
    token_count = _estimate_tokens(bundle)
    formatted = _format_token_count(token_count)
    bundle = bundle.replace(
        f"Estimated tokens: {TOKEN_COUNT_PLACEHOLDER} (cl100k_base)",
        f"Estimated tokens: {formatted} (cl100k_base)",
        1,
    )
    return _replace_last(
        bundle,
        f" | {TOKEN_COUNT_PLACEHOLDER} tokens",
        f" | {formatted} tokens",
    )


def _replace_md_token_placeholder(bundle: str) -> str:
    token_count = _estimate_tokens(bundle)
    formatted = _format_token_count(token_count)
    bundle = bundle.replace(
        f" | {TOKEN_COUNT_PLACEHOLDER} tokens",
        f" | {formatted} tokens",
        1,
    )
    return _replace_last(
        bundle,
        f" | {TOKEN_COUNT_PLACEHOLDER} tokens",
        f" | {formatted} tokens",
    )


def _replace_last(text: str, old: str, new: str) -> str:
    before, separator, after = text.rpartition(old)
    if not separator:
        return text
    return before + new + after
