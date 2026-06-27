"""
Public Python API for agent integration.

Example usage:
    from aipack import pack_project

    result = pack_project("./my-project", fmt="xml", max_tokens=80_000)
    print(result.bundle)          # XML string ready for LLM
    print(result.token_count)     # int
    print(result.warnings)        # list[str]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .builder import BundleBuilder
from .counter import estimate_tokens
from .scanner import FileScanner
from .security import SecretWarning, scan_for_secrets
from .tree import generate_tree


@dataclass
class PackResult:
    """Structured result from pack_project()."""

    bundle: str
    token_count: int
    bundle_size_bytes: int
    files_included: int
    warnings: list[str] = field(default_factory=list)
    secret_warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def pack_project(
    path: str | Path = ".",
    *,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    max_size: str = "500kb",
    max_tokens: int | None = None,
    fmt: str = "xml",
    strip_comments: bool = False,
    diff_ref: str | None = None,
    no_tree: bool = False,
) -> PackResult:
    """
    Bundle a project directory into a single text string for LLM consumption.

    Args:
        path: Root directory to scan. Default: current directory.
        exclude: Glob patterns to exclude (e.g. ["tests/*", "docs/*"]).
        include: If set, ONLY include files matching these globs.
        max_size: Max size per file (e.g. "500kb", "2mb").
        max_tokens: Raise ValueError if bundle exceeds N tokens.
        fmt: Output format - "xml" (default), "plain", or "md".
        strip_comments: Strip comment-only lines from source files.
        diff_ref: Include only files changed since this git ref.
        no_tree: Skip the project structure section.

    Returns:
        PackResult with bundle string and metadata.

    Raises:
        ValueError: If max_tokens is set and the bundle exceeds it.
    """
    root = Path(path).resolve()

    scanner = FileScanner(
        root=root,
        extra_exclude=exclude or [],
        include_only=include or [],
        max_file_size=max_size,
        diff_ref=diff_ref,
    )
    files = scanner.scan()

    builder = BundleBuilder()
    files = builder.sort_files(files)
    tree = "" if no_tree else generate_tree(root, [file.abs_path for file in files])

    all_secret_warnings = _scan_file_contents(builder, files)

    if fmt == "xml":
        bundle = builder.build_xml(root, files, tree, strip_comments, all_secret_warnings)
    elif fmt == "md":
        bundle = builder.build_md(root, files, tree, strip_comments, all_secret_warnings)
    else:
        bundle = builder.build_plain(root, files, tree, strip_comments, all_secret_warnings)

    token_count = estimate_tokens(bundle)
    if max_tokens is not None and token_count > max_tokens:
        raise ValueError(f"Bundle exceeds max_tokens: {token_count:,} > {max_tokens:,}")

    scan_stats = scanner.stats
    secret_warning_strings = [
        f"{warning.filepath} line {warning.line_number}: possible {warning.secret_type}"
        for warning in all_secret_warnings
    ]

    return PackResult(
        bundle=bundle,
        token_count=token_count,
        bundle_size_bytes=len(bundle.encode("utf-8")),
        files_included=len(files),
        warnings=list(scan_stats.warnings) + list(builder.warnings),
        secret_warnings=secret_warning_strings,
        stats={
            "total_found": scan_stats.total_files_found,
            "filtered_hardcoded": scan_stats.filtered_hardcoded,
            "filtered_gitignore": scan_stats.filtered_gitignore,
            "filtered_size": scan_stats.filtered_size,
            "filtered_security": scan_stats.filtered_security_blacklist,
            "filtered_binary": scan_stats.filtered_binary,
            "filtered_diff": scan_stats.filtered_diff,
        },
    )


def _scan_file_contents(
    builder: BundleBuilder, files
) -> list[SecretWarning]:
    all_secret_warnings: list[SecretWarning] = []
    for file in files:
        content = builder.read_file_content(file)
        found = scan_for_secrets(content, file.rel_path.as_posix())
        if found:
            file.security_risk = True
            file.security_warnings.extend(
                f"line {warning.line_number}: possible {warning.secret_type}"
                for warning in found
            )
            all_secret_warnings.extend(found)
    return all_secret_warnings
