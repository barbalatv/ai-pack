from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SecretWarning:
    filepath: str
    line_number: int
    secret_type: str
    snippet: str


SECRET_PATTERNS = [
    (
        re.compile(
            r"(?i)(api[_-]?key|apikey|access[_-]?token|secret[_-]?key)\s*[=:]\s*[\"']?([A-Za-z0-9_\-]{20,})"
        ),
        "API Key",
    ),
    (
        re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*[\"']([^\"']{6,})[\"']"),
        "Hardcoded Password",
    ),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google API Key"),
    (re.compile(r"sk-[A-Za-z0-9]{48}"), "OpenAI API Key"),
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{90,}"), "Anthropic API Key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"), "GitHub Token"),
    (
        re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "Private Key Block",
    ),
    (
        re.compile(r"(mongodb(\+srv)?|postgresql|mysql|redis)://[^\s\"'<>]+"),
        "Database Connection String",
    ),
    (
        re.compile(r"(?i)Authorization:\s*Bearer\s+[A-Za-z0-9\-_\.]{20,}"),
        "Bearer Token",
    ),
]


def scan_for_secrets(content: str, filepath: str) -> list[SecretWarning]:
    """Scan file content line by line for secret patterns."""
    warnings: list[SecretWarning] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for pattern, label in SECRET_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            warnings.append(
                SecretWarning(
                    filepath=filepath,
                    line_number=line_number,
                    secret_type=label,
                    snippet=_redact_snippet(line, match),
                )
            )
    return warnings


def _redact_snippet(line: str, match: re.Match[str]) -> str:
    clean = line.strip()
    offset = max(0, match.start() - (len(line) - len(line.lstrip())))
    visible_match = clean[offset : offset + 12]
    snippet = f"{clean[:offset]}{visible_match}...[REDACTED]"
    return snippet[:60]
