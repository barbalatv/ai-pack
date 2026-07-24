"""Best-effort clipboard support kept separate from the core package."""

from __future__ import annotations


def copy_to_clipboard(text: str) -> tuple[bool, str | None]:
    """Copy text to the system clipboard without allowing failures to escape."""
    try:
        import pyperclip
    except ImportError:
        return False, "pyperclip not installed (pip install ai-pack[clipboard])"

    try:
        pyperclip.copy(text)
    except Exception as exc:  # pyperclip backends vary by platform.
        return False, str(exc)
    return True, None
