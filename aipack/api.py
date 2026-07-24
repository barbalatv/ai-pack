"""Public Python API for agent integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Callable

from .builder import BundleBuilder, refresh_token_count
from .config import DEFAULTS, load_config_file, merge_settings
from .counter import estimate_tokens
from .pyast import extract_python_structure, render_symbol_map, skeletonize_python
from .scanner import FileScanner, ScannedFile
from .security import redact_content, scan_files_for_secrets
from .shrink import ShrinkReport, auto_shrink as shrink_bundle
from .tree import generate_tree


_UNSET = object()
_API_DEFAULTS = {**DEFAULTS, "fmt": "xml"}


@dataclass
class PackResult:
    """Structured result from :func:`pack_project`."""

    bundle: str
    token_count: int
    bundle_size_bytes: int
    files_included: int
    warnings: list[str] = field(default_factory=list)
    secret_warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    file_token_map: dict[str, int] = field(default_factory=dict)
    redacted_count: int = 0
    omitted_files: list[tuple[str, str]] = field(default_factory=list)


def pack_project(
    path: str | Path = ".",
    *,
    exclude: list[str] | None | object = _UNSET,
    include: list[str] | None | object = _UNSET,
    max_size: str | object = _UNSET,
    max_tokens: int | None | object = _UNSET,
    fmt: str | object = _UNSET,
    strip_comments: bool | object = _UNSET,
    diff_ref: str | None = None,
    no_tree: bool | object = _UNSET,
    redact: bool | object = _UNSET,
    skeletons: bool | object = _UNSET,
    symbol_map: bool | object = _UNSET,
    auto_shrink: bool = False,
    no_config: bool = False,
) -> PackResult:
    """Bundle a project directory into a structured LLM-ready text string.

    Configurable values use a sentinel internally so an explicit ``False`` or
    ``None`` from an API caller can override project configuration.
    """
    root = Path(path).resolve()
    explicit = {
        key: value
        for key, value in {
            "exclude": exclude,
            "include": include,
            "max_size": max_size,
            "max_tokens": max_tokens,
            "fmt": fmt,
            "strip_comments": strip_comments,
            "no_tree": no_tree,
            "redact": redact,
            "skeletons": skeletons,
            "symbol_map": symbol_map,
        }.items()
        if value is not _UNSET
    }
    config_file = {} if no_config else load_config_file(root)
    config_warning = config_file.pop("_config_warning", None)
    settings = merge_settings(_API_DEFAULTS, config_file, {}, explicit)

    if auto_shrink and settings["max_tokens"] is None:
        raise ValueError("--auto-shrink requires --max-tokens to be set")

    scanner = FileScanner(
        root=root,
        extra_exclude=list(settings["exclude"] or []),
        include_only=list(settings["include"] or []),
        max_file_size=settings["max_size"],
        diff_ref=diff_ref,
    )
    files = scanner.scan()
    builder = BundleBuilder()
    files = builder.sort_files(files)
    tree = "" if settings["no_tree"] else generate_tree(root, [file.abs_path for file in files])
    secret_warnings = scan_files_for_secrets(builder, files)

    symbol_map_content = _symbol_map_for_files(builder, files) if settings["symbol_map"] else ""
    postprocess: Callable[[str], str] | None = None
    if symbol_map_content:
        postprocess = lambda bundle: _prepend_symbol_map(bundle, settings["fmt"], symbol_map_content)

    bundle = _build_bundle(
        builder,
        root,
        files,
        tree,
        settings["fmt"],
        bool(settings["strip_comments"]),
        secret_warnings,
        skeletonize=bool(settings["skeletons"]),
        redact=bool(settings["redact"]),
    )
    if postprocess is not None:
        bundle = refresh_token_count(postprocess(bundle), settings["fmt"])

    shrink_report = ShrinkReport(final_token_count=estimate_tokens(bundle))
    if settings["max_tokens"] is not None and shrink_report.final_token_count > settings["max_tokens"]:
        if not auto_shrink:
            raise ValueError(
                f"Bundle exceeds max_tokens: {shrink_report.final_token_count:,} > {settings['max_tokens']:,}"
            )
        bundle, shrink_report = shrink_bundle(
            builder,
            root,
            files,
            tree,
            settings["fmt"],
            secret_warnings,
            settings["max_tokens"],
            bool(settings["strip_comments"]),
            bool(settings["skeletons"]),
            redact=bool(settings["redact"]),
            postprocess=postprocess,
        )

    token_count = estimate_tokens(bundle)
    effective_skeletons = bool(settings["skeletons"]) or "skeletons" in shrink_report.steps_applied
    omitted_paths = {path for path, _reason in shrink_report.omitted_files}
    redacted_count = _count_redactions(
        builder,
        files,
        skeletonize=effective_skeletons,
        omitted_paths=omitted_paths,
    ) if settings["redact"] else 0

    scan_stats = scanner.stats
    secret_warning_strings = [
        f"{warning.filepath} line {warning.line_number}: possible {warning.secret_type}"
        for warning in secret_warnings
    ]
    warnings = list(scan_stats.warnings) + list(builder.warnings)
    if config_warning:
        warnings.append(config_warning)
    if shrink_report.steps_applied:
        warnings.append(f"[auto-shrink] Applied: {', '.join(shrink_report.steps_applied)}")
    warnings.extend(
        f"[auto-shrink] Omitted: {path} ({reason})"
        for path, reason in shrink_report.omitted_files
    )

    return PackResult(
        bundle=bundle,
        token_count=token_count,
        bundle_size_bytes=len(bundle.encode("utf-8")),
        files_included=len(files),
        warnings=warnings,
        secret_warnings=secret_warning_strings,
        stats={
            "total_found": scan_stats.total_files_found,
            "filtered_hardcoded": scan_stats.filtered_hardcoded,
            "filtered_gitignore": scan_stats.filtered_gitignore,
            "filtered_size": scan_stats.filtered_size,
            "filtered_security": scan_stats.filtered_security_blacklist,
            "filtered_binary": scan_stats.filtered_binary,
            "filtered_diff": scan_stats.filtered_diff,
            "filtered_user_exclude": scan_stats.filtered_user_exclude,
            "filtered_user_include": scan_stats.filtered_user_include,
            "filtered_errors": scan_stats.filtered_errors,
        },
        file_token_map={
            file.rel_path.as_posix(): estimate_tokens(builder.read_file_content(file))
            for file in files
        },
        redacted_count=redacted_count,
        omitted_files=shrink_report.omitted_files,
    )


def _build_bundle(
    builder: BundleBuilder,
    root: Path,
    files: list[ScannedFile],
    tree: str,
    fmt: str,
    strip_comments: bool,
    secret_warnings: list[Any],
    *,
    skeletonize: bool,
    redact: bool,
) -> str:
    kwargs = {"skeletonize": skeletonize, "redact": redact}
    if fmt == "xml":
        return builder.build_xml(root, files, tree, strip_comments, secret_warnings, **kwargs)
    if fmt == "md":
        return builder.build_md(root, files, tree, strip_comments, secret_warnings, **kwargs)
    return builder.build_plain(root, files, tree, strip_comments, secret_warnings, **kwargs)


def _symbol_map_for_files(builder: BundleBuilder, files: list[ScannedFile]) -> str:
    entries = {
        file.rel_path.as_posix(): extract_python_structure(builder.read_file_content(file))
        for file in files
        if file.rel_path.suffix.lower() == ".py"
    }
    return render_symbol_map(entries)


def _prepend_symbol_map(bundle: str, fmt: str, content: str) -> str:
    if fmt == "xml":
        opening, separator, remainder = bundle.partition("\n")
        if not separator:
            return bundle
        return "\n".join(
            [
                opening,
                "  <python_symbol_map>",
                escape(content),
                "  </python_symbol_map>",
                remainder,
            ]
        )
    if fmt == "md":
        header, separator, remainder = bundle.partition("\n\n")
        if not separator:
            return bundle
        return f"{header}\n\n## Python Symbol Map\n```\n{content}\n```\n\n{remainder}"
    header, separator, remainder = bundle.partition("\n\n")
    if not separator:
        return bundle
    return f"{header}\n\n[PYTHON SYMBOL MAP]\n{content}\n\n{remainder}"


def _count_redactions(
    builder: BundleBuilder,
    files: list[ScannedFile],
    *,
    skeletonize: bool,
    omitted_paths: set[str],
) -> int:
    total = 0
    for file in files:
        if file.rel_path.as_posix() in omitted_paths:
            continue
        content = builder.read_file_content(file)
        if skeletonize and file.rel_path.suffix.lower() == ".py":
            content = skeletonize_python(content)
        _, count = redact_content(content)
        total += count
    return total
