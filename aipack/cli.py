from __future__ import annotations

from pathlib import Path

import click

from .builder import BundleBuilder
from .counter import estimate_tokens, format_token_count
from .scanner import FileScanner
from .security import SecretWarning, scan_for_secrets
from .tree import generate_tree


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output file (default: stdout). Multiple files if chunking.",
)
@click.option(
    "--exclude",
    "-e",
    multiple=True,
    help='Glob patterns to exclude (repeatable). E.g. --exclude "tests/*"',
)
@click.option(
    "--include",
    "-i",
    multiple=True,
    help="If set, ONLY include files matching these globs.",
)
@click.option(
    "--max-size",
    default="500kb",
    help="Max size per individual file. E.g. 100kb, 2mb. Default: 500kb",
)
@click.option(
    "--max-tokens",
    default=None,
    type=int,
    help="Abort with error if final bundle exceeds N tokens.",
)
@click.option(
    "--stats",
    is_flag=True,
    help="Dry-run: print stats table only, produce no output file.",
)
@click.option(
    "--no-tree",
    is_flag=True,
    help="Skip the [PROJECT STRUCTURE] section.",
)
@click.option(
    "--strip-comments",
    is_flag=True,
    help="Strip comment-only lines from source files (saves tokens).",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["plain", "xml", "md"]),
    default="plain",
    help="Output format: plain (default), xml (Claude-friendly), md (Markdown).",
)
@click.option(
    "--chunk-size",
    default=None,
    type=int,
    help="Split output into multiple files, each <= N tokens. E.g. --chunk-size 80000",
)
@click.option(
    "--diff",
    default=None,
    help="Include only files changed since this git ref. E.g. --diff HEAD~1",
)
def pack(
    path,
    output,
    exclude,
    include,
    max_size,
    max_tokens,
    stats,
    no_tree,
    strip_comments,
    fmt,
    chunk_size,
    diff,
):
    """
    Bundle source code into a single text file for LLM consumption.

    PATH is the root directory to scan (default: current directory).
    """
    root = Path(path).resolve()
    scanner = FileScanner(
        root=root,
        extra_exclude=list(exclude),
        include_only=list(include),
        max_file_size=max_size,
        diff_ref=diff,
    )
    files = scanner.scan()
    builder = BundleBuilder()
    files = builder.sort_files(files)
    tree = "" if no_tree else generate_tree(root, [file.abs_path for file in files])
    secret_warnings = _scan_file_contents(builder, files)

    if fmt == "plain":
        bundle = builder.build_plain(root, files, tree, strip_comments, secret_warnings)
    elif fmt == "xml":
        bundle = builder.build_xml(root, files, tree, strip_comments, secret_warnings)
    else:
        bundle = builder.build_md(root, files, tree, strip_comments, secret_warnings)

    token_count = estimate_tokens(bundle)
    if max_tokens is not None and token_count > max_tokens:
        raise click.ClickException(
            f"Bundle exceeds --max-tokens: {format_token_count(token_count)} > {format_token_count(max_tokens)}"
        )

    _emit_warnings(scanner.stats.warnings + builder.warnings)
    _emit_secret_warnings(secret_warnings)

    if stats:
        click.echo(
            f"Files in bundle: {len(files)} | Bundle size: {len(bundle.encode('utf-8'))} bytes | "
            f"Estimated tokens: {format_token_count(token_count)}",
            err=True,
        )
        return

    if chunk_size is not None:
        raise click.ClickException("--chunk-size is not implemented yet")

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(bundle, encoding="utf-8")
        click.echo(f"Wrote {output_path} ({format_token_count(token_count)} tokens)", err=True)
    else:
        click.echo(bundle, nl=False)


def _emit_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        click.echo(f"WARNING: {warning}", err=True)


def _scan_file_contents(builder: BundleBuilder, files) -> list[SecretWarning]:
    warnings: list[SecretWarning] = []
    for file in files:
        content = builder.read_file_content(file)
        found = scan_for_secrets(content, file.rel_path.as_posix())
        if found:
            file.security_risk = True
            file.security_warnings.extend(
                f"line {warning.line_number}: possible {warning.secret_type}"
                for warning in found
            )
            warnings.extend(found)
    return warnings


def _emit_secret_warnings(warnings: list[SecretWarning]) -> None:
    for warning in warnings:
        click.echo(
            f"WARNING: [secret] {warning.filepath} line {warning.line_number}: "
            f"possible {warning.secret_type} detected",
            err=True,
        )


if __name__ == "__main__":
    pack()
