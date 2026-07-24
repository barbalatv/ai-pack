"""Deterministic, visible bundle shrinking for token-constrained workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .counter import estimate_tokens

if TYPE_CHECKING:
    from .builder import BundleBuilder
    from .scanner import ScannedFile


@dataclass
class ShrinkReport:
    steps_applied: list[str] = field(default_factory=list)
    omitted_files: list[tuple[str, str]] = field(default_factory=list)
    final_token_count: int = 0


def auto_shrink(
    builder: "BundleBuilder",
    root: Path,
    files: list["ScannedFile"],
    tree: str,
    fmt: str,
    secret_warnings: list[Any],
    max_tokens: int,
    strip_comments_already: bool,
    skeletons_already: bool,
    *,
    redact: bool = False,
    postprocess: Callable[[str], str] | None = None,
) -> tuple[str, ShrinkReport]:
    """Shrink a bundle in a fixed order while preserving visible omissions."""
    strip_comments = strip_comments_already
    skeletons = skeletons_already
    omitted: dict[Path, str] = {}
    report = ShrinkReport()
    rebuilds = 0
    max_rebuilds = len(files) + 4

    def rebuild() -> str:
        nonlocal rebuilds
        if rebuilds >= max_rebuilds:
            raise ValueError("Auto-shrink reached its defensive rebuild limit")
        rebuilds += 1
        built = _build_bundle(
            builder,
            root,
            files,
            tree,
            fmt,
            secret_warnings,
            strip_comments,
            skeletons,
            redact,
            omitted,
        )
        return postprocess(built) if postprocess is not None else built

    bundle = rebuild()
    if _fits(bundle, max_tokens, report):
        return bundle, report

    if not strip_comments:
        strip_comments = True
        report.steps_applied.append("strip_comments")
        bundle = rebuild()
        if _fits(bundle, max_tokens, report):
            return bundle, report

    if not skeletons:
        skeletons = True
        report.steps_applied.append("skeletons")
        bundle = rebuild()
        if _fits(bundle, max_tokens, report):
            return bundle, report

    test_files = sorted(
        (file for file in files if builder._priority(file.rel_path) == 4),
        key=lambda file: file.size_bytes,
        reverse=True,
    )
    for file in test_files:
        omitted[file.abs_path] = "auto-shrink"
        report.omitted_files.append((file.rel_path.as_posix(), "auto-shrink"))
        if "omit_tests" not in report.steps_applied:
            report.steps_applied.append("omit_tests")
        bundle = rebuild()
        if _fits(bundle, max_tokens, report):
            return bundle, report

    remaining_files = sorted(
        (
            file
            for file in files
            if file.abs_path not in omitted and builder._priority(file.rel_path) >= 2
        ),
        key=lambda file: file.size_bytes,
        reverse=True,
    )
    for file in remaining_files:
        omitted[file.abs_path] = "auto-shrink"
        report.omitted_files.append((file.rel_path.as_posix(), "auto-shrink"))
        if "omit_lower_priority" not in report.steps_applied:
            report.steps_applied.append("omit_lower_priority")
        bundle = rebuild()
        if _fits(bundle, max_tokens, report):
            return bundle, report

    report.final_token_count = estimate_tokens(bundle)
    raise ValueError("Bundle still exceeds max_tokens after auto-shrink")


def _fits(bundle: str, max_tokens: int, report: ShrinkReport) -> bool:
    report.final_token_count = estimate_tokens(bundle)
    return report.final_token_count <= max_tokens


def _build_bundle(
    builder: "BundleBuilder",
    root: Path,
    files: list["ScannedFile"],
    tree: str,
    fmt: str,
    secret_warnings: list[Any],
    strip_comments: bool,
    skeletons: bool,
    redact: bool,
    omitted: dict[Path, str],
) -> str:
    kwargs = {
        "skeletonize": skeletons,
        "redact": redact,
        "omitted": omitted,
    }
    if fmt == "xml":
        return builder.build_xml(root, files, tree, strip_comments, secret_warnings, **kwargs)
    if fmt == "md":
        return builder.build_md(root, files, tree, strip_comments, secret_warnings, **kwargs)
    return builder.build_plain(root, files, tree, strip_comments, secret_warnings, **kwargs)
