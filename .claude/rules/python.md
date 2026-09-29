# Python Rules

## HARD BLOCKS (reject if violated)

1. **No bare `except:` or blanket `except Exception: pass`** — Swallowing an error
   hides a data-processing failure and produces a silently wrong result set. Catch a
   specific exception and record a typed exception code on the affected row.
2. **No untyped public functions** — Public functions, pipeline stages, and schema
   models carry type hints. `mypy` must pass on changed code. Untyped boundaries are
   where row-shape drift hides.
3. **No mutable default arguments** (`def f(x=[])`) — Use `None` and initialise inside.

## REQUIRED PATTERNS

- **Row/config models:** define row shapes and configs as `pydantic` models (or
  `dataclass`) validated at the boundary; the shared shapes live in `libs/`.
- **Config via env / files, not literals:** taxonomy version, thresholds, model
  version, paths come from config — never hardcoded (see `command-conventions.md`).
- **Deterministic:** seed any randomness; sort before writing outputs so runs are
  reproducible (Contract 4).
- **Structured logging:** log source IDs + non-identifying metadata only — never
  sensitive content or identifiers (see `privacy-sensitive-data.md`).
- **Naming:** `PascalCase` for classes/models, `snake_case` for functions/vars,
  `SCREAMING_SNAKE_CASE` for module-level constants.
- **`pathlib.Path`** over string paths; **`with`** for every file handle.

## SUPPRESSIONS (do NOT flag)

- Broad `except` in a top-level batch runner that records a `failed`/exception code
  on the row and re-raises or logs (fail loud, not silent).
- `type: ignore` with a one-line reason comment on a genuinely untyped third-party lib.
