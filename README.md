# ai-pack

Bundle source code into a single structured file for LLM consumption.

`ai-pack` walks a project directory, applies layered filtering, and emits a
context-friendly bundle in plain text, XML, or Markdown.

## Python API

```python
from aipack import pack_project

result = pack_project(
    "./my-project",
    fmt="xml",             # "xml" (default), "plain", or "md"
    exclude=["tests/*", "docs/*"],
    max_tokens=80_000,     # raises ValueError if exceeded
)

print(result.bundle)           # str - ready to pass to an LLM
print(result.token_count)      # int - estimated tokens (cl100k_base)
print(result.files_included)   # int
print(result.warnings)         # list[str] - skipped files, encoding fallbacks
print(result.secret_warnings)  # list[str] - potential secrets found in content
print(result.stats)            # dict - per-filter counts, incl. user exclusions
print(result.file_token_map)   # dict[str, int] - per-file token weight
```

## CLI

```bash
pip install ai-pack

ai-pack ./my-project --format xml --output bundle.xml
ai-pack ./my-project --format xml --exclude "tests/*" --exclude "docs/*"
ai-pack ./my-project --stats                  # dry-run: print filter counts only
ai-pack ./my-project --diff HEAD~1            # only files changed since last commit
ai-pack ./my-project --chunk-size 80000 -o out.txt  # split into chunked files
ai-pack ./my-project --format xml --redact --symbol-map
ai-pack ./my-project --preset review --format md
ai-pack ./my-project --max-tokens 80000 --auto-shrink --skeletons
ai-pack ./my-project --copy                   # requires: pip install "ai-pack[clipboard]"
```

See [the Russian usage guide](docs/USAGE.ru.md) for the full CLI reference,
project configuration, presets, redaction, skeletons, and auto-shrink behavior.
