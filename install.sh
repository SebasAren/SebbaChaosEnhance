#!/usr/bin/env bash
#
# PoECraft installer.
#
# Installs the app via `uv tool`, drops a default config (without clobbering an
# existing one), and installs the systemd user service. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG_DIR="${POECRAFT_CONFIG_DIR:-$HOME/.config/poecraft}"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "==> Installing poecraft via 'uv tool'"
uv tool install "$SCRIPT_DIR"

echo "==> Ensuring config directory: $CONFIG_DIR"
mkdir -p "$CONFIG_DIR"

if [[ -f "$CONFIG_FILE" ]]; then
    echo "    Existing config at $CONFIG_FILE left untouched"
else
    cp "$SCRIPT_DIR/config.example.yaml" "$CONFIG_FILE"
    echo "    Wrote default config to $CONFIG_FILE"
fi

echo "==> Installing systemd user service"
mkdir -p "$SYSTEMD_USER_DIR"
cp "$SCRIPT_DIR/systemd/poecraft.service" "$SYSTEMD_USER_DIR/poecraft.service"
systemctl --user daemon-reload

cat <<EOF

==> Done. Next steps:

  1. Edit $CONFIG_FILE and set:
       - account_name, league, session_id (POESESSID cookie)
       - stash_tabs      (comma-separated, 0-based tab indices)
       - client_log_path (Path of Exile Client.txt)
       - loot_filter_path (your .filter file)

  2. Enable and start the service:
       systemctl --user enable --now poecraft

  3. Open the dashboard: http://127.0.0.1:8420

  4. Reload your loot filter in-game (Options -> UI -> Loot Filter) so PoECraft's
     highlight rules take effect. PoECraft does not auto-reload the filter.

Logs:        journalctl --user -u poecraft -f
Stop/start:  systemctl --user {stop,restart} poecraft
EOF
