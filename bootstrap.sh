#!/usr/bin/env bash
# bootstrap.sh — kept at the repository root for anyone who has it bookmarked.
#
# The script itself now ships inside the lanekeeper package, and `lanekeeper board`
# generates its inputs from .lanekeeper/config.yaml so the board carries the same lane
# names the gate enforces. Run that instead; this wrapper just forwards to the script.
exec "$(dirname "$0")/src/lanekeeper/scripts/bootstrap.sh" "$@"
