#!/usr/bin/env python3
"""CG-12: non-certifying telemetry fixture gate for playback lab scenarios.

One invocation per scenario; the runner that drives real FFmpeg, emulators,
network faults and the published server image must supply its observations.
No playback behavior or numeric thresholds are changed or invented here.

    python3 tools/playback_lab.py <scenario> <evidence-json>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCENARIOS: dict[str, tuple[str, ...]] = {
    "bandwidth_loss_recovery": ("play_started", "bandwidth_reduced", "stall_seen", "bandwidth_restored", "playback_resumed"),
    "brief_stalls": ("play_started", "brief_stall_seen", "playback_resumed"),
    "conversion_behind": ("play_started", "conversion_behind", "conversion_recovered", "playback_resumed"),
    "abrupt_disconnect": ("play_started", "network_lost", "retry_started", "network_restored", "playback_resumed"),
    "wifi_cellular": ("play_started", "wifi_lost", "cellular_connected", "playback_resumed"),
    "competing_remote_viewers": ("viewer_one_started", "viewer_two_started", "both_progressing"),
    "multi_track_switch": ("play_started", "tracks_switched", "audio_continues", "subtitle_continues", "position_kept"),
    "stations_1080p_4k": ("station_1080p_started", "station_4k_started", "station_clocks_observed"),
    "unsupported_decoder": ("play_started", "decoder_incompatible", "result_observed"),
    "server_app_restart": ("play_started", "server_restarted", "app_restarted", "playback_resumed"),
}


def _event_names(events: object) -> list[str]:
    """Reject private fields, malformed labels and nonmonotonic timestamps."""
    if not isinstance(events, list) or not events:
        raise ValueError("no measured events recorded")
    names: list[str] = []
    last_ms = -1
    for event in events:
        if not isinstance(event, dict) or set(event) != {"name", "at_ms"}:
            raise ValueError("event has unknown or potentially private fields")
        name, ms = event["name"], event["at_ms"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,49}", name):
            raise ValueError("invalid event label")
        if type(ms) is not int or ms < last_ms or ms < 0:
            raise ValueError("event times are invalid or out of order")
        last_ms = ms
        names.append(name)
    return names


def validate(record: dict) -> dict:
    """Require ordered and privacy-safe event evidence; NOT a lab certification.

    This contract intentionally cannot replace measured playback thresholds
    or independently prove signals were gathered from real emulators.
    """
    if not isinstance(record, dict) or set(record) != {"scenario", "run_id", "image_digest", "events"}:
        raise ValueError("invalid evidence structure")
    scenario = record["scenario"]
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise ValueError("unknown playback scenario")
    run = record["run_id"]
    digest = record["image_digest"]
    if not isinstance(run, str) or not re.fullmatch(r"[0-9]{6,}", run):
        raise ValueError("missing or invalid run identifier")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("image must be recorded by immutable SHA-256 digest")
    names = _event_names(record["events"])
    cursor = 0
    for expected in SCENARIOS[scenario]:
        try:
            cursor = names.index(expected, cursor) + 1
        except ValueError:
            raise ValueError("required scenario evidence is absent or out of order") from None
    return {"scenario": scenario, "status": "fixture_contract_complete"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        outcome = validate(data)
        if outcome["scenario"] != args.scenario:
            raise ValueError("scenario does not match requested test")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        # Never echo input data, paths, tokens, addresses or file names.
        print("playback lab: evidence rejected; see private test log", file=sys.stderr)
        return 1
    print("playback lab: fixture contract complete (NOT lab-certified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
