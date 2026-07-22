# PoECraft

Native Linux tool for the Path of Exile chaos recipe (and regal/chance/exalted).
It scans your stash tabs, groups rare items into recipe sets, highlights the
still-needed classes in your loot filter, and refreshes automatically when you
change zones — driven by the game's `Client.txt` log.

![dashboard grid](https://img.shields.io/badge/dashboard-24x24%20grid-e94560)

## How it works

- **Zone-change driven refresh.** A background watcher tails
  `Client.txt`; each time you enter a new area it re-fetches the configured
  stash tabs, regenerates recipe sets, and rewrites the loot-filter highlight
  section.
- **Highlight-only filter editing.** PoECraft never deletes your filter
  rules — it injects/replaces a marker-wrapped `Show` block for the recipe
  classes you're still missing.
- **POESESSID auth.** Account cookie only — no OAuth, no third-party logins.
- **Manual in-game reload.** PoECraft rewrites the `.filter` file on disk but
  does **not** auto-reload it in-game. Reload the filter yourself after a refresh
  (Options → UI → Loot Filter).

## Requirements

- Linux desktop (systemd user session)
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Path of Exile installed via Steam (Proton), so `Client.txt` exists at
  `~/.local/share/Steam/steamapps/common/Path of Exile/logs/Client.txt`
- A loot filter file (`.filter`) you want PoECraft to manage the highlight
  section of

## Install

From a checkout of this repo:

```bash
./install.sh
```

`install.sh` is idempotent and safe to re-run. It will:

1. `uv tool install .` — install the `poecraft` command to `~/.local/bin/`
2. Drop a default config at `~/.config/poecraft/config.yaml` (an existing one is
   **never** overwritten)
3. Install the systemd user unit and run `systemctl --user daemon-reload`

You can also install manually without systemd:

```bash
uv tool install .
```

## Configure

Edit `~/.config/poecraft/config.yaml`:

```yaml
account_name: "your_account"
league: "Standard"
session_id: "POESESSID cookie value"   # from your browser cookies

stash_tabs: [0, 1]                      # 0-based tab indices to scan

recipe_type: "chaos"                    # chaos | regal | chance | exalted
set_threshold: 5                        # how many sets to track
include_identified: false

loot_filter_path: "/abs/path/to/your.filter"
client_log_path: ""                     # empty => auto-discover Steam install
```

The **session_id** is the `POESESSID` cookie — grab it from your browser while
logged in to pathofexile.com.

## Usage with systemd

```bash
systemctl --user enable --now poecraft
```

Open the dashboard: <http://127.0.0.1:8420>

The grid renders each item at its stash position, colored by the recipe set it
belongs to (gray = surplus). Missing classes, per-class counts, and the last
refresh time are shown alongside. The **Refresh Now** button triggers a manual
refresh; the settings form saves config via `POST /api/config`.

Logs:

```bash
journalctl --user -u poecraft -f
```

Stop / restart:

```bash
systemctl --user stop poecraft
systemctl --user restart poecraft
```

## Running directly (no systemd)

```bash
poecraft --host 127.0.0.1 --port 8420
# or with an explicit config path:
POECRAFT_CONFIG=/path/to/config.yaml poecraft
```

## HTTP endpoints

| Method | Path            | Purpose                                            |
|--------|-----------------|----------------------------------------------------|
| GET    | `/`             | Dashboard (grid + status + settings)               |
| GET    | `/api/status`   | Current recipe status JSON (grid, counts, missing) |
| POST   | `/api/refresh`  | Trigger a refresh cycle                            |
| POST   | `/api/config`   | Validate and save config                           |
| GET    | `/api/leagues`  | Proxy the active league list                       |
| GET    | `/api/tabs`     | Proxy stash tab metadata                           |
| GET    | `/overlay`      | 302 redirect to `/` (overlay folded into dashboard)|
| GET    | `/health`       | Health check                                       |

## Troubleshooting

- **The loot filter must already exist.** PoECraft injects (or replaces) a
  marker-wrapped highlight section inside your `.filter`; it does not create a
  filter from scratch. Point `loot_filter_path` at an existing filter file.
- **Zone-change refresh needs a Client.txt path.** If `client_log_path` is empty
  *and* the Steam install isn't found at the default location, logwatch is
  disabled — but as long as `refresh_interval` > 0 a periodic refresh still
  runs every `refresh_interval` seconds. Otherwise refresh only happens via
  the **Refresh Now** button or `POST /api/refresh`.
- **Startup does an initial fetch.** With `stash_tabs` set and a valid
  `session_id`, PoECraft fetches the stash once on startup (in addition to each
  zone change).
- **Remember to reload the filter in-game** after a refresh — PoECraft rewrites
  the file on disk but does not auto-reload it.

## Development

```bash
uv sync                 # create venv + install deps
uv run pytest -q        # run the test suite
```

## Acknowledgements

PoECraft is a from-scratch, native-Linux reimplementation inspired by the
[Chaos Recipe Enhancer](https://github.com/ChaosRecipeEnhancer/ChaosRecipeEnhancer)
(CRE). The recipe-set logic, the highlight-only loot-filter manipulation, and
the zone-change-triggered refresh all follow CRE's design — thanks to the CRE
team for the concept.

## License

Copyright © 2026 Sebas.
Chaos Recipe Enhancer is Copyright © 2025 Chaos Recipe Enhancer Team.

PoECraft was developed with [Chaos Recipe Enhancer][cre] (CRE) as a guideline;
it is free software: you can redistribute it and/or modify it under the terms
of the [GNU General Public License as published by the Free Software
Foundation][gpl], either version 3 of the License, or (at your option) any
later version.

PoECraft is distributed in the hope that it will be useful, but **without any
warranty**; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
A PARTICULAR PURPOSE. See the [`LICENSE`](LICENSE) file for details.

[cre]: https://github.com/ChaosRecipeEnhancer/ChaosRecipeEnhancer
[gpl]: https://www.gnu.org/licenses/gpl-3.0.html

---

PoECraft is not affiliated with Grinding Gear Games.
