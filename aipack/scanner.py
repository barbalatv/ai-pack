from __future__ import annotations

import fnmatch
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

try:
    import pathspec
except ImportError:  # pragma: no cover - exercised only when deps are absent
    pathspec = None


@dataclass
class ScannedFile:
    abs_path: Path
    rel_path: Path
    size_bytes: int
    is_binary: bool
    security_risk: bool
    security_warnings: list[str]


@dataclass
class ScanStats:
    total_files_found: int = 0
    filtered_hardcoded: int = 0
    filtered_security_blacklist: int = 0
    filtered_gitignore: int = 0
    filtered_user_exclude: int = 0
    filtered_user_include: int = 0
    filtered_size: int = 0
    filtered_binary: int = 0
    filtered_diff: int = 0
    filtered_errors: int = 0
    warnings: list[str] = field(default_factory=list)


class _SimplePathSpec:
    """Small gitignore-style fallback used only when pathspec is unavailable."""

    def __init__(self, patterns: Iterable[str]):
        self.patterns = [
            pattern.strip().replace("\\", "/")
            for pattern in patterns
            if pattern.strip() and not pattern.lstrip().startswith("#")
        ]

    def match_file(self, path: str) -> bool:
        path = FileScanner._strip_dot_slash(path.replace("\\", "/"))
        name = path.rsplit("/", 1)[-1]
        for pattern in self.patterns:
            negated = pattern.startswith("!")
            if negated:
                pattern = pattern[1:]
            matched = FileScanner._match_one(path, name, pattern)
            if matched and not negated:
                return True
        return False


class FileScanner:
    HARDCODED_EXCLUDES = [
        ".git/",
        ".svn/",
        ".hg/",
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        ".venv/",
        "venv/",
        "env/",
        ".env/",
        "virtualenv/",
        "*.egg-info/",
        "dist/",
        "build/",
        "node_modules/",
        ".next/",
        ".nuxt/",
        ".cache/",
        "target/",
        ".gradle/",
        "*.class",
        "*.jar",
        "*.war",
        ".idea/",
        ".vscode/",
        "*.iml",
        ".project",
        ".classpath",
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "poetry.lock",
        "Cargo.lock",
        "composer.lock",
        "Gemfile.lock",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.bmp",
        "*.tiff",
        "*.webp",
        "*.ico",
        "*.svg",
        "*.mp4",
        "*.mp3",
        "*.wav",
        "*.mov",
        "*.avi",
        "*.mkv",
        "*.pdf",
        "*.doc",
        "*.docx",
        "*.xls",
        "*.xlsx",
        "*.ppt",
        "*.pptx",
        "*.zip",
        "*.tar",
        "*.gz",
        "*.bz2",
        "*.rar",
        "*.7z",
        "*.xz",
        "*.exe",
        "*.dll",
        "*.so",
        "*.dylib",
        "*.bin",
        "*.o",
        "*.obj",
        "*.a",
        "*.lib",
        "*.out",
        "*.woff",
        "*.woff2",
        "*.ttf",
        "*.eot",
        "*.otf",
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        "*.mdb",
    ]

    SECURITY_BLACKLIST = [
        ".env",
        ".env.local",
        ".env.development",
        ".env.staging",
        ".env.production",
        "*.env",
        "*.pem",
        "*.key",
        "*.id_rsa",
        "id_rsa",
        "id_ed25519",
        "*.p12",
        "*.pfx",
        "*.cer",
        "*.crt",
        "secrets.yaml",
        "secrets.yml",
        "secrets.json",
        "secrets.toml",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials.json",
        "service-account*.json",
        "*.keystore",
    ]

    def __init__(
        self,
        root: Path,
        extra_exclude: list[str] | tuple[str, ...] | None,
        include_only: list[str] | tuple[str, ...] | None,
        max_file_size: int | str,
        diff_ref: str | None,
        progress_callback: Callable[[int], None] | None = None,
    ):
        self.root = Path(root).resolve()
        self.extra_exclude = [self._normalize_pattern(p) for p in (extra_exclude or [])]
        self.include_only = [self._normalize_pattern(p) for p in (include_only or [])]
        self.max_file_size = (
            self._parse_max_size(max_file_size)
            if isinstance(max_file_size, str)
            else max_file_size
        )
        self.diff_ref = diff_ref
        self.progress_callback = progress_callback
        self.gitignore_cache: dict[Path, object | None] = {}
        self.stats = ScanStats()

    def _load_gitignore(self, dir_path: Path) -> object | None:
        """Load .gitignore from a directory. Returns None if not found."""
        dir_path = Path(dir_path).resolve()
        if dir_path in self.gitignore_cache:
            return self.gitignore_cache[dir_path]

        gitignore_path = dir_path / ".gitignore"
        if not gitignore_path.is_file():
            self.gitignore_cache[dir_path] = None
            return None

        try:
            lines = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            self.stats.warnings.append(
                f"[scan] Could not read {self._display_path(gitignore_path)}: {exc}"
            )
            self.gitignore_cache[dir_path] = None
            return None

        if pathspec is not None:
            spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)
        else:
            spec = _SimplePathSpec(lines)
        self.gitignore_cache[dir_path] = spec
        return spec

    def _is_binary(self, path: Path) -> bool:
        """Heuristic: read first 8KB, check for null bytes."""
        try:
            with path.open("rb") as handle:
                return b"\0" in handle.read(8192)
        except OSError as exc:
            self.stats.warnings.append(
                f"[scan] Could not read {self._display_path(path)}: {exc}"
            )
            return True

    @staticmethod
    def _parse_max_size(size_str: str) -> int:
        """Parse '500kb', '2mb', '1gb' into bytes."""
        cleaned = size_str.strip().lower().replace(" ", "")
        units = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}
        for unit in ("gb", "mb", "kb", "b"):
            if cleaned.endswith(unit):
                value = cleaned[: -len(unit)]
                break
        else:
            value = cleaned
            unit = "b"

        try:
            return int(float(value) * units[unit])
        except ValueError as exc:
            raise ValueError(f"Invalid size value: {size_str!r}") from exc

    def _get_diff_files(self, diff_ref: str) -> set[Path]:
        """Run `git diff --name-only <ref>` and return absolute paths."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", diff_ref],
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            self.stats.warnings.append(f"[git] Could not run git diff: {exc}")
            return set()

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            self.stats.warnings.append(
                f"[git] git diff --name-only {diff_ref} failed: {message}"
            )
            return set()

        paths = set()
        for line in result.stdout.splitlines():
            rel = line.strip()
            if not rel:
                continue
            paths.add((self.root / rel).resolve())
        return paths

    def scan(self) -> list[ScannedFile]:
        """
        Walk the directory tree and return filtered file list.

        Uses os.walk(followlinks=False) to avoid symlink loops.
        """
        included: list[ScannedFile] = []
        diff_files = self._get_diff_files(self.diff_ref) if self.diff_ref else None

        for current_dir, dirnames, filenames in os.walk(self.root, followlinks=False):
            current_path = Path(current_dir)
            dirnames[:] = [
                dirname for dirname in dirnames if not self._should_prune_dir(current_path, dirname)
            ]

            for filename in filenames:
                abs_path = current_path / filename
                self.stats.total_files_found += 1
                if self.progress_callback is not None:
                    try:
                        self.progress_callback(self.stats.total_files_found)
                    except Exception:
                        pass
                if abs_path.is_symlink():
                    self.stats.filtered_errors += 1
                    self.stats.warnings.append(f"Skipped symlink: {filename}")
                    continue

                try:
                    rel_path = abs_path.relative_to(self.root)
                except ValueError:
                    continue
                rel_posix = rel_path.as_posix()

                if self._matches_patterns(rel_posix, self.HARDCODED_EXCLUDES):
                    self.stats.filtered_hardcoded += 1
                    continue

                if self._matches_patterns(rel_posix, self.SECURITY_BLACKLIST):
                    self.stats.filtered_security_blacklist += 1
                    self.stats.warnings.append(
                        f"[security] Skipped: {rel_posix} (matches security blacklist)"
                    )
                    continue

                if self._matches_gitignore(abs_path):
                    self.stats.filtered_gitignore += 1
                    continue

                if self._matches_patterns(rel_posix, self.extra_exclude):
                    self.stats.filtered_user_exclude += 1
                    continue

                if self.include_only and not self._matches_patterns(rel_posix, self.include_only):
                    self.stats.filtered_user_include += 1
                    continue

                try:
                    size_bytes = abs_path.stat().st_size
                except OSError as exc:
                    self.stats.filtered_errors += 1
                    self.stats.warnings.append(
                        f"[scan] Could not stat {self._display_path(abs_path)}: {exc}"
                    )
                    continue

                if size_bytes > self.max_file_size:
                    self.stats.filtered_size += 1
                    self.stats.warnings.append(
                        f"[scan] Skipped: {rel_posix} (size {size_bytes} > max {self.max_file_size})"
                    )
                    continue

                is_binary = self._is_binary(abs_path)
                if is_binary:
                    self.stats.filtered_binary += 1
                    continue

                if diff_files is not None and abs_path.resolve() not in diff_files:
                    self.stats.filtered_diff += 1
                    continue

                included.append(
                    ScannedFile(
                        abs_path=abs_path.resolve(),
                        rel_path=rel_path,
                        size_bytes=size_bytes,
                        is_binary=is_binary,
                        security_risk=False,
                        security_warnings=[],
                    )
                )

        return included

    def _should_prune_dir(self, current_path: Path, dirname: str) -> bool:
        rel_path = (current_path / dirname).relative_to(self.root).as_posix() + "/"
        if self._matches_patterns(rel_path, self.HARDCODED_EXCLUDES):
            self.stats.filtered_hardcoded += 1
            return True
        if self._matches_gitignore(current_path / dirname):
            self.stats.filtered_gitignore += 1
            return True
        return False

    def _matches_gitignore(self, path: Path) -> bool:
        specs: list[tuple[Path, object]] = []
        current = self.root
        try:
            rel_parts = path.relative_to(self.root).parts
        except ValueError:
            return False

        spec = self._load_gitignore(self.root)
        if spec is not None:
            specs.append((self.root, spec))

        for part in rel_parts[:-1]:
            current = current / part
            spec = self._load_gitignore(current)
            if spec is not None:
                specs.append((current, spec))

        for base_dir, spec in specs:
            rel_to_spec = path.relative_to(base_dir).as_posix()
            if spec.match_file(rel_to_spec):
                return True
        return False

    @classmethod
    def _matches_patterns(cls, rel_path: str, patterns: Iterable[str]) -> bool:
        rel_path = cls._strip_dot_slash(rel_path.replace("\\", "/"))
        name = rel_path.rstrip("/").rsplit("/", 1)[-1]
        return any(cls._match_one(rel_path, name, pattern) for pattern in patterns)

    @staticmethod
    def _match_one(rel_path: str, name: str, pattern: str) -> bool:
        pattern = FileScanner._normalize_pattern(pattern)
        rel_path = FileScanner._strip_dot_slash(rel_path.replace("\\", "/"))
        name = name.rstrip("/")

        if pattern.endswith("/"):
            directory = pattern.rstrip("/")
            is_directory_path = rel_path.endswith("/")
            return (is_directory_path and rel_path.rstrip("/") == directory) or rel_path.startswith(
                f"{directory}/"
            )

        if "/" not in pattern and fnmatch.fnmatch(name, pattern):
            return True

        return (
            fnmatch.fnmatch(rel_path, pattern)
            or fnmatch.fnmatch(f"./{rel_path}", pattern)
            or fnmatch.fnmatch(name, pattern)
        )

    @staticmethod
    def _normalize_pattern(pattern: str) -> str:
        return pattern.replace("\\", "/").strip()

    @staticmethod
    def _strip_dot_slash(path: str) -> str:
        while path.startswith("./"):
            path = path[2:]
        return path

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)
