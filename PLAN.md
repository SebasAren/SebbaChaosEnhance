# PoECraft — Native Linux Chaos Recipe Filter Tool

A Linux-native tool that fetches your Path of Exile stash data, calculates
which chaos/regal/exalted recipe sets you can complete, and automatically
updates your loot filter to highlight the missing items.

## Tech Stack

- **Python 3** (uv for dependency management)
- **FastAPI** + **uvicorn** for the web server
- **httpx** for async HTTP (PoE API calls)
- **Jinja2** for HTML templates
- **PyYAML** for config
- **systemd** user service for background operation

## Directory Layout

```
poecraft/
├── PLAN.md
├── pyproject.toml
├── config.example.yaml
├── poecraft/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Config loading/validation
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py        # PoE API client
│   │   ├── models.py        # Pydantic response models
│   │   └── auth.py          # Session/cookie management
│   ├── recipe/
│   │   ├── __init__.py
│   │   ├── classifier.py    # Icon URL → item class
│   │   ├── sets.py          # Set generation logic
│   │   └── types.py         # Enums and constants
│   ├── filter/
│   │   ├── __init__.py
│   │   ├── reader.py        # Parse existing .filter files
│   │   ├── generator.py     # Generate filter rules
│   │   └── writer.py        # Inject/replace section in filter
│   └── web/
│       ├── __init__.py
│       ├── routes.py        # Web UI endpoints
│       └── templates/
│           ├── base.html
│           ├── index.html   # Dashboard
│           └── overlay.html # Minimal overlay page
└── systemd/
    └── poecraft.service     # User service unit
```

---

## Step 1: Project Scaffold + Config

**Goal:** Create the Python project structure, pyproject.toml, config loading,
and a basic FastAPI app that starts and serves a health endpoint.

### Tasks

1. **Create `pyproject.toml`** with dependencies:
   ```toml
   [project]
   name = "poecraft"
   version = "0.1.0"
   description = "Native Linux Chaos Recipe Filter Tool for Path of Exile"
   requires-python = ">=3.10"
   dependencies = [
       "fastapi>=0.115",
       "uvicorn[standard]>=0.30",
       "httpx>=0.27",
       "pyyaml>=6.0",
       "jinja2>=3.1",
       "pydantic>=2.0",
       "pydantic-settings>=2.0",
   ]

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"
   ```

2. **Create `config.example.yaml`**:
   ```yaml
   # PoE Account
   account_name: ""
   league: "Standard"
   session_id: ""  # POESESSID cookie value

   # Stash tabs to scan (list of tab indices, 0-based)
   stash_tabs: []

   # Recipe settings
   recipe_type: "chaos"  # chaos | regal | chance | exalted
   set_threshold: 5      # how many sets to track
   include_identified: false

   # Loot filter
   loot_filter_path: ""  # absolute path to your .filter file

   # Server
   host: "127.0.0.1"
   port: 8420

   # Auto-refresh interval in seconds (0 = manual only)
   refresh_interval: 30
   ```

3. **Create `poecraft/config.py`**:
   - Load config.yaml with PyYAML
   - Validate with Pydantic Settings model
   - Provide defaults for all fields
   - Export a singleton `get_config()` function

4. **Create `poecraft/main.py`**:
   - FastAPI app with lifespan handler
   - Mount Jinja2 templates
   - Include router from `web.routes`
   - `/health` endpoint returning `{"status": "ok"}`
   - `__main__` block: load config, run uvicorn

5. **Create empty `__init__.py`** files for all packages

6. **Verify:** Run `uv sync` then `uv run python -m poecraft.main` —
   server starts on port 8420, `curl localhost:8420/health` returns ok.

---

## Step 2: PoE API Client + Item Classification

**Goal:** Fetch stash tab metadata and contents from the PoE API,
and classify items by decoding their icon URLs into item classes.

### Tasks

1. **Create `poecraft/api/models.py`** — Pydantic models for API responses:
   ```python
   # Stash tab metadata (from tabs=1 response)
   class StashTabProps:
       id: str
       name: str
       type: str          # "NormalStash", "CurrencyStash", etc.
       index: int
       children: list     # for Folder type

   # Individual item in a stash tab
   class StashItem:
       id: str
       name: str           # prefix name (e.g. "Shaper's")
       typeLine: str       # base type (e.g. "Gold Ring")
       ilvl: int
       frameType: int      # 0=Normal, 1=Magic, 2=Rare, 3=Unique
       identified: bool
       icon: str           # CDN URL with base64 metadata
       category: dict      # {"ring": []} or {"armour": ["helmet"]}
       socketedItems: list
       influences: dict    # {"shaper": true} etc.
       x: int
       y: int
       w: int
       h: int
       # ... other fields as needed
   ```

2. **Create `poecraft/recipe/types.py`** — Enums and constants:
   ```python
   class ItemClass(str, Enum):
       HELMETS = "Helmets"
       BODY_ARMOURS = "BodyArmours"
       GLOVES = "Gloves"
       BOOTS = "Boots"
       RINGS = "Rings"
       AMULETS = "Amulets"
       BELTS = "Belts"
       ONE_HAND_WEAPONS = "OneHandWeapons"
       TWO_HAND_WEAPONS = "TwoHandWeapons"

   class RecipeType(str, Enum):
       CHAOS = "chaos"
       REGAL = "regal"
       CHANCE = "chance"
       EXALTED = "exalted"

   # Item level ranges per recipe type
   RECIPE_ILVL_RANGES = {
       RecipeType.CHAOS:  (60, 74),
       RecipeType.REGAL:  (75, 999),
       RecipeType.CHANCE: (1, 59),
       RecipeType.EXALTED: (60, 999),
   }
   ```

3. **Create `poecraft/recipe/classifier.py`** — Icon URL → item class:
   ```python
   def classify_item(icon_url: str) -> ItemClass | None:
       """
       Decode the base64 metadata from the icon URL to derive the item class.

       The 5th path segment of the URL is a base64-encoded JSON array:
         [25,14,{"f":"2DItems/Rings/TopazSapphire","w":1,"h":1,"scale":1}]

       The "f" field contains the item path. Split by "/" and extract:
       - index 1 for Rings, Amulets, Belts
       - index 2 for Armours/* and Weapons/* (e.g. Helmets, Gloves, Boots, etc.)
       """
   ```

   Implementation notes:
   - Split icon URL by `/`, take segment at index 4
   - Base64 decode it (add padding if needed)
   - Parse as JSON, extract the `"f"` field
   - Split `"f"` by `/`, check element at index 1:
     - `"Rings"` → `ItemClass.RINGS`
     - `"Amulets"` → `ItemClass.AMULETS`
     - `"Belts"` → `ItemClass.BELTS`
     - `"Weapons"` → check index 2 for `OneHandWeapons` vs `TwoHandWeapons`
     - `"Armours"` → check index 2 for `Helmets`, `Gloves`, `Boots`, `BodyArmours`

4. **Create `poecraft/api/auth.py`** — Session management:
   - Store POESESSID in a cookie jar
   - Provide helper to set session ID from config
   - Health check: hit the account-avatar endpoint to validate session

5. **Create `poecraft/api/client.py`** — The API client:
   ```python
   class PoeApiClient:
       BASE = "https://www.pathofexile.com"

       def __init__(self, account_name: str, league: str, session_id: str):
           ...

       async def get_stash_tabs(self) -> list[StashTabProps]:
           """GET /character-window/get-stash-items?accountName=...&league=...&tabs=1&tabIndex="""

       async def get_stash_tab_contents(self, tab_index: int) -> list[StashItem]:
           """GET /character-window/get-stash-items?accountName=...&league=...&tabIndex=N"""

       async def get_all_selected_tabs(self, tab_indices: list[int]) -> dict[int, list[StashItem]]:
           """Fetch contents for multiple tabs with rate limit handling."""
   ```

   Implementation notes:
   - Use httpx.AsyncClient with cookie jar
   - Set User-Agent: `poecraft/0.1.0 (contact: you@example.com)`
   - Parse `X-Rate-Limit-*` headers and back off if needed
   - Retry 429 responses with exponential backoff
   - Log all requests and responses (for debugging)

6. **Verify:** Create a test script that loads config, fetches tab metadata,
   prints tab names. Then fetch one tab's contents and print classified items.

---

## Step 3: Set Generation Logic

**Goal:** Given a list of classified items, calculate which recipe sets
are complete, which are missing items, and what the missing item classes are.

### Tasks

1. **Create `poecraft/recipe/sets.py`**:
   ```python
   @dataclass
   class RecipeSet:
       """A single in-progress recipe set."""
       items: dict[ItemClass, EnhancedItem]  # filled slots
       missing: set[ItemClass]               # empty slots
       is_complete: bool

   @dataclass
   class RecipeStatus:
       """Overall recipe tracking status."""
       completed_sets: int
       in_progress: list[RecipeSet]
       missing_classes: set[ItemClass]  # union of all missing across sets
       item_counts: dict[ItemClass, int]
       needs_lower_level: bool

   def generate_sets(
       items: list[EnhancedItem],
       recipe_type: RecipeType,
       set_threshold: int,
       include_identified: bool = False,
       vendor_sets_early: bool = False,
       do_not_preserve_low_ilvl: bool = False,
   ) -> RecipeStatus:
       ...
   ```

2. **Implement `EnhancedItem`** dataclass:
   ```python
   @dataclass
   class EnhancedItem:
       id: str
       name: str
       type_line: str
       item_level: int
       frame_type: int        # 0=Normal, 1=Magic, 2=Rare
       identified: bool
       icon: str
       derived_item_class: ItemClass | None
       stash_tab_index: int
       x: int
       y: int
       influences: dict       # {"shaper": True, ...}

       @property
       def is_rare(self) -> bool:
           return self.frame_type == 2

       @property
       def is_chaos_eligible(self) -> bool:
           return 60 <= self.item_level <= 74

       @property
       def is_regal_eligible(self) -> bool:
           return self.item_level >= 75

       @property
       def is_chance_eligible(self) -> bool:
           return 1 <= self.item_level <= 59

       @property
       def is_exalted_eligible(self) -> bool:
           return self.item_level >= 60
   ```

3. **Implement `generate_sets()`** — Port the logic from CRE:
   - Filter items by recipe eligibility (ilvl, rarity, influence)
   - Sort: two-hand weapons first, then by class
   - Create `set_threshold` empty sets
   - Fill each set one item at a time, prioritizing closest items
   - Track which classes are missing per set
   - Return `RecipeStatus` with counts and missing classes

4. **Implement helper functions:**
   - `filter_stash_items(raw_items, config) → list[EnhancedItem]`
     - Classify each item via `classifier.classify_item()`
     - Filter by recipe-eligible ilvl range
     - Filter by rarity (rare, unless identified setting says otherwise)
     - Return only items that belong to a recipe-relevant class
   - `count_items(items) → dict[ItemClass, int]`

5. **Verify:** Create a test with mock items, verify set generation
   produces correct counts and missing classes.

---

## Step 4: Filter Manipulation

**Goal:** Read an existing `.filter` file, generate chaos recipe filter rules,
inject them between marker comments, and write the file back.

### Tasks

1. **Create `poecraft/filter/reader.py`**:
   ```python
   MARKER_START = "# Chaos Recipe START - Filter Manipulation by PoECraft"
   MARKER_END = "# Chaos Recipe END - Filter Manipulation by PoECraft"

   def read_filter(path: str) -> str:
       """Read the .filter file contents."""

   def split_filter(content: str) -> tuple[str, str, str]:
       """
       Split filter into (before_section, existing_section, after_section).
       If no markers exist, the whole file is 'after_section'.
       """
   ```

2. **Create `poecraft/filter/generator.py`**:
   ```python
   # Default style applied to all generated rules
   DEFAULT_STYLE = [
       "Sockets < 6",
       "LinkedSockets < 5",
   ]

   # Colors per item class (RGBA hex from CRE defaults)
   CLASS_COLORS = {
       ItemClass.RINGS:          {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
       ItemClass.AMULETS:        {"bg": "#FFFF6AFF", "text": "#FFFFFFFF", "border": "#FFFF6AFF"},
       ItemClass.BELTS:          {"bg": "#FF8C00FF", "text": "#FFFFFFFF", "border": "#FF8C00FF"},
       ItemClass.BODY_ARMOURS:   {"bg": "#FF6132FF", "text": "#FFFFFFFF", "border": "#FF6132FF"},
       ItemClass.HELMETS:        {"bg": "#FF6132FF", "text": "#FFFFFFFF", "border": "#FF6132FF"},
       ItemClass.GLOVES:         {"bg": "#FF6132FF", "text": "#FFFFFFFF", "border": "#FF6132FF"},
       ItemClass.BOOTS:          {"bg": "#FF6132FF", "text": "#FFFFFFFF", "border": "#FF6132FF"},
       ItemClass.ONE_HAND_WEAPONS: {"bg": "#FFFFFFFF", "text": "#FF0000FF", "border": "#FFFFFFFF"},
       ItemClass.TWO_HAND_WEAPONS: {"bg": "#FFFFFFFF", "text": "#FF0000FF", "border": "#FFFFFFFF"},
   }

   def generate_rule(
       item_class: ItemClass,
       recipe_type: RecipeType,
       is_missing: bool,
       include_identified: bool = False,
       style_overrides: dict | None = None,
   ) -> str:
       """
       Generate a single PoE filter rule for an item class.

       Format:
           Show  (or Hide if always-hidden and not missing)
               Class "Rings"
               Rarity Rare
               Identified False
               ItemLevel >= 60
               ItemLevel <= 74
               HasInfluence None
               Sockets < 6
               LinkedSockets < 5
               SetBackgroundColor R G B A
               SetFontSize 40
               SetTextColor R G B A
               SetBorderColor R G B A
               MinimapIcon 0 Yellow Circle
               PlayEffect Yellow Temp
       """

   def generate_section(
       missing_classes: set[ItemClass],
       recipe_type: RecipeType,
       include_identified: bool = False,
       always_active_classes: set[ItemClass] | None = None,
   ) -> str:
       """
       Generate the full chaos recipe filter section.
       Rules for missing classes are 'Show', others can be 'Show' if always-active.
       """
   ```

   Implementation notes:
   - Parse hex colors (e.g. `#AABBCCFF`) into RGBA integers
   - The `Class` filter line needs quotes for multi-word classes: `Class "Body Armours"`
     Use: `"Rings"`, `"Amulets"`, `"Belts"`, `"Body Armours"`, `"Helmets"`,
     `"Gloves"`, `"Boots"`, `"One Hand Weapons"`, `"Two Hand Weapons"`
   - Weapon rules need space-saving options (hide 2H weapons if user configures)

3. **Create `poecraft/filter/writer.py`**:
   ```python
   def update_filter(
       filter_path: str,
       missing_classes: set[ItemClass],
       recipe_type: RecipeType,
       include_identified: bool = False,
   ) -> bool:
       """
       Read filter, generate section, inject between markers, write back.
       Returns True if filter was updated.
       """
       content = read_filter(filter_path)
       before, _, after = split_filter(content)
       section = generate_section(missing_classes, recipe_type, include_identified)
       new_content = before + section + after
       write_filter(filter_path, new_content)
       return True

   def remove_chaos_section(filter_path: str) -> bool:
       """Remove the chaos recipe section from the filter file."""
   ```

4. **Verify:** Test with a sample `.filter` file:
   - Create a dummy filter with some existing rules
   - Run `update_filter()` with known missing classes
   - Read back and verify the section was injected correctly
   - Run again and verify the section was replaced (not duplicated)

---

## Step 5: Web UI + Main Loop

**Goal:** Build the web dashboard and tie everything together with
periodic auto-refresh.

### Tasks

1. **Create `poecraft/web/templates/base.html`**:
   - Clean dark theme (PoE-inspired)
   - Auto-refresh via JavaScript interval
   - Responsive layout

2. **Create `poecraft/web/templates/index.html`**:
   - Dashboard showing:
     - Current league and configured tabs
     - Set completion status (X/Y complete)
     - Item counts per class (table with icons if possible)
     - Missing classes list (highlighted)
     - Last refresh timestamp
     - Manual refresh button
   - Settings panel:
     - League selector (fetched from API)
     - Tab multi-select (fetched from API)
     - Recipe type dropdown
     - Set threshold number input
     - Filter file path + browse
     - Include identified items toggle
     - Save config button

3. **Create `poecraft/web/templates/overlay.html`**:
   - Minimal page showing just the missing item classes
   - Large text, high contrast, no chrome
   - Auto-refreshes on same interval
   - Designed to be used with browser overlay tools or OBS

4. **Create `poecraft/web/routes.py`**:
   ```python
   router = APIRouter()

   @router.get("/")
   async def dashboard(request: Request): ...

   @router.get("/overlay")
   async def overlay(request: Request): ...

   @router.get("/api/status")
   async def api_status(): ...

   @router.post("/api/refresh")
   async def api_refresh(): ...

   @router.post("/api/config")
   async def api_update_config(settings: dict): ...

   @router.get("/api/leagues")
   async def api_leagues(): ...

   @router.get("/api/tabs")
   async def api_tabs(): ...
   ```

5. **Wire up `main.py`**:
   - On startup: load config, create API client, run initial fetch
   - Background task: periodic refresh every `refresh_interval` seconds
   - On refresh: fetch stash → classify → generate sets → update filter
   - Store current `RecipeStatus` in memory for the web UI to read

6. **Verify:** Start the server, open dashboard in browser, verify:
   - Tabs are listed correctly
   - Item counts update after manual refresh
   - Filter file is modified with correct rules
   - Overlay page shows missing classes

---

## Step 6: Systemd Service + Polish

**Goal:** Create a systemd user service for background operation,
add CLI entrypoint, and final polish.

### Tasks

1. **Create `systemd/poecraft.service`**:
   ```ini
   [Unit]
   Description=PoECraft - Chaos Recipe Filter Tool
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   ExecStart=%h/.local/bin/poecraft
   Restart=on-failure
   RestartSec=5
   Environment=POECRAFT_CONFIG=%h/.config/poecraft/config.yaml

   [Install]
   WantedBy=default.target
   ```

2. **Add CLI entrypoint** in `pyproject.toml`:
   ```toml
   [project.scripts]
   poecraft = "poecraft.main:cli"
   ```

3. **Add `--config` CLI flag** for custom config path

4. **Create install script** (`install.sh`):
   ```bash
   #!/bin/bash
   uv tool install .
   mkdir -p ~/.config/poecraft
   cp config.example.yaml ~/.config/poecraft/config.yaml
   mkdir -p ~/.config/systemd/user
   cp systemd/poecraft.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   echo "Edit ~/.config/poecraft/config.yaml with your settings"
   echo "Then: systemctl --user enable --now poecraft"
   ```

5. **Final verification:**
   - Install with `uv tool install .`
   - Configure with real POESESSID
   - Start service
   - Open dashboard, verify stash data loads
   - Check that filter file is updated
   - Test overlay page

---

## Open Questions (resolve before Phase 1)

1. **PoE 1 confirmed?** (assumed yes based on CRE targeting PoE 1)
2. **POESESSID auth only for v1?** (OAuth2 can be added later)
3. **Filter reload on Linux:** Skip for v1 — user presses reload keybind manually. Could add ydotool integration later.
