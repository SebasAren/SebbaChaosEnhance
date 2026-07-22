"""Tests for poecraft.logwatch — Client.txt zone-change watcher."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from poecraft.logwatch import (
    ClientLogWatcher,
    default_log_path,
    parse_zone_change,
    resolve_log_path,
)


def test_parse_zone_change_happy_path() -> None:
    line = "[INFO Client 340] : You have entered Divided Hideout."
    assert parse_zone_change(line) == "Divided Hideout"


@pytest.mark.parametrize(
    "line",
    [
        # Other INFO lines
        "[INFO Client 340] : Connected to ams.login.pathofexile.com.",
        "[INFO Client 340] : Some other status message.",
        # Chat lines (not zone changes)
        "<LOGINED> player: hi everyone",
        "#party: hello",
        # Blank / malformed
        "",
        "You have entered Lioneye's Watch but not really a log line",
        "[INFO Client 340] : You have entered Missing Trailing Period",
    ],
)
def test_parse_zone_change_non_matching_returns_none(line: str) -> None:
    assert parse_zone_change(line) is None


def test_default_log_path_discovers_steam_install(tmp_path: Path) -> None:
    # Build a fake Steam root: <root>/steamapps/common/Path of Exile/logs/Client.txt
    steam_root = tmp_path / "steam"
    client_txt = (
        steam_root
        / "steamapps"
        / "common"
        / "Path of Exile"
        / "logs"
        / "Client.txt"
    )
    client_txt.parent.mkdir(parents=True)
    client_txt.write_text("")

    found = default_log_path(roots=[steam_root])
    assert found == client_txt


def test_default_log_path_missing_returns_none(tmp_path: Path) -> None:
    # No install anywhere under the (empty) fake root.
    assert default_log_path(roots=[tmp_path]) is None


def test_resolve_log_path_explicit_config_wins(tmp_path: Path) -> None:
    explicit = tmp_path / "custom" / "Client.txt"
    explicit.parent.mkdir(parents=True)
    explicit.write_text("")

    config = SimpleNamespace(client_log_path=str(explicit))
    assert resolve_log_path(config, roots=[tmp_path]) == explicit


def test_resolve_log_path_falls_back_to_default(tmp_path: Path) -> None:
    steam_root = tmp_path / "steam"
    client_txt = (
        steam_root / "steamapps" / "common" / "Path of Exile" / "logs" / "Client.txt"
    )
    client_txt.parent.mkdir(parents=True)
    client_txt.write_text("")

    config = SimpleNamespace(client_log_path="")  # no explicit path
    assert resolve_log_path(config, roots=[steam_root]) == client_txt


def test_resolve_log_path_explicit_but_missing_returns_none(tmp_path: Path) -> None:
    config = SimpleNamespace(client_log_path=str(tmp_path / "does_not_exist.txt"))
    assert resolve_log_path(config, roots=[tmp_path]) is None


def test_process_new_extracts_single_zone_change_among_noise(tmp_path: Path) -> None:
    watcher = ClientLogWatcher(tmp_path / "Client.txt", on_zone_change=_noop)
    block = (
        "[INFO Client 340] : Connected to ams.login.pathofexile.com.\n"
        "[INFO Client 340] : You have entered Lioneye's Watch.\n"
        "<LOGINED> someone: hi\n"
    )
    assert watcher._process_new(block) == ["Lioneye's Watch"]


def test_process_new_no_zone_change_returns_empty(tmp_path: Path) -> None:
    watcher = ClientLogWatcher(tmp_path / "Client.txt", on_zone_change=_noop)
    block = (
        "[INFO Client 340] : Connected to ams.login.pathofexile.com.\n"
        "some chat line\n"
    )
    assert watcher._process_new(block) == []


def test_process_new_multiple_zone_changes(tmp_path: Path) -> None:
    watcher = ClientLogWatcher(tmp_path / "Client.txt", on_zone_change=_noop)
    block = (
        "[INFO Client 340] : You have entered The Twilight Temple.\n"
        "[INFO Client 340] : You have entered Lioneye's Watch.\n"
    )
    assert watcher._process_new(block) == ["The Twilight Temple", "Lioneye's Watch"]


async def _noop(_area: str) -> None:
    return None


class RecordingCallback:
    """Async callback that records every area it receives, in order."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, area: str) -> None:
        self.calls.append(area)


def test_poll_no_new_data_no_callback(tmp_path: Path) -> None:
    client_txt = tmp_path / "Client.txt"
    client_txt.write_text("existing line\n")
    callback = RecordingCallback()
    watcher = ClientLogWatcher(client_txt, on_zone_change=callback)

    asyncio.run(watcher._poll())  # initializes last_size, nothing new
    assert callback.calls == []


def test_poll_appended_zone_change_fires_callback(tmp_path: Path) -> None:
    client_txt = tmp_path / "Client.txt"
    client_txt.write_text("existing line\n")
    callback = RecordingCallback()
    watcher = ClientLogWatcher(client_txt, on_zone_change=callback)

    asyncio.run(watcher._poll())  # first poll establishes baseline size
    # append a zone-change line
    with open(client_txt, "a") as f:
        f.write("[INFO Client 340] : You have entered Lioneye's Watch.\n")
    asyncio.run(watcher._poll())  # second poll sees the append
    assert callback.calls == ["Lioneye's Watch"]


def test_poll_truncation_resets_offset_without_spurious_callback(tmp_path: Path) -> None:
    client_txt = tmp_path / "Client.txt"
    client_txt.write_text("[INFO Client 340] : You have entered Old Area.\n")
    callback = RecordingCallback()
    watcher = ClientLogWatcher(client_txt, on_zone_change=callback)

    asyncio.run(watcher._poll())  # consumes initial content, last_size set
    assert callback.calls == ["Old Area"]
    callback.calls.clear()

    # Simulate log rotation/truncation: rewrite the file smaller.
    client_txt.write_text("fresh small\n")
    asyncio.run(watcher._poll())  # size < last_size -> must reset, no callback
    assert callback.calls == []
    # Subsequent append of a zone line is picked up from the reset offset.
    with open(client_txt, "a") as f:
        f.write("[INFO Client 340] : You have entered New Area.\n")
    asyncio.run(watcher._poll())
    assert callback.calls == ["New Area"]


def test_start_skips_historical_zone_changes(tmp_path: Path) -> None:
    """Startup must not replay old zone-change lines from Client.txt.

    Only zone changes appended *after* the watcher starts should fire the
    callback (tail -f semantics). Replaying history on startup bursts the PoE
    API and trips rate limiting (HTTP 429).
    """
    client_txt = tmp_path / "Client.txt"
    client_txt.write_text(
        "[INFO Client 340] : You have entered Old Area 1.\n"
        "[INFO Client 340] : You have entered Old Area 2.\n"
    )
    callback = RecordingCallback()
    watcher = ClientLogWatcher(
        client_txt, on_zone_change=callback, poll_interval=0.01
    )

    async def driver() -> None:
        task = asyncio.create_task(watcher.start())
        await asyncio.sleep(0.03)  # let startup seed the offset
        with open(client_txt, "a") as f:  # append a post-startup zone change
            f.write("[INFO Client 340] : You have entered New Area.\n")
        for _ in range(50):
            await asyncio.sleep(0.02)
            if callback.calls:
                break
        await watcher.stop()
        await task

    asyncio.run(driver())
    assert callback.calls == ["New Area"]  # history skipped, only new fires


def test_start_stop_lifecycle(tmp_path: Path) -> None:
    client_txt = tmp_path / "Client.txt"
    client_txt.write_text("")  # start empty
    callback = RecordingCallback()
    watcher = ClientLogWatcher(
        client_txt, on_zone_change=callback, poll_interval=0.01
    )

    async def driver() -> None:
        task = asyncio.create_task(watcher.start())
        # let a baseline poll run on the empty file
        await asyncio.sleep(0.03)
        # append a zone-change line
        with open(client_txt, "a") as f:
            f.write("[INFO Client 340] : You have entered The Mud Flats.\n")
        # wait (bounded) for a poll to observe the append
        for _ in range(50):
            await asyncio.sleep(0.02)
            if callback.calls:
                break
        await watcher.stop()
        await task  # start() returns cleanly

    asyncio.run(driver())
    assert callback.calls == ["The Mud Flats"]
    assert watcher._running is False
