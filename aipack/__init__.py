"""ai-pack: bundle source code for LLM consumption."""

from .api import PackResult, pack_project

__all__ = ["pack_project", "PackResult"]
__version__ = "0.3.2"
