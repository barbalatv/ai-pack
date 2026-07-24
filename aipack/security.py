from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .builder import BundleBuilder
    from .scanner import ScannedFile


@dataclass
class SecretWarning:
    filepath: str
    line_number: int
    secret_type: str
    snippet: str
    redact_group: int = 0


SECRET_PATTERNS = [
    (
        re.compile(
            r"(?i)(api[_-]?key|apikey|access[_-]?token|secret[_-]?key)\s*[=:]\s*[\"']?([A-Za-z0-9_\-]{20,})"
        ),
        "API Key",
        2,
    ),
    (
        re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*[\"']([^\"']{6,})[\"']"),
        "Hardcoded Password",
        2,
    ),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google API Key", 0),
    (re.compile(r"sk-[A-Za-z0-9]{48}"), "OpenAI API Key", 0),
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{90,}"), "Anthropic API Key", 0),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"), "GitHub Token", 0),
    (
        re.compile(r"(mongodb(\+srv)?|postgresql|mysql|redis)://[^\s\"'<>]+"),
        "Database Connection String",
        0,
    ),
    (
        re.compile(r"(?i)(Authorization:\s*Bearer\s+)([A-Za-z0-9\-_\.]{20,})"),
        "Bearer Token",
        2,
    ),
]

PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    r".*?"
    r"-----END (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    re.DOTALL,
)


def scan_for_secrets(content: str, filepath: str) -> list[SecretWarning]:
    """Scan file content for possible secrets without changing it."""
    warnings: list[SecretWarning] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for pattern, label, redact_group in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                warnings.append(
                    SecretWarning(
                        filepath=filepath,
                        line_number=line_number,
                        secret_type=label,
                        snippet=_redact_snippet(line, match),
                        redact_group=redact_group,
                    )
                )

    for match in PRIVATE_KEY_BLOCK.finditer(content):
        line_number = content.count("\n", 0, match.start()) + 1
        warnings.append(
            SecretWarning(
                filepath=filepath,
                line_number=line_number,
                secret_type="Private Key Block",
                snippet="[REDACTED PRIVATE KEY BLOCK]",
            )
        )
    return warnings


def redact_content(content: str) -> tuple[str, int]:
    """Replace detected secret values with a stable redaction marker.

    The function intentionally scans the supplied content itself, rather than
    reusing warning spans. This keeps it safe after transformations such as
    Python skeletonization have changed the text and line positions.
    """
    replacements = 0

    def redact_private_key(match: re.Match[str]) -> str:
        nonlocal replacements
        replacements += 1
        lines = match.group(0).splitlines()
        if len(lines) >= 2:
            return f"{lines[0]}\n[REDACTED]\n{lines[-1]}"
        return "[REDACTED]"

    redacted = PRIVATE_KEY_BLOCK.sub(redact_private_key, content)

    for pattern, _label, redact_group in SECRET_PATTERNS:
        def redact_match(match: re.Match[str], group: int = redact_group) -> str:
            nonlocal replacements
            if group == 0:
                replacements += 1
                return "[REDACTED]"
            start, end = match.span(group)
            if start < 0 or end < start:
                return match.group(0)
            replacements += 1
            whole = match.group(0)
            relative_start = start - match.start()
            relative_end = end - match.start()
            return f"{whole[:relative_start]}[REDACTED]{whole[relative_end:]}"

        redacted = pattern.sub(redact_match, redacted)

    return redacted, replacements


def scan_files_for_secrets(
    builder: "BundleBuilder", files: list["ScannedFile"]
) -> list[SecretWarning]:
    """Scan included file contents for secrets and annotate file metadata."""
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


def _redact_snippet(line: str, match: re.Match[str]) -> str:
    clean = line.strip()
    offset = max(0, match.start() - (len(line) - len(line.lstrip())))
    visible_match = clean[offset : offset + 12]
    snippet = f"{clean[:offset]}{visible_match}...[REDACTED]"
    return snippet[:60]
