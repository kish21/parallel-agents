# CLAUDE.md — lanekeeper

Project instructions and build state. Read this first; it exists so each session stops
re-deriving the same decisions from the issue tracker.

Repository: `kish21/parallel-agents` · package `lanekeeper` · published on PyPI at v0.6.0.

---

## What this product is

**Lanekeeper runs a department of agents.** The user picks 2–10 coding agents and
lanekeeper keeps them out of each other's way: one worktree, one branch, one port range
and one set of code boundaries each, with a mechanical gate that fails a change which
leaves its boundary.

Its companion is **product-playbook**, which makes the work. The division of labour is
firm and worth restating whenever a feature blurs it:

> **product-playbook writes the work down. Lanekeeper divides it up.**
> Lanekeeper never invents what a product should do. When the work is not written down,
> it hands off to `/vision`, `/scope`, `/plan` and stops.

Capability comes from the harness (Claude Code and friends). Seats are numbers, not
personalities.

## The one product decision that keeps getting re-derived

**A lane is a feature slice, not a tech layer.** `checkout` — its service, its schema,
its API route, its React page and its tests — not `backend`. An ordinary ticket touches
five files across four layers; under a layer split that is one ticket against four
lanes, and every ticket becomes a four-way escalation.

The tool's own `layout.py` still detects backend/frontend/data/platform and teaches the
opposite. That is issue #23, and it is a known contradiction between what the README
argues and what `init` does.

## The `start` vs `init` decision (2026-09-01, settled)

`lanekeeper start` is the single guided entry point. It runs a **pre-flight FIRST** —
is the work written down, does it cover the features, can modules be identified — and
hands off to product-playbook when it is not. Only after that does it do the
config-writing that `init` does today, then the board (#40) and the desks (#41).

**`init` is not rewritten and not deleted.** It stays exactly as it is, demoted to a
low-level escape hatch for someone who already knows their lanes. Nobody on v0.6.0
breaks. Recorded on #30, #36 and #37.

---

## Build state

**Shipped (v0.6.0, on PyPI):** `init`, `spawn`, `validate`, `diff`, `status`,
`inspect`, `logs`, `stop`, `restart`, `repair`, `doctor`, `declare`, `cleanup`; the lane
engine, capability gates, port allocation, per-agent `.env` generation, worktree
lifecycle. Verified against a real full-stack application.

**Merged since:** the v1 lane-file schema (#34, PR #44) — `lanes.yaml` documented in the
README with a fully worked 17-lane example in `examples/feature-lanes.yaml`. Nothing
reads that file yet; it is the contract steps 2–4 will write to.

**Merged (#46):** the ticket form stopped asking for a technology layer. `Lane` is free
text and optional; **`Allowed File Paths` is the required field**, in `bug.yml` too.
Design doc: [`docs/ticket-template.md`](docs/ticket-template.md).

**Merged (#37, step 1 of the #36 umbrella — PR #45):** `lanekeeper start` and
`lanekeeper intake` — the pre-flight gate. Design doc:
[`docs/start-step1-intake.md`](docs/start-step1-intake.md).

- `src/lanekeeper/trackers/` — the `IssueTracker` provider interface, with
  `GitHubIssuesTracker` (shells `gh`, injected runner) and `NullTracker`. Selected by
  `intake.tracker` in config; unknown names fail closed.
- `src/lanekeeper/intake/` — `spec` (PRODUCT.md → docs → nothing), `coverage`
  (COVERED / GAPS / **CANNOT_JUDGE**), `quality` (tickets that would make grouping a
  guess), `gate` (the verdict), `record` (fingerprinted, resumable), `presenter` (every
  user-facing string, in plain language, guarded by a test).
- `config.yaml` gains an `intake:` section, fully defaulted so pre-v0.7 configs load
  unchanged.
- `start` stops after step 1 and says so; steps 2–7 are not built.

## The v0.7 milestone (#36) — where each step stands

| Step | What it does | Issue | State |
|---|---|---|---|
| 1 | Is the work written down, and does it cover the features? | #37 | **done — PR #45, merged** |
| 2 | Divide the work: group where it groups, otherwise ask which tickets to hand out | #38 | **done — PR #47, open** |
| 3 | Separate a dependency from a collision; fuse or share | #39 | **next** |
| 4 | Create the board and fill Lane, Owner, Seat on every card | #40 | not started |
| 5 | Ask how many agents exist and how many to activate now | #33 | not started |
| 6 | Prepare a desk per activated agent | #41 | not started |
| 7 | Enforce the boundary on every change (`check`, the PR gate) | #31, #32 | not started |

---

## The design decisions of 2026-09-01 that #38 was rebuilt around

Posted on [#38](https://github.com/kish21/parallel-agents/issues/38#issuecomment-5494124416)
and [#36](https://github.com/kish21/parallel-agents/issues/36#issuecomment-5494126576) so
they stop being re-derived. Read the #38 comment, **not** its description, which is stale.

**The prerequisite is the ticket template, not a `PRODUCT.md`.** A ticket filed through
`.github/ISSUE_TEMPLATE/task.yml` already names the files it touches, so it carries its
own boundary and nothing needs comparing against a spec. Coverage-against-a-document is
a **greenfield question only** — demanding a `PRODUCT.md` from a project that already has
a backlog is asking the user to write a document to satisfy a checker. #37 already
behaves correctly here (`CANNOT_JUDGE` → `NEEDS_TIDYING` → `--take-as-is`); nothing in it
needs undoing.

**When lanekeeper cannot group the tickets, it ASKS.** It never blocks and never guesses.
It shows the tickets and asks which ones to hand to a separate agent — the user knows the
product, we do not. Three consequences:

- **A lane can be a SINGLE TICKET**, bounded by that ticket's Allowed File Paths.
  Grouping into modules is the nice case, not the required one.
- **The mechanical collision check moves into #38**, earlier than #39 planned: he picks,
  lanekeeper says whether any two picks touch the same files, he adjusts. A set
  intersection over globs — no model, no judgement. #39 keeps the harder question
  (dependency or collision; fuse or share a zone).
- **A picked ticket with NO file paths has nothing to enforce.** Ask for the paths or
  propose some for confirmation; never hand over an agent whose safety guarantee
  quietly does not exist.

---

## Session of 2026-09-01 (this one): #38, step 2 — PR #47

**Done.** `lanekeeper divide` — the whole of step 2. Design doc:
[`docs/start-step2-divide.md`](docs/start-step2-divide.md), confirmed before any code
was written.

- `src/lanekeeper/divide/` — `boundary` (reads **only** the Allowed File Paths section),
  `names` (a feature name out of a path — the replacement for `ROLE_BY_DIR_NAME`),
  `codebase` (feature slices read from the tree), `grouping`, `collision` (a set
  intersection over globs), `draft` (propose → the user edits → `--confirm`),
  `proposal`, `presenter`, `models`.
- `config.yaml` gains a `divide:` section, fully defaulted. `advisor: none` is the only
  accepted value and any other **fails the load** rather than being ignored.
- `IntakeResult` now carries the tickets step 1 read — runtime only, never recorded,
  re-attached on a resumed run. Step 2 does not read the tracker.
- `intake.thresholds.broad_ticket_areas` default **3 → 5** (a feature slice spans
  backend + frontend + tests by design).

**The interaction, settled with the user:** draft file plus `--confirm`, not an
interactive picker. `--redraft` replaces a draft the user has edited; `--force` replaces
an existing `lanes.yaml`. Neither is ever done silently.

**What the worked-example run actually recovered** (the MarkVid stand-in, since MarkVid
is not on this machine): 9 of the example's 17 lane names exactly, 4 more as the head
word of a compound name — 13 of 17. The 4 missed are the ones the example itself calls
residue, and a test asserts they are **not** invented.

**#23 is not closed.** The guided path no longer goes near `layout.ROLE_BY_DIR_NAME`;
`init` still uses it. That half is a separate session with real blast radius on v0.6.0.

---

## NEXT SESSION PLAN — #39, step 3: dependency or collision?

**How to resume**

1. `git checkout main && git pull` — PR #47 should be merged first.
2. Read `docs/start-step2-divide.md` §5 (what step 2 already answers) and the #39 issue.
3. Step 3 is handed a `DivisionProposal` (`lanekeeper.divide.models`) whose `overlaps`
   are already computed. **Do not re-run the mechanical check** — extend it.
4. Write `docs/start-step3-collisions.md` before coding, and confirm it.

**What #38 already did that #39 was going to**

The mechanical half is done and shipped: `divide.collision` reports whether two entries
touch the same files, with the file that proves it, and marks the weaker
`patterns-only` case as weaker. `deny` and shared zones are honoured. #39 keeps the
question that is actually hard: **is an overlap a dependency or a collision, and is the
answer to fuse the two entries or to declare a shared zone with a steward?**

**Two things this session found and left for #39**

- `collision._answered_by` is approximate: a `deny` or shared pattern intersecting both
  sides is taken to cover the region they share. It only ever suppresses the structural
  finding, never one proved by a real file, and it is documented as approximate — but
  #39 owns the exact answer if it needs one.
- The `wider_paths` offer (a ticket named files one by one; the area they sit in is
  offered as commented lines) is the seam where "fuse or share" would naturally be
  proposed.

**Constraints that carry over**

- **The gate never calls a model.** `divide.advisor` exists, defaults to `none`, and any
  other value fails the config load. Keep it that way.
- **Never tell the user to restructure their repository.** Guarded by
  `test_divide_language.py::test_no_case_tells_the_user_to_rearrange_their_project`.
- Plain language in every user-facing string; the vocabulary guard covers every rendered
  case and treats a file name as a name, not a word.
- `check` is #31's name. `divide` is step 2's.
- No hardcoding: word lists, headings, thresholds and paths are all config, and the two
  configured paths are checked to stay inside the project.

**Blockers:** PR #47 must merge first.

**Known local noise:** `test_ports` (×2) and `test_cleanup` fail on this Windows machine
on port-allocation assertions. Confirmed pre-existing on clean `main`; CI's
windows-latest is green. Not a regression — do not chase it.

---

## Working conventions in this repository

- **Tests are `unittest` classes run under pytest.** Helper imports use
  `sys.path.insert(0, str(Path(__file__).resolve().parent))` before
  `from _cli_harness import ...` — follow the existing files.
- Run the suite with `PYTHONPATH=src python -m pytest tests/ -q`. The end-to-end tests
  spawn real subprocesses and are slow; the full run takes a few minutes.
- Never let a test touch the network or require `gh` to be installed. Inject a fake at a
  seam — `_intake_fakes.FakeTracker`, or `cli.get_tracker`.
- Filesystem layout goes through `lanekeeper.paths`, never a literal `.lanekeeper`.
- Every path lanekeeper writes lives under `paths.home()`, which `.gitignore` already
  excludes except for `config.yaml`.
- Comments explain **why**, in the voice of the surrounding code. The codebase argues
  with itself about design decisions in its docstrings; match that.
- Branch → PR → squash-merge. **Never `gh pr merge --admin`**, ever, including when CI
  is red or missing; stop and report what is blocking instead.
- One subtask per session. Finish with `/code-review`, a confidence score against the
  issue's definition of done, a PR saying `Closes #N`, and an update to this file.
