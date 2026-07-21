# Contributing to NESTfetch

Thanks for your interest in improving NESTfetch! This guide covers local setup,
the quality gates, and how to add a new site.

## Development setup

NESTfetch uses a `src/` layout: the importable package lives in
`src/nestfetch/`. Install it in editable mode so imports resolve everywhere.

```bash
python -m venv .venv && source .venv/bin/activate   # optional but recommended
make install-dev          # editable install + pytest, ruff, mypy
# equivalently:
pip install -e ".[async,config,dev]"
pip install -r requirements-dev.txt
```

Run it with `python -m nestfetch` (or the installed `nestfetch` command).

## Quality gates

Everything CI enforces can be run locally with one target:

```bash
make check      # ruff + mypy + health-check + pytest
```

Or individually:

| Command        | What it does                                            |
|----------------|---------------------------------------------------------|
| `make lint`    | `ruff check .` — style + common bug patterns            |
| `make type`    | `mypy` — static type checking on `src/nestfetch`        |
| `make health`  | Re-parses `samples/` to catch config drift (0 items)    |
| `make test`    | `pytest` — the full offline suite                       |

The entire test suite is **offline**: it uses recorded HTML in `samples/` and
fake HTTP/clock objects in `tests/fakes.py`. No network access is required (or
allowed) during tests. Please keep it that way — never make a live request in a
test.

## Coding conventions

- Target **Python 3.9+**. Prefer standard library; new hard runtime deps need a
  good reason (optional extras are fine, guarded by a soft import).
- Formatting is governed by `.editorconfig` and `ruff` (line length 100).
- Public functions/classes get docstrings and type hints.
- **Error handling policy:**
  - Intentional best-effort cleanup (closing a socket, quitting a browser,
    decoding an optional value) may swallow exceptions with a bare `pass` — this
    is deliberate and should stay quiet.
  - Anything diagnostically useful (an adapter failing to load, a browser
    failing to open) must log at `log.debug(...)` inside the `except`, never a
    silent `pass`.
  - Never use a bare `except:`; always `except Exception as exc:` (or narrower).

## Adding a new site

Most sites need **zero Python** — they are pure JSON configs.

1. Save a representative listing page to `samples/<site>.txt` (used by the
   health-check and the `test_real_<site>_config` regression test).
2. Drop a `src/nestfetch/sites/configs/<site>.json` describing how to extract
   listings, detail pages, and mirrors. Start from
   `_preset_wordpress-repack.json` or an existing config; see
   `src/nestfetch/sites/configs/README.md` for the schema.
3. Add a `test_real_<site>_config` assertion in `tests/test_config_adapter.py`.
4. Run `make health` and `make test` — both must stay green, and
   `python -m nestfetch --list-sites` should show your site.

Only reach for a hand-written Python adapter (like `switchroms.py`) when a site
needs logic a config can't express.

## Pull requests

- Keep PRs focused; update `CHANGELOG.md` under the top section.
- Ensure `make check` passes before pushing — CI runs the same gates on
  Python 3.9 / 3.11 / 3.12.
- Please read `SECURITY.md` for the project's responsible-use stance.
