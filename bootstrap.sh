#!/usr/bin/env bash
#
# bootstrap.sh — create the GitHub coordination layer for a multi-seat repository.
#
# Creates, from one command:
#   * a project board
#   * the three single-select fields that make parallel work safe (Lane, Owner, Seat)
#   * the labels
#   * the milestones
#
# Then prints the two built-in board workflows that must be switched on by hand,
# because GitHub exposes no API for them (see NOTE ON WORKFLOWS below).
#
# Doing this by hand is what produces off-board tickets, half-stamped cards and
# nesting milestones. The point of the script is that the setup is identical
# every time and can be re-run without thinking.
#
# Idempotent. Re-running reports what already exists and creates only what does
# not. Safe to run against a repository that is already half configured.
#
# Usage:
#   ./bootstrap.sh [--config FILE] [--repo OWNER/NAME] [--dry-run] [--check]
#
#   --config FILE   inputs to read (default: ./bootstrap.conf)
#   --repo O/N      override the repository in the config
#   --dry-run       print every action, change nothing
#   --check         report the current state and exit; implies --dry-run
#
# Requires: bash, gh (authenticated), jq.
#
# ---------------------------------------------------------------------------
# NOTE ON WORKFLOWS
#
# The two board workflows worth having — "auto-add to project" and
# "item closed -> Done" — have no representation in the REST API or the GraphQL
# schema. They are settings behind the board UI and there is nothing to script.
#
# This script does not pretend otherwise. It ends by printing the exact clicks
# and the direct URL, and --check re-prints them, because a board without
# auto-add silently disagrees with the issue list and that failure recurs weekly.
# ---------------------------------------------------------------------------

set -euo pipefail

CONFIG="./bootstrap.conf"
REPO_OVERRIDE=""
DRY_RUN=0
CHECK_ONLY=0

# --------------------------------------------------------------- output ----

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""; C_GREEN=""; C_YELLOW=""; C_RED=""
fi

heading() { printf '\n%s==> %s%s\n' "$C_BOLD" "$1" "$C_RESET"; }
created() { printf '  %screated%s  %s\n' "$C_GREEN" "$C_RESET" "$1"; }
exists()  { printf '  %sexists %s  %s\n' "$C_DIM" "$C_RESET" "$1"; }
warn()    { printf '  %swarn   %s  %s\n' "$C_YELLOW" "$C_RESET" "$1"; }
note()    { printf '  %s%s%s\n' "$C_DIM" "$1" "$C_RESET"; }
die()     { printf '\n%serror%s  %s\n\n' "$C_RED" "$C_RESET" "$1" >&2; exit 1; }

would() { printf '  %swould  %s  %s\n' "$C_YELLOW" "$C_RESET" "$1"; }

# ------------------------------------------------------------ arguments ----

while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="${2:?--config needs a file}"; shift 2 ;;
    --repo)   REPO_OVERRIDE="${2:?--repo needs OWNER/NAME}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --check)  CHECK_ONLY=1; DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^#\{0,1\} \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

# ------------------------------------------------------------- preflight ----

command -v gh >/dev/null 2>&1 || die "gh is not installed. See https://cli.github.com"
command -v jq >/dev/null 2>&1 || die "jq is not installed."

gh auth status >/dev/null 2>&1 || die "gh is not authenticated. Run: gh auth login"

# Project boards need a scope the default login does not request. Ask for it up
# front rather than failing halfway through a partially created board.
if ! gh auth status 2>&1 | grep -q "'project'"; then
  die "The current token has no 'project' scope, so the board cannot be created.

  Grant it, then re-run:

      gh auth refresh -s project,read:project"
fi

[ -f "$CONFIG" ] || die "config not found: $CONFIG

  Copy the example and edit it:

      cp bootstrap.conf.example bootstrap.conf"

# shellcheck disable=SC1090
. "$CONFIG"

# --------------------------------------------------------------- helpers ----

# Read a multi-line config value into a newline-delimited list, dropping blank
# lines and surrounding whitespace. Keeps the config readable and indented.
clean_list() {
  printf '%s\n' "$1" \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
    | grep -v '^$' || true
}

# Field 1..n of a pipe-delimited line, trimmed.
field() {
  printf '%s' "$1" | awk -F'|' -v n="$2" '{ print $n }' \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

# ---------------------------------------------------------------- target ----

REPO="${REPO_OVERRIDE:-${REPO:-}}"
if [ -z "$REPO" ]; then
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || true)"
  [ -n "$REPO" ] || die "No repository given and the current directory is not a git repository.
  Set REPO in $CONFIG or pass --repo OWNER/NAME."
fi

REPO_OWNER="${REPO%%/*}"
PROJECT_OWNER="${PROJECT_OWNER:-$REPO_OWNER}"
PROJECT_TITLE="${PROJECT_TITLE:?PROJECT_TITLE must be set in the config}"

gh repo view "$REPO" >/dev/null 2>&1 || die "cannot see repository: $REPO"

printf '%sRepository%s      %s\n' "$C_BOLD" "$C_RESET" "$REPO"
printf '%sBoard%s           %s (owner: %s)\n' "$C_BOLD" "$C_RESET" "$PROJECT_TITLE" "$PROJECT_OWNER"
printf '%sConfig%s          %s\n' "$C_BOLD" "$C_RESET" "$CONFIG"
if [ "$CHECK_ONLY" -eq 1 ]; then
  printf '%sMode%s            check only, nothing will change\n' "$C_BOLD" "$C_RESET"
elif [ "$DRY_RUN" -eq 1 ]; then
  printf '%sMode%s            dry run, nothing will change\n' "$C_BOLD" "$C_RESET"
fi

# ----------------------------------------------------------------- board ----

heading "Project board"

PROJECT_NUMBER="$(
  gh project list --owner "$PROJECT_OWNER" --format json --limit 200 2>/dev/null \
    | jq -r --arg t "$PROJECT_TITLE" '.projects[] | select(.title == $t) | .number' \
    | head -n1
)"

if [ -n "$PROJECT_NUMBER" ]; then
  exists "$PROJECT_TITLE (#$PROJECT_NUMBER)"
elif [ "$DRY_RUN" -eq 1 ]; then
  would "board \"$PROJECT_TITLE\""
  note "later steps cannot be checked without a board"
else
  PROJECT_NUMBER="$(
    gh project create --owner "$PROJECT_OWNER" --title "$PROJECT_TITLE" \
      --format json | jq -r .number
  )"
  created "$PROJECT_TITLE (#$PROJECT_NUMBER)"
fi

PROJECT_URL=""
if [ -n "$PROJECT_NUMBER" ]; then
  PROJECT_URL="$(
    gh project view "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json \
      | jq -r .url
  )"
fi

# ---------------------------------------------------------------- fields ----
#
# Three fields, one job each. Lane is the load-bearing one — one lane, one seat.
# Owner records the bar the work needs. Seat is the slot, and on a repository
# where every agent pushes under a single account it is the ONLY thing that
# distinguishes them: assignees, reviewers and CODEOWNERS all collapse to one
# login. Do not build routing on anything else.

create_field() {
  local name="$1" options_raw="$2" options
  options="$(clean_list "$options_raw" | paste -sd, -)"

  if [ -z "$options" ]; then
    warn "$name — no options configured, skipped"
    return 0
  fi

  if [ -z "$PROJECT_NUMBER" ]; then
    would "field $name [$options]"
    return 0
  fi

  if gh project field-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" \
       --format json --limit 100 \
     | jq -e --arg n "$name" '.fields[] | select(.name == $n)' >/dev/null 2>&1; then
    exists "$name"
    FIELD_REUSED=1
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    would "field $name [$options]"
    return 0
  fi

  gh project field-create "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" \
    --name "$name" --data-type SINGLE_SELECT --single-select-options "$options" \
    >/dev/null
  created "$name [$options]"
}

heading "Board fields"
FIELD_REUSED=0
create_field "Lane"  "${LANES:-}"
create_field "Owner" "${OWNERS:-}"
create_field "Seat"  "${SEATS:-}"

# A field that already exists is left exactly as it is. gh has no command to add
# an option to an existing single-select field, and rewriting one would unstamp
# every card already carrying the old option — which is worse than a stale list.
if [ "$FIELD_REUSED" -eq 1 ]; then
  note "existing fields are left untouched; add missing options on the board itself"
fi

# ---------------------------------------------------------------- labels ----
#
# Labels filter the issue list. They do NOT fill board fields — a card can carry
# every label and still render as unassigned on a lane board.

heading "Labels"

existing_labels="$(gh label list --repo "$REPO" --limit 300 --json name --jq '.[].name' || true)"

while IFS= read -r line; do
  [ -n "$line" ] || continue
  name="$(field "$line" 1)"
  colour="$(field "$line" 2)"
  desc="$(field "$line" 3)"
  [ -n "$name" ] || continue

  if printf '%s\n' "$existing_labels" | grep -Fxq "$name"; then
    exists "$name"
    continue
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    would "label $name"
    continue
  fi
  gh label create "$name" --repo "$REPO" \
    --color "${colour:-ededed}" --description "$desc" >/dev/null
  created "$name"
done <<EOF
$(clean_list "${LABELS:-}")
EOF

# ------------------------------------------------------------ milestones ----
#
# Disjoint, never nested. An issue belongs to exactly one milestone, so a
# release milestone that "contains" the others reports a falsely small progress
# number — its children hold all the tickets. The release is the union of these
# closing.

heading "Milestones"

existing_milestones="$(
  gh api "repos/$REPO/milestones?state=all&per_page=100" --jq '.[].title' 2>/dev/null || true
)"

while IFS= read -r line; do
  [ -n "$line" ] || continue
  title="$(field "$line" 1)"
  desc="$(field "$line" 2)"
  [ -n "$title" ] || continue

  if printf '%s\n' "$existing_milestones" | grep -Fxq "$title"; then
    exists "$title"
    continue
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    would "milestone $title"
    continue
  fi
  gh api "repos/$REPO/milestones" -X POST \
    -f title="$title" -f description="$desc" -f state=open >/dev/null
  created "$title"
done <<EOF
$(clean_list "${MILESTONES:-}")
EOF

# -------------------------------------------------------------- workflows ----
#
# The honest part. Both of these are built-in board workflows and neither is in
# the REST API or the GraphQL schema, so there is nothing to call. They are two
# toggles and they prevent a failure that otherwise recurs weekly, so the script
# ends by naming them rather than quietly leaving the board half configured.

heading "Two workflows to switch on by hand"

cat <<EOF
  GitHub exposes no API for board workflows. These are the only manual steps.

  ${C_BOLD}1. Auto-add to project${C_RESET}
     Board -> ... -> Workflows -> "Auto-add to project" -> Edit
     Filter: is:issue is:open        Then: Enable

     Without this, tickets filed from the command line — which is how agents
     file them — exist in the repository and on no board. This is the single
     most common reason a board and an issue list silently disagree.

  ${C_BOLD}2. Item closed -> Done${C_RESET}
     Board -> ... -> Workflows -> "Item closed" -> Edit
     Set Status: Done                Then: Enable

     Cards then move themselves, so the board stays true without a sweep.
EOF

if [ -n "$PROJECT_URL" ]; then
  printf '\n  Board: %s\n' "$PROJECT_URL"
  printf '  Workflows: %s/workflows\n' "$PROJECT_URL"
fi

# ------------------------------------------------------------------ next ----

heading "Then"

cat <<'EOF'
  * Stamp Lane, Owner and Seat at creation. A ticket with a blank Seat belongs
    to nobody and nobody notices it exists.
  * One lane, one seat, always. Move whole lanes between seats, never single
    tickets — re-labelling one ticket creates the collision lanes prevent.
  * Files that belong to no lane — central config, the entry point, the router —
    are not covered by lanes at all. Serialise those with a blocked-by
    dependency; nothing else will catch them.
  * Compare the repository's open issue count against the board's. Filtering
    issues by project only counts issues already on the board, so two filtered
    views can agree while a batch of tickets sits off the board entirely.
EOF

printf '\n'
