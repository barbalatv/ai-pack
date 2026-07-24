# Использование ai-pack

`ai-pack` собирает исходники проекта в один plain/XML/Markdown-бандл для передачи LLM или агенту. По умолчанию скрытые каталоги сборки, бинарные файлы, файлы из `.gitignore` и известные секретные файлы не попадают в результат.

## Установка

```bash
pip install ai-pack
```

Для флага `--copy` установите дополнительную зависимость:

```bash
pip install "ai-pack[clipboard]"
```

В режиме editable из репозитория проекта:

```bash
python -m pip install -e .
```

## Быстрый старт

```bash
ai-pack . --format xml
ai-pack "C:\Projects\my-app" --format md
ai-pack . --format plain --output bundle.txt
```

Без `--output` файл создаётся в текущем каталоге запуска:

| Формат | Путь по умолчанию |
| --- | --- |
| `xml` | `./xml/<имя-проекта>.xml` |
| `md` | `./md/<имя-проекта>.md` |
| `plain` | `./plain/<имя-проекта>.txt` |

## Python API

```python
from aipack import pack_project

result = pack_project(
    "./my-project",
    fmt="xml",
    exclude=["tests/*"],
    redact=True,
    skeletons=True,
    symbol_map=True,
    max_tokens=80_000,
    auto_shrink=True,
)

print(result.bundle)
print(result.token_count)
print(result.redacted_count)
print(result.omitted_files)
```

`PackResult` также содержит число файлов, предупреждения, найденные потенциальные секреты, статистику сканирования и `file_token_map` с оценкой веса каждого файла.

## Флаги CLI

| Флаг | Назначение | Пример |
| --- | --- | --- |
| `PATH` | Корень проекта, по умолчанию текущая папка | `ai-pack ./app` |
| `-o`, `--output` | Явный путь выходного файла | `-o out.xml` |
| `-e`, `--exclude` | Исключает glob; повторяется | `-e "tests/*" -e "docs/*"` |
| `-i`, `--include` | Оставляет только совпадающие glob | `-i "*.py"` |
| `--max-size` | Максимальный размер одного файла | `--max-size 200kb` |
| `--max-tokens` | Лимит токенов финального бандла | `--max-tokens 80000` |
| `--stats` | Печатает статистику без выходного файла | `--stats` |
| `--no-tree` | Не добавляет дерево проекта | `--no-tree` |
| `--strip-comments` | Удаляет строки, состоящие только из комментариев | `--strip-comments` |
| `--format` | `plain`, `xml` или `md` | `--format xml` |
| `--chunk-size` | Делит plain-бандл на части | `--format plain --chunk-size 80000` |
| `--diff` | Оставляет файлы, изменённые относительно git-ref | `--diff HEAD~1` |
| `-c`, `--copy` | Копирует финальный бандл в буфер | `--copy` |
| `--preset` | Пресет `review`, `refactor` или `docs` | `--preset review` |
| `--redact` | Заменяет найденные секреты на `[REDACTED]` | `--redact` |
| `--skeletons` / `--no-skeletons` | Убирает тела Python-функций или явно отключает режим | `--skeletons` |
| `--symbol-map` | Добавляет индекс Python-классов и функций | `--symbol-map` |
| `--auto-shrink` | Укладывает бандл в лимит вместо немедленной ошибки | `--auto-shrink --max-tokens 50000` |
| `--lang` | Язык терминального вывода: `en` или `ru` | `--lang ru` |
| `--no-config` | Игнорирует конфиг проекта | `--no-config` |

`--chunk-size` работает только с `--format plain`. При отсутствии `--output` части получают имена вида `plain/<проект>_001.txt`.

## Пресеты

| Пресет | Действие |
| --- | --- |
| `review` | Использует `--diff HEAD~1` и добавляет список недавних коммитов. |
| `refactor` | Исключает `tests/*`, `docs/*` и `*.md`. |
| `docs` | Оставляет `*.md` и `*.py`, включает skeletons. |

Пресет имеет приоритет над конфигом, но явный флаг выше обоих. Например, `--preset docs --no-skeletons` оставит тела функций.

## Конфигурация проекта

`ai-pack` читает `[tool.aipack]` из `aipack.toml` или `pyproject.toml` в корне проекта. Если есть оба файла, используется `aipack.toml` и выводится предупреждение.

```toml
[tool.aipack]
exclude = ["generated/*"]
max_size = "300kb"
max_tokens = 60000
fmt = "xml"
strip_comments = true
redact = true
skeletons = false
symbol_map = true
lang = "ru"
```

Поддерживаемые ключи: `exclude`, `include`, `max_size`, `max_tokens`, `fmt`, `strip_comments`, `no_tree`, `redact`, `skeletons`, `symbol_map`, `lang`.

Приоритет настроек: встроенные значения < конфиг проекта < `--preset` < явно переданные флаги. Списки `exclude` и `include` на более высоком уровне заменяют список целиком, а не объединяются. `--no-config` отключает чтение обоих конфигов.

## Redact, Skeletons и Symbol Map

`--redact` ищет типичные ключи API, токены, пароли, строки подключения и PEM-блоки и заменяет значения на `[REDACTED]`. Сигнатуры и имя файла остаются видимыми. Это эвристика, а не гарантия отсутствия секретов: перед внешней передачей результата всё равно нужна проверка.

`--skeletons` и `--symbol-map` в v0.4 работают только для Python. Skeletons сохраняют импорты, константы, сигнатуры и docstring, но заменяют тела функций и методов на `...`. Для Python с синтаксической ошибкой исходное содержимое остаётся без изменений. Другие языки не преобразуются.

## Auto-shrink

`--auto-shrink` требует `--max-tokens` и несовместим с `--chunk-size`. Если бандл слишком велик, шаги применяются строго по порядку:

1. Включаются `--strip-comments`.
2. Включаются Python skeletons.
3. По одному исключаются самые большие тестовые файлы.
4. Затем исключаются самые большие оставшиеся файлы с обычным или конфигурационным приоритетом.

README и точки входа не удаляются автоматически. Исключённый файл остаётся в дереве и в бандле с явным маркером; например, plain-формат содержит `FILE: tests/test_api.py [OMITTED - auto-shrink: token budget]`. XML использует `<file ... omitted="true" reason="auto-shrink" />`.

## Локализация

`--lang en` и `--lang ru` задают язык статистики, сообщений записи и ошибок, которые формирует CLI. При отсутствии флага используется `AIPACK_LANG`, затем системная локаль; итоговый fallback - английский.

`ai-pack --help` всегда остаётся английским: Click строит справку до разбора `--lang`.

## Ограничения и troubleshooting

- `--copy` использует `pyperclip`. В headless/CI-среде может не быть системного backend (`xclip`, `xsel` или `wl-clipboard`); в таком случае обычная запись бандла продолжится, а CLI выведет предупреждение.
- Ошибка `--chunk-size is only supported with --format plain` означает, что XML и Markdown нельзя безопасно делить текущим chunker-ом.
- Ошибка `--auto-shrink requires --max-tokens to be set` означает, что не задан бюджет, к которому надо стремиться.
- Если auto-shrink всё ещё не укладывается в лимит, исключите дополнительные пути через `--exclude` или увеличьте `--max-tokens`.
- Предупреждения scanner-а, security-проверки и Python API намеренно остаются на английском: это программные данные, на которые могут опираться агенты и тесты.
