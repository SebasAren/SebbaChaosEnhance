# AGENTS.md

Guidance for AI coding agents working in this repo.

## What this is

PoECraft is a native Linux tool for the Path of Exile **chaos recipe** (and
regal/chance/exalted). It tails the game's `Client.txt` log, and on each zone
change re-fetches the configured stash tabs, computes which recipe sets are
complete/missing, and rewrites a marker-wrapped highlight section in the user's
loot filter.

Python 3.10+, managed with [uv](https://docs.astral.sh/uv/). Stack: FastAPI +
uvicorn, httpx, pydantic, PyYAML, Jinja2.

## Commands

```bash
uv run pytest                 # run tests (sync tests use asyncio.run)
uv run ruff check .           # lint
uv run ruff format .          # format
uv run python -m poecraft.main        # run the server (default 127.0.0.1:8420)
./install.sh                  # install as a systemd user service
```

Version control is **jj** (on top of git). Use conventional commits:
`type(scope): description`.

## Architecture

The data flow is a single **refresh cycle**, centralized in `state.py`:

```
client.get_all_selected_tabs()  →  sets.generate_sets()  →  filter.writer.update_filter()
        (api/client.py)              (recipe/sets.py)          (filter/writer.py)
```

`RecipeState.refresh()` (in `state.py`) holds an `asyncio.Lock` for the whole
cycle, so the three triggers — the **logwatch** zone-change watcher, the
**periodic** timer, and the manual **Refresh** button — queue instead of racing.

Key modules:

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app, `lifespan` (wires client/state/logwatch/periodic), CLI |
| `config.py` | YAML config load/validate/save; `get_config()` singleton |
| `state.py` | `RecipeState` — owns the refresh cycle, SSE pub/sub, status payload |
| `logwatch.py` | Tails `Client.txt`, fires callback on zone-change lines |
| `api/client.py` | PoE stash API client; `_get` handles rate limits + 429 retry |
| `api/auth.py` | POESESSID cookie auth (no OAuth) |
| `recipe/sets.py` | Pure set-generation: eligible items → `RecipeSet`s |
| `recipe/classifier.py` | Derives item class from base64 icon-URL metadata |
| `filter/reader.py` / `generator.py` / `writer.py` | Parse / emit / splice the marker-wrapped filter section |
| `web/routes.py` | Dashboard, REST endpoints, SSE stream, config persistence |

## Conventions

- **Filter editing is highlight-only.** Never emit `Hide`. Inject/replace a
  `MARKER_START`/`MARKER_END`-wrapped `Show` block; preserve everything outside.
- **The client and filter writer are injected** into `refresh()` so the cycle is
  unit-testable without network or filesystem. Tests use `FakeClient` /
  `FakeFilterWriter` (see `tests/test_web.py`).
- **`get_config()` reads the live singleton** — call it at use-time, don't
  capture at startup, or credential/tab changes won't take effect. `resolve_client()`
  rebuilds the API client when account/league/session change.
- **Version comes from `importlib.metadata`** (`poecraft.__version__`), sourced
  from `pyproject.toml`. Don't hardcode it.
- **The PoE API embeds no per-item tab index** — it's injected from the fetch
  loop in `state.py` (`data["stashTabindex"] = tab_index`).

## Testing notes

- No pytest-asyncio. Async code is exercised via `asyncio.run(coro())` inside
  ordinary sync test functions.
- `tests/test_client.py` uses `httpx.MockTransport` to exercise `_get` status
  branches and 429 retry without network.

## Domain facts

- Recipe set = 2 rings, 1 amulet, 1 belt, 1 each helmet/gloves/boots/body, and a
  weapon slot (either one 2H or two 1H weapons).
- ilvl ranges: chaos 60–74, regal 75+, chance 1–59, exalted 60+.
- The dashboard models a **24×24 Quad tab**; only Quad tabs are offered in the picker.
