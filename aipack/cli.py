from __future__ import annotations

import subprocess
import sys
from html import escape
from pathlib import Path
from typing import Any, Callable

import click
from click.core import ParameterSource

from . import clipboard
from .builder import BundleBuilder
from .config import DEFAULTS, PRESETS, load_config_file, merge_settings
from .counter import estimate_tokens, format_token_count
from .i18n import resolve_lang, t
from .pyast import extract_python_structure, render_symbol_map, skeletonize_python
from .scanner import FileScanner, ScannedFile
from .security import SecretWarning, scan_files_for_secrets
from .shrink import auto_shrink as shrink_bundle
from .tree import generate_tree


_FMT_EXT = {"xml": "xml", "md": "md", "plain": "txt"}
_MERGE_KEYS = [
    "exclude",
    "include",
    "max_size",
    "max_tokens",
    "fmt",
    "strip_comments",
    "no_tree",
    "redact",
    "skeletons",
    "symbol_map",
    "lang",
]


class TokenBudgetExceeded(click.ClickException):
    exit_code = 2


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output file. Multiple files if chunking.")
@click.option("--exclude", "-e", multiple=True, help='Glob patterns to exclude (repeatable). E.g. --exclude "tests/*"')
@click.option("--include", "-i", multiple=True, help="If set, ONLY include files matching these globs.")
@click.option("--max-size", default="500kb", help="Max size per individual file. E.g. 100kb, 2mb. Default: 500kb")
@click.option("--max-tokens", default=None, type=int, help="Abort with error if final bundle exceeds N tokens.")
@click.option("--stats", is_flag=True, help="Dry-run: print stats table only, produce no output file.")
@click.option("--no-tree", is_flag=True, help="Skip the [PROJECT STRUCTURE] section.")
@click.option("--strip-comments", is_flag=True, help="Strip comment-only lines from source files (saves tokens).")
@click.option("--format", "fmt", type=click.Choice(["plain", "xml", "md"]), default="plain", help="Output format: plain (default), xml (Claude-friendly), md (Markdown).")
@click.option("--chunk-size", default=None, type=int, help="Split output into multiple files, each <= N tokens. E.g. --chunk-size 80000")
@click.option("--diff", default=None, help="Include only files changed since this git ref. E.g. --diff HEAD~1")
@click.option("--copy", "copy_bundle", "-c", is_flag=True, help="Copy the bundle to the clipboard.")
@click.option("--preset", type=click.Choice(["review", "refactor", "docs"]), default=None)
@click.option("--redact", is_flag=True, help="Replace detected secrets with [REDACTED].")
@click.option("--skeletons/--no-skeletons", default=None, help="Python files only: keep signatures/docstrings, strip bodies.")
@click.option("--symbol-map", is_flag=True, help="Prepend a Python symbol index (classes/functions).")
@click.option("--auto-shrink", is_flag=True, help="If over --max-tokens, shrink instead of failing.")
@click.option("--lang", type=click.Choice(["en", "ru"]), default=None, help="Language for terminal output.")
@click.option("--no-config", is_flag=True, help="Ignore aipack.toml / pyproject.toml [tool.aipack].")
def pack(
    path: str,
    output: str | None,
    exclude: tuple[str, ...],
    include: tuple[str, ...],
    max_size: str,
    max_tokens: int | None,
    stats: bool,
    no_tree: bool,
    strip_comments: bool,
    fmt: str,
    chunk_size: int | None,
    diff: str | None,
    copy_bundle: bool,
    preset: str | None,
    redact: bool,
    skeletons: bool | None,
    symbol_map: bool,
    auto_shrink: bool,
    lang: str | None,
    no_config: bool,
) -> None:
    """Bundle source code into a single text file for LLM consumption."""
    root = Path(path).resolve()
    ctx = click.get_current_context()
    local_values = {
        "exclude": list(exclude),
        "include": list(include),
        "max_size": max_size,
        "max_tokens": max_tokens,
        "fmt": fmt,
        "strip_comments": strip_comments,
        "no_tree": no_tree,
        "redact": redact,
        "skeletons": skeletons,
        "symbol_map": symbol_map,
        "lang": lang,
    }
    explicit_cli = {
        key: value
        for key, value in local_values.items()
        if ctx.get_parameter_source(key) == ParameterSource.COMMANDLINE
    }
    config_file = {} if no_config else load_config_file(root)
    config_warning = config_file.pop("_config_warning", None)
    preset_settings = dict(PRESETS.get(preset, {})) if preset else {}
    include_commit_log = bool(preset_settings.pop("include_commit_log", False))
    if (
        "diff_ref" in preset_settings
        and ctx.get_parameter_source("diff") != ParameterSource.COMMANDLINE
    ):
        diff = preset_settings.pop("diff_ref")
    settings = merge_settings(DEFAULTS, config_file, preset_settings, explicit_cli)
    lang = resolve_lang(settings.get("lang"))
    fmt = settings["fmt"]
    max_tokens = settings["max_tokens"]

    if chunk_size is not None and fmt != "plain":
        raise click.ClickException(t("err.chunk_format", lang))
    if auto_shrink and max_tokens is None:
        raise click.ClickException(t("err.auto_shrink_requires_max_tokens", lang))
    if auto_shrink and chunk_size is not None:
        raise click.ClickException(t("err.auto_shrink_chunk_conflict", lang))

    scanner = FileScanner(
        root=root,
        extra_exclude=list(settings["exclude"] or []),
        include_only=list(settings["include"] or []),
        max_file_size=settings["max_size"],
        diff_ref=diff,
    )
    files = _scan_with_progress(scanner, enabled=not stats)
    builder = BundleBuilder()
    files = builder.sort_files(files)
    tree = "" if settings["no_tree"] else generate_tree(root, [file.abs_path for file in files])
    secret_warnings = scan_files_for_secrets(builder, files)

    sections: list[tuple[str, str, str]] = []
    if include_commit_log and diff:
        commit_log = _recent_commit_log(root, diff, scanner.stats.warnings)
        if commit_log:
            sections.append(("RECENT COMMITS", "recent_commits", commit_log))
    if settings["symbol_map"]:
        symbol_content = _symbol_map_for_files(builder, files)
        if symbol_content:
            sections.append(("PYTHON SYMBOL MAP", "python_symbol_map", symbol_content))
    postprocess: Callable[[str], str] | None = None
    if sections:
        postprocess = lambda bundle: _prepend_sections(bundle, fmt, sections)

    bundle = _build_bundle(
        builder,
        root,
        files,
        tree,
        fmt,
        bool(settings["strip_comments"]),
        secret_warnings,
        skeletonize=bool(settings["skeletons"]),
        redact=bool(settings["redact"]),
    )
    if postprocess is not None:
        bundle = postprocess(bundle)

    token_count = estimate_tokens(bundle)
    shrink_report = None
    if max_tokens is not None and token_count > max_tokens:
        if not auto_shrink:
            raise TokenBudgetExceeded(
                t(
                    "err.max_tokens",
                    lang,
                    actual=format_token_count(token_count),
                    limit=format_token_count(max_tokens),
                )
            )
        try:
            bundle, shrink_report = shrink_bundle(
                builder,
                root,
                files,
                tree,
                fmt,
                secret_warnings,
                max_tokens,
                bool(settings["strip_comments"]),
                bool(settings["skeletons"]),
                redact=bool(settings["redact"]),
                postprocess=postprocess,
            )
        except ValueError as exc:
            raise TokenBudgetExceeded(
                t(
                    "err.auto_shrink_insufficient",
                    lang,
                    actual=format_token_count(token_count),
                    limit=format_token_count(max_tokens),
                )
            ) from exc
        token_count = estimate_tokens(bundle)

    warnings = list(scanner.stats.warnings) + list(builder.warnings)
    if config_warning:
        warnings.append(config_warning)
    if shrink_report is not None:
        if shrink_report.steps_applied:
            warnings.append(f"[auto-shrink] Applied: {', '.join(shrink_report.steps_applied)}")
        warnings.extend(
            f"[auto-shrink] Omitted: {file_path} ({reason})"
            for file_path, reason in shrink_report.omitted_files
        )

    file_token_map = {
        file.rel_path.as_posix(): estimate_tokens(builder.read_file_content(file))
        for file in files
    }
    skeleton_savings = _skeleton_savings(builder, files) if settings["skeletons"] else 0

    if copy_bundle:
        copied, reason = clipboard.copy_to_clipboard(bundle)
        if copied:
            click.echo(t("info.copied", lang, tokens=f"{token_count:,}"), err=True)
        else:
            click.echo(t("err.clipboard_unavailable", lang, reason=reason or "unknown error"), err=True)

    if stats:
        _print_stats(
            scanner=scanner,
            files_in_bundle=len(files),
            bundle_size=len(bundle.encode("utf-8")),
            token_count=token_count,
            file_token_map=file_token_map,
            skeleton_savings=skeleton_savings,
            lang=lang,
        )
        _emit_warnings(warnings, lang)
        _emit_secret_warnings(secret_warnings, lang)
        return

    _emit_warnings(warnings, lang)
    _emit_secret_warnings(secret_warnings, lang)

    if chunk_size is not None:
        try:
            output_base = output or f"{root.name}.{_FMT_EXT[fmt]}"
            chunks = builder.split_into_chunks(bundle, chunk_size, output_base)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        for index, (filename, content) in enumerate(chunks, start=1):
            if output:
                chunk_path = Path(filename)
            else:
                chunk_path = Path.cwd() / fmt / f"{root.name}_{index:03d}.{_FMT_EXT[fmt]}"
            chunk_path.parent.mkdir(parents=True, exist_ok=True)
            chunk_path.write_text(content, encoding="utf-8")
            if not output:
                click.echo(str(chunk_path), err=True)
        if output:
            click.echo(t("info.wrote_chunks", lang, count=len(chunks), base=output), err=True)
        return

    if output:
        out_path = Path(output)
    else:
        out_path = Path.cwd() / fmt / f"{root.name}.{_FMT_EXT[fmt]}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(bundle, encoding="utf-8")
    if output:
        click.echo(t("info.wrote_file", lang, path=out_path, tokens=format_token_count(token_count)), err=True)
    else:
        click.echo(str(out_path), err=True)


def _scan_with_progress(scanner: FileScanner, *, enabled: bool) -> list[ScannedFile]:
    if not enabled or not sys.stderr.isatty():
        return scanner.scan()
    try:
        from rich.console import Console
    except ImportError:
        return scanner.scan()

    console = Console(stderr=True)
    with console.status("Scanning files...") as status:
        scanner.progress_callback = lambda count: status.update(f"Scanning files ({count})")
        return scanner.scan()


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


def _recent_commit_log(root: Path, diff_ref: str, warnings: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"{diff_ref}..HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        warnings.append(f"[git] Could not run git log: {exc}")
        return ""
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        warnings.append(f"[git] git log --oneline {diff_ref}..HEAD failed: {message}")
        return ""
    return result.stdout.strip()


def _prepend_sections(bundle: str, fmt: str, sections: list[tuple[str, str, str]]) -> str:
    if fmt == "xml":
        opening, separator, remainder = bundle.partition("\n")
        if not separator:
            return bundle
        rendered = []
        for _title, tag, content in sections:
            rendered.extend([f"  <{tag}>", escape(content), f"  </{tag}>"])
        return "\n".join([opening, *rendered, remainder])
    if fmt == "md":
        header, separator, remainder = bundle.partition("\n\n")
        if not separator:
            return bundle
        rendered = []
        for title, _tag, content in sections:
            rendered.extend([f"## {title.title()}", "```", content, "```", ""])
        return f"{header}\n\n{'\n'.join(rendered)}\n{remainder}"
    header, separator, remainder = bundle.partition("\n\n")
    if not separator:
        return bundle
    rendered = []
    for title, _tag, content in sections:
        rendered.extend([f"[{title}]", content, ""])
    return f"{header}\n\n{'\n'.join(rendered)}\n{remainder}"


def _skeleton_savings(builder: BundleBuilder, files: list[ScannedFile]) -> int:
    original = 0
    skeletonized = 0
    for file in files:
        if file.rel_path.suffix.lower() != ".py":
            continue
        content = builder.read_file_content(file)
        original += estimate_tokens(content)
        skeletonized += estimate_tokens(skeletonize_python(content))
    return max(0, original - skeletonized)


def _emit_warnings(warnings: list[str], lang: str) -> None:
    prefix = t("warn.prefix", lang)
    for warning in warnings:
        click.echo(f"{prefix}: {warning}", err=True)


def _print_stats(
    scanner: FileScanner,
    files_in_bundle: int,
    bundle_size: int,
    token_count: int,
    file_token_map: dict[str, int],
    skeleton_savings: int,
    lang: str,
) -> None:
    rows = [
        (t("stats.total_found", lang), str(scanner.stats.total_files_found)),
        (t("stats.filtered_hardcoded", lang), str(scanner.stats.filtered_hardcoded)),
        (t("stats.filtered_gitignore", lang), str(scanner.stats.filtered_gitignore)),
        (t("stats.filtered_size", lang), str(scanner.stats.filtered_size)),
        (t("stats.filtered_security", lang), str(scanner.stats.filtered_security_blacklist)),
        (t("stats.filtered_user_exclude", lang), str(scanner.stats.filtered_user_exclude)),
        (t("stats.filtered_user_include", lang), str(scanner.stats.filtered_user_include)),
        (t("stats.filtered_binary", lang), str(scanner.stats.filtered_binary)),
        (t("stats.filtered_diff", lang), str(scanner.stats.filtered_diff)),
        (t("stats.files_in_bundle", lang), f"{files_in_bundle} OK"),
        (t("stats.bundle_size", lang), _format_bytes(bundle_size)),
        (t("stats.estimated_tokens", lang), format_token_count(token_count)),
    ]
    if skeleton_savings:
        rows.append((t("stats.skeleton_savings", lang), format_token_count(skeleton_savings)))
    heatmap = _render_heatmap(file_token_map)

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console(stderr=True)
        table = Table(title=t("stats.title", lang))
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        for metric, value in rows:
            table.add_row(metric, value)
        console.print(table)
        if heatmap:
            console.print(t("stats.heaviest_files", lang))
            console.print(heatmap)
    except ImportError:
        click.echo(t("stats.title", lang), err=True)
        for metric, value in rows:
            click.echo(f"{metric}: {value}", err=True)
        if heatmap:
            click.echo(t("stats.heaviest_files", lang), err=True)
            click.echo(heatmap, err=True)


def _render_heatmap(file_token_map: dict[str, int]) -> str:
    if not file_token_map:
        return ""
    heaviest = sorted(file_token_map.items(), key=lambda item: item[1], reverse=True)[:10]
    largest = heaviest[0][1]
    return "\n".join(
        f"{path}: {'█' * max(1, round(tokens / largest * 20))} {format_token_count(tokens)}"
        for path, tokens in heaviest
    )


def _format_bytes(size: int) -> str:
    if size >= 1024**2:
        return f"{size / 1024**2:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _emit_secret_warnings(warnings: list[SecretWarning], lang: str) -> None:
    prefix = t("warn.prefix", lang)
    for warning in warnings:
        click.echo(
            f"{prefix}: [secret] {warning.filepath} line {warning.line_number}: "
            f"possible {warning.secret_type} detected",
            err=True,
        )


if __name__ == "__main__":
    pack()
