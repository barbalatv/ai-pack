from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """
    Estimate token count using tiktoken cl100k_base.

    Falls back to a character-based heuristic when tiktoken is unavailable.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, len(text) // 4)


def format_token_count(n: int) -> str:
    """Return a human-readable token count string."""
    if n >= 1_000_000:
        return f"~{n / 1_000_000:.1f}M"
    return f"~{n:,}"
