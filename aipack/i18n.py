"""Translations for human-facing CLI output only."""

from __future__ import annotations

import locale
import os


SUPPORTED_LANGS = ("en", "ru")

_CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "stats.title": "ai-pack - Bundle Preview",
        "stats.total_found": "Total files found",
        "stats.filtered_hardcoded": "Filtered (hardcoded rules)",
        "stats.filtered_gitignore": "Filtered (.gitignore)",
        "stats.filtered_size": "Filtered (size > max)",
        "stats.filtered_security": "Filtered (security blacklist)",
        "stats.filtered_user_exclude": "Filtered (user excludes)",
        "stats.filtered_user_include": "Filtered (include-only)",
        "stats.filtered_binary": "Filtered (binary)",
        "stats.filtered_diff": "Filtered (diff)",
        "stats.files_in_bundle": "Files in bundle",
        "stats.bundle_size": "Bundle size",
        "stats.estimated_tokens": "Estimated tokens (cl100k_base)",
        "stats.heaviest_files": "Heaviest files (by tokens)",
        "stats.skeleton_savings": "Skeleton savings (Python files)",
        "warn.prefix": "WARNING",
        "err.chunk_format": "--chunk-size is only supported with --format plain",
        "err.max_tokens": "Bundle exceeds --max-tokens: {actual} > {limit}",
        "err.auto_shrink_requires_max_tokens": "--auto-shrink requires --max-tokens to be set",
        "err.auto_shrink_chunk_conflict": "--auto-shrink cannot be combined with --chunk-size",
        "err.auto_shrink_insufficient": "Bundle still exceeds --max-tokens after auto-shrink ({actual} > {limit}). Try --exclude or a higher --max-tokens.",
        "err.clipboard_unavailable": "[copy] Clipboard unavailable ({reason}); bundle was NOT copied.",
        "info.copied": "Copied to clipboard (~{tokens} tokens).",
        "info.wrote_file": "Wrote {path} ({tokens} tokens)",
        "info.wrote_chunks": "Wrote {count} chunks using base {base}",
    },
    "ru": {
        "stats.title": "ai-pack - Предпросмотр бандла",
        "stats.total_found": "Всего файлов найдено",
        "stats.filtered_hardcoded": "Отфильтровано (жёсткие правила)",
        "stats.filtered_gitignore": "Отфильтровано (.gitignore)",
        "stats.filtered_size": "Отфильтровано (размер > максимума)",
        "stats.filtered_security": "Отфильтровано (чёрный список безопасности)",
        "stats.filtered_user_exclude": "Отфильтровано (исключения пользователя)",
        "stats.filtered_user_include": "Отфильтровано (include-only)",
        "stats.filtered_binary": "Отфильтровано (бинарные)",
        "stats.filtered_diff": "Отфильтровано (diff)",
        "stats.files_in_bundle": "Файлов в бандле",
        "stats.bundle_size": "Размер бандла",
        "stats.estimated_tokens": "Примерно токенов (cl100k_base)",
        "stats.heaviest_files": "Самые тяжёлые файлы (по токенам)",
        "stats.skeleton_savings": "Экономия от skeleton-режима (Python)",
        "warn.prefix": "ВНИМАНИЕ",
        "err.chunk_format": "--chunk-size поддерживается только с --format plain",
        "err.max_tokens": "Бандл превышает --max-tokens: {actual} > {limit}",
        "err.auto_shrink_requires_max_tokens": "--auto-shrink требует указания --max-tokens",
        "err.auto_shrink_chunk_conflict": "--auto-shrink нельзя сочетать с --chunk-size",
        "err.auto_shrink_insufficient": "Бандл всё ещё превышает --max-tokens после auto-shrink ({actual} > {limit}). Используйте --exclude или увеличьте --max-tokens.",
        "err.clipboard_unavailable": "[copy] Буфер обмена недоступен ({reason}); бандл НЕ скопирован.",
        "info.copied": "Скопировано в буфер обмена (~{tokens} токенов).",
        "info.wrote_file": "Записано {path} ({tokens} токенов)",
        "info.wrote_chunks": "Записано частей: {count}, базовое имя {base}",
    },
}


def resolve_lang(explicit: str | None = None) -> str:
    """Resolve explicit, environment, then system language with an English fallback."""
    if explicit in SUPPORTED_LANGS:
        return explicit
    env = os.environ.get("AIPACK_LANG")
    if env in SUPPORTED_LANGS:
        return env
    try:
        system_locale = locale.getdefaultlocale()[0] or ""
    except (ValueError, TypeError):
        system_locale = ""
    return "ru" if system_locale.lower().startswith("ru") else "en"


def t(key: str, lang: str = "en", **kwargs: object) -> str:
    """Translate a CLI string, falling back to English and then the raw key."""
    template = _CATALOG.get(lang, {}).get(key) or _CATALOG["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template
