# ai-pack

Bundle a source-code directory into structured context for LLMs and coding agents.
`ai-pack` provides a Python CLI and library, with plain-text, XML, and Markdown output.

## Features

- Layered filtering: common generated/binary files, sensitive filenames, nested
  `.gitignore` rules, include/exclude globs, and a per-file size limit.
- Token estimates, explicit bundle budgets, and optional automatic shrinking with
  visible omission markers.
- Git diff selection, Python AST skeletons, and a Python class/function symbol map.
- Optional pattern-based secret redaction, comment stripping, and clipboard copying.
- Plain-text chunking that preserves whole file sections.

## Installation

Requires **Python 3.10 or newer**. Git is needed for cloning and `--diff`.
Install from this repository in a virtual environment:

```text
git clone https://github.com/barbalatv/ai-pack.git
cd ai-pack
python -m venv ../ai-pack-venv
```

Activate the environment using the command for your shell:

```bash
# Linux / macOS
source ../ai-pack-venv/bin/activate
```

```powershell
# Windows PowerShell
..\ai-pack-venv\Scripts\Activate.ps1
```

Then, from the repository root:

```text
python -m pip install .
ai-pack --help
```

For optional clipboard support, install the local extra:

```text
python -m pip install ".[clipboard]"
```

`--copy` also needs a working OS clipboard backend; installing the extra alone
does not guarantee one is available. A clipboard failure is reported without
preventing file output. These instructions install the checkout, not a registry release.

## Quick start

From the repository root, move to its parent and create a small sample directory
(use a fresh directory if `sample` already exists). These commands work in
PowerShell and POSIX shells with the environment activated:

```text
cd ..
python -c "from pathlib import Path; Path('sample').mkdir(); Path('sample/hello.py').write_text('print(123)\n', encoding='utf-8')"
ai-pack sample --no-config --lang en --output bundle.txt
```

`bundle.txt` contains project metadata, a file tree, and source sections, including:

```text
FILE: hello.py
Size: 0.0 KB | Lines: 1 | Lang: python
================================================================

print(123)
```

This is an excerpt; timestamps, metadata, and token counts depend on the input
and environment. Keep bundle output outside the directory being scanned to avoid
including a previous bundle in subsequent runs.

Without project configuration or presets, the **CLI defaults to `plain`**, while
the **Python API defaults to `xml`**. Without `--output`, the CLI writes to
`<format>/<directory-name>.<extension>` under the current working directory.
For example, `ai-pack sample` writes `plain/sample.txt`. `--stats` produces no file.

## Python API

```python
from aipack import pack_project

result = pack_project(
    "./sample",
    fmt="xml",             # API default; also supports "plain" and "md"
    exclude=["tests/*", "docs/*"],
    max_tokens=80_000,     # raises ValueError if exceeded without auto_shrink
)

print(result.bundle)           # structured bundle text
print(result.token_count)      # estimated tokens
print(result.files_included)
print(result.warnings)         # skipped files and encoding/configuration warnings
print(result.secret_warnings)  # potential-secret locations, not a safety guarantee
print(result.stats)            # filter counts
print(result.file_token_map)   # per-file token estimates
```

The API returns the bundle in memory; it does not write a file. Use
`redact=True`, `skeletons=True`, `symbol_map=True`, or `auto_shrink=True` as needed.
Configuration in `aipack.toml` or `[tool.aipack]` in `pyproject.toml` can change
defaults; explicit API arguments override it. `no_config=True` ignores it.
When printing Unicode bundles to a legacy-encoded terminal or redirected stream,
use Python's UTF-8 mode (`python -X utf8`).

## CLI examples

Replace `./my-project` with your source directory. Quote glob patterns so the
shell does not expand them before ai-pack receives them.

```bash
ai-pack ./my-project --format xml --output bundle.xml
ai-pack ./my-project --format xml --exclude "tests/*" --exclude "docs/*"
ai-pack ./my-project --include "*.py" --stats
ai-pack ./my-project --diff HEAD~1
ai-pack ./my-project --chunk-size 80000 --output out.txt
ai-pack ./my-project --format xml --redact --symbol-map
ai-pack ./my-project --preset review --format md
ai-pack ./my-project --max-tokens 80000 --auto-shrink --skeletons
ai-pack ./my-project --copy
```

- `--diff REF` selects files reported by `git diff --name-only REF`; it requires
  a valid Git checkout/reference and does not add untracked files.
- `--preset review` uses `HEAD~1` unless `--diff` overrides it. Presets and project
  configuration can change defaults; `--no-config` ignores project configuration.
- `--max-tokens` fails if the final bundle exceeds the estimate budget (CLI exit
  code 2). `--auto-shrink` requires that budget and may strip comments, skeletonize
  Python, or omit files with visible markers; it still fails if the bundle cannot fit.
- `--chunk-size` supports only plain text and cannot be combined with
  `--auto-shrink`. A single file section larger than the chunk budget causes an error.
- `--max-size` limits each input file (default `500kb`), not the total bundle.

See the [Russian usage guide](docs/USAGE.ru.md) for configuration, presets,
redaction, skeletons, and more CLI examples.

## Testing and development

From the repository root, with the environment activated:

```text
python -m unittest discover -s tests -q
python -m pip install build
python -m build --outdir ../ai-pack-dist
```

For development edits, `python -m pip install -e .` is also available.
The existing tests use `unittest`; no separate test framework is required.
Keep virtual environments and generated distributions out of Git.

[CI](.github/workflows/ci.yml) runs on pull requests and pushes to `main` for
Python **3.10, 3.11, 3.12, and 3.13**. It tests source installation, runs the unit
suite, builds an sdist and wheel, and smoke-tests each installed distribution in
a fresh environment outside the checkout. The clipboard extra is installed and
imported without accessing a real clipboard. CI does not publish packages.

## Limitations and security

- Redaction is **optional, heuristic, and pattern-based**. Filename exclusions
  and secret warnings do not guarantee that all secrets or confidential data are
  removed. ai-pack is not a full security scanner. Review the complete bundle
  before sending code or data to an external LLM provider.
- Token counts use `cl100k_base` when available, with a character-based fallback
  on tokenizer failure. Estimates may differ from the target model's tokenizer;
  budgets and chunk sizes are not guarantees about that model's context window.
- AST skeletons and symbol maps cover Python only. Shrinking deliberately removes
  context; review omission markers before relying on the result.
- Git failures are reported as warnings and can yield an empty selection. Check
  warnings and included-file counts when using `--diff` or the review preset.
