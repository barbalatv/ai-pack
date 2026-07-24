"""Project configuration and named CLI presets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 uses the optional dependency.
    import tomli as tomllib


PRESETS: dict[str, dict[str, Any]] = {
    "review": {
        "diff_ref": "HEAD~1",
        "include_commit_log": True,
    },
    "refactor": {
        "exclude": ["tests/*", "docs/*", "*.md"],
    },
    "docs": {
        "include": ["*.md", "*.py"],
        "skeletons": True,
    },
}

CONFIG_KEYS = {
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
}

DEFAULTS: dict[str, Any] = {
    "exclude": [],
    "include": [],
    "max_size": "500kb",
    "max_tokens": None,
    "fmt": "plain",
    "strip_comments": False,
    "no_tree": False,
    "redact": False,
    "skeletons": False,
    "symbol_map": False,
    "lang": None,
}


def load_config_file(root: Path) -> dict[str, Any]:
    """Load ``[tool.aipack]`` from the preferred project configuration file."""
    root = Path(root)
    aipack_path = root / "aipack.toml"
    pyproject_path = root / "pyproject.toml"
    aipack_exists = aipack_path.is_file()
    pyproject_exists = pyproject_path.is_file()

    if not aipack_exists and not pyproject_exists:
        return {}

    config_path = aipack_path if aipack_exists else pyproject_path
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"_config_warning": f"[config] Could not read {config_path.name}: {exc}"}

    tool = parsed.get("tool", {})
    section = tool.get("aipack", {}) if isinstance(tool, dict) else {}
    if not isinstance(section, dict):
        section = {}

    result = {key: value for key, value in section.items() if key in CONFIG_KEYS}
    if aipack_exists and pyproject_exists:
        result["_config_warning"] = (
            "[config] Both aipack.toml and pyproject.toml were found; using aipack.toml"
        )
    return result


def merge_settings(
    defaults: dict[str, Any],
    config_file: dict[str, Any],
    preset: dict[str, Any],
    explicit_cli: dict[str, Any],
) -> dict[str, Any]:
    """Merge settings with precedence: defaults < config < preset < explicit."""
    merged = dict(defaults)
    merged.update({key: value for key, value in config_file.items() if key in CONFIG_KEYS})
    merged.update({key: value for key, value in preset.items() if key in CONFIG_KEYS})
    merged.update({key: value for key, value in explicit_cli.items() if key in CONFIG_KEYS})
    return merged
