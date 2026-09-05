# CLAUDE.md — lanekeeper

Project instructions and build state. Read this first; it exists so each session stops
re-deriving the same decisions from the issue tracker.

Repository: `kish21/parallel-agents` · package `lanekeeper` · published on PyPI at v0.7.2.

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
| 3 | Separate a dependency from a collision; fuse or share | #39 | **frozen** — see the later session below |
| 4 | Create the board and fill Lane, Owner, Seat on every card | #40 | **done** — `lanekeeper board`, `board.read`, `spawn --ticket`; unverified against a live board |
| 5 | Ask how many agents exist and how many to activate now | #33 | not started — `spawn --ticket` covers the per-agent half |
| 6 | Prepare a desk per activated agent | #41 | **done** — `open`, `spawn --open` |
| 7 | Enforce the boundary on every change (`check`, the PR gate) | #31, #32 | **done** — `check --write-workflow` |

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

## Session of 2026-09-01 (later the same day): the review, and the re-ordering

A thorough review of the code (three subsystem reviews plus probes against real
repositories) reached one verdict: **the idea is right; the build order was wrong.** The
enforcement core had five fail-open holes, nothing ran `validate` automatically, and the
guided path was three steps of heuristics away from anything a user could see.

**Fixed this session** (`tests/test_gate_holes.py` reproduces each escape first):

- A rename out of another lane reported only its destination → both sides reported,
  `--no-renames` on the diff.
- A base branch git could not diff produced an empty change list → `GitError`, and
  `validate`/`check` fail with "nothing was checked".
- `.lanekeeper/` was wholly exempt, including `config.yaml` and the cards → only the
  runtime subdirs are exempt (`paths.ignored_prefixes`); the policy files are
  `paths.policy_paths()` and denied to every lane (`LaneViolation.reason == "policy"`).
- `allow: []` allowed everything → `InvalidLaneError` at load.
- `secrets/` matched nothing in a lane → a trailing slash means `/**` in `match_glob`.
- `state._read_json` read a damaged ledger as empty → `StateCorruptError`, caught once
  in `main()`. The id counter is still lenient (it is reconciled against state).
- `cleanup` ignored the `y` answer → `y` now means `--force`.

**Built this session:**

- `lanekeeper check` (`src/lanekeeper/check.py`) — the lane engine as a PR gate: a lane
  name or `--labels-json`, a base ref, no agent state. `--write-workflow` writes
  `.github/workflows/lanekeeper-gate.yml`, which reads a `lane: <name>` label and fails
  closed without exactly one. `policy` is a reserved lane name: a change under it may
  touch only the policy files. **This is step 7 (#31/#32), done first because it is
  the product.**
- `lanekeeper open` and `spawn --open` (`src/lanekeeper/desk.py`) — the desk (#41).
  `editor.command` in config, default `code`. `.lane` now carries `TASK`, `ALLOW`, `DENY`.

**The new order, decided with the user:** 1. ~~Gate holes~~ 2. ~~`check` in CI~~
3. ~~Editor launch~~ — all merged in PR #48.

---

## Session of 2026-09-01 (third): the board, the hand-off, the advisor — v0.7.0

Everything below shipped together as v0.7.0. The board reading is built against `gh`'s
documented JSON through an injected runner, **not against a live board** — this
environment has no `gh` and no `project` scope. First thing to do on a real machine:
`lanekeeper board --dry-run`, then `lanekeeper board`, then `board --show`.

- **`lanekeeper board` (#40)** — `src/lanekeeper/board.py`. `bootstrap.sh` now lives in
  `src/lanekeeper/scripts/` (package data); the root `bootstrap.sh` is a wrapper. Its
  inputs are generated into `.lanekeeper/board.conf` from `config.yaml` (lanes) and the
  capability cards (seats). `bootstrap.conf.example` is gone. `BoardReader.cards()`
  reads Lane/Owner/Seat by ticket number; `config.board` holds title, owner, `read`,
  `command`. `spawn --ticket N` takes lane and seat from the card; `--lane` is no longer
  required by argparse but one of the two must be given.
- **Hand-off** — `src/lanekeeper/handoff.py`. `start` opens `claude "/vision"`
  interactively when step 1 says `NEEDS_PLAYBOOK` and stdin/stdout are a tty (or
  `--handoff`); `--no-handoff` disables. `config.intake.playbook` = command, steps, auto.
  Not a headless call on purpose: the skills are conversations.
- **Advisor** — `src/lanekeeper/divide/advisor.py`. `divide.advisor: claude-code` runs
  `claude -p <prompt> --output-format text`, parses a JSON `{"paths": [...]}`, keeps only
  paths matching a tracked file, and is asked only about `draft.unplaced`. Result lands in
  `needs_paths` with `PathSource.PROPOSED` → commented-out in the draft. An
  `AdvisorError` becomes one note printed by the CLI. **The gate never sees it.**
- **Decision on `divide`/`intake`: keep both, and make `divide` real.** `divide --confirm`
  now also writes the lanes into `config.yaml` (`draft.apply_to_config`), creating the
  file from defaults if absent; `claims: unowned` lanes are exempt from the no-paths check
  and left out of the policy with a printed line. `collision._segment_may_match` compares
  two wildcard segments properly; `examples/feature-lanes.yaml` confirms clean against
  its own tree (`tests/test_divide_applies.py`). The coverage half of `intake` is unchanged
  and still the weakest part of the tool; with the board as the source of Lane, the next
  candidate for deletion is `intake.coverage`, not `divide`.
- Step 3 (#39, dependency vs collision) is still not built.

**Blockers:** none.

---

## Session of 2026-09-01 (fourth): the first real project — v0.7.1

Ran the published v0.7.0 end to end on `kish21/mini-issue-tracker` (a React app with a
product-playbook `PRODUCT.md` and three product-playbook tickets), with `gh` replaced by
a stand-in serving the real issues. **v0.7.0 could not get past step 1** on it. Every
fix below is pinned by a test and listed in CHANGELOG `[v0.7.1]`:

- Coverage `GAPS` is advisory now (`gate._verdict_for`); nested bullets are not
  features (`spec.extract_features`); the `NO_LABELS` flag is gone.
- `divide.boundary` reads product-playbook's *📁 Target Modules & Exact File Names*
  (emoji-prefixed heading, checkbox + bold label + backticked path), skips `---`.
  `path_headings` default gained `target modules`, `target files`.
- Solo lanes are named by the ticket tag (`names.tag`, `[FEAT-02]` → `feat-02`).
- The draft offers a `shared:` block for files two entries claim (`draft._shared_candidates`).
- `divide --confirm` on a fresh project runs `cli._first_time_setup` (cards, gitignore).
- `.gitignore` no longer ignores `.lanekeeper/capabilities/` (`paths.gitignore_lines`).
- `check`: repo root from git; `policy` lane also allows `.gitignore`, `lanes.yaml`,
  the gate workflow (`check.policy_lane_paths`); missing-policy message says why.
- `cleanup` deletes a fully merged agent branch (`WorktreeManager.delete_branch`).
- README: five-minute opening from the trial's real output; reference below.
  `docs/legacy/` holds the six process docs and `EXAMPLES.md`; `init` says its lanes
  are layers.

**What the trial proved in real CI:** on `mini-issue-tracker` PR #8 (agent branch,
label `lane: feat-02`) the gate failed closed before the label and **passed after it**.
PR #7 (the policy, label `lane: policy`) fails until v0.7.1 is on PyPI, because the
workflow installs the published package. Neither PR is merged; that is the owner's call.
`verify` on PR #7 is the tracker's own gitleaks step failing on a shallow checkout —
not lanekeeper's.

**Still unverified:** `lanekeeper board` against a live GitHub project (no `gh` here).
**Known:** grouped lanes are still named from a shared path segment (`prompt` for
#1+#3); good enough, not great. `intake.coverage` remains a word match.

**Known local noise:** `test_ports` (×2) and `test_cleanup` fail on the user's Windows
machine on port-allocation assertions. Confirmed pre-existing on clean `main`; CI's
windows-latest is green. Not a regression — do not chase it.

---

## Session of 2026-09-02: the one-command path — v0.7.3

The user's question after the v0.7.2 trial: *why are we doing this, and will anyone
use it?* The honest answer given: the complaint is real (worktrees isolate the copy,
not the intent, so people using worktree tools still collide at merge), the gate is
the one thing nothing else does, and the adoption blocker is the setup cost — `start`,
`divide`, a draft, a board — before a person with an existing backlog gets anything.

**Built:** `lanekeeper spawn --ticket N` with no board. `src/lanekeeper/ticket.py`:
the ticket's own file list is the lane, named by its tag (`names.tag`) or `issue-N`,
written into `config.yaml` (`ensure_lane`, which also lets scoped seat cards into the
lane). No files → refused with the fix: `--allow <glob>` (repeatable, commas ok) or
`--propose` (runs `ClaudeCodeAdvisor` whatever `divide.advisor` says; the answer is
printed and used only on a tty `y` or `--yes`). An existing lane of that name is
reused, never rewritten. Collisions with other lanes (`collision.patterns_intersect`)
are reported, not blocked on. No `config.yaml` at all → one is written holding only
this lane plus `_first_time_setup`. The board is consulted only with `board.read:
true`; a ticket the board lacks falls back to the ticket. `IssueTracker.get_issue`
added (default scans the list; GitHub uses `gh issue view`). Tests:
`tests/test_spawn_ticket.py`; `test_board.py`'s spawn tests now set `board.read`.

**The tester one-pager** lives outside the repo as a Claude artifact (published this
session) and mirrors the README section *Already have a backlog? One command per
ticket*. It assumes 0.7.3 is on PyPI — the owner tags releases from the phone.

**Released:** 0.7.3 is on PyPI (PR #52, merge `e10ecaa`). The first v0.7.3 release tagged
the pre-merge commit and the publish workflow refused it on the VERSION check — delete
the release *and* its tag, then re-release with target `main`.

**Not done:** the live board check (still waits on tracker PR #7 and a
`LANEKEEPER_GH_TOKEN` secret); any outside tester.

---

## Session of 2026-09-02 (second): the tester sheet, run for real — v0.7.4

The user cannot run a terminal (mobile only), so **this session ran the tester sheet
itself** against a fresh clone of `kish21/mini-issue-tracker` on published 0.7.3, with
`gh` replaced by a stand-in replaying the repo's three real issues
(`scratchpad/trial/bin/gh`). The gate was right every time. The flow around it was not,
and both failures were nobody's mistake:

1. `check` inside the agent's worktree found no policy — `spawn --ticket` writes the
   policy in the main checkout and branches the agent from a commit without it.
2. The agent's first `git add -A` swept that uncommitted policy into its branch, where
   the gate denied it under an ordinary lane. Correct, and baffling.

Both fixed by saying more, never by loosening the gate: `WorktreeManager.main_worktree_root()`
lets `check` borrow the main checkout's policy (printing that it did, and that CI needs
it committed); `ticket.policy_is_uncommitted` drives a "commit the policy first" line in
`next_steps`, printed before the label line. Plus two cosmetics the run exposed: a branch
name ending in `-`, and "All 1 changed file stay". `tests/test_trial_findings.py`
reproduces all four against the released code (9 of 11 fail without the fix).

**Also proven on the real tickets:** the collision report is not theoretical — FEAT-02
and FEAT-03 both claim `src/domain/contracts.ts`, and `spawn --ticket 3` said so.

---

## Session of 2026-09-05: the deep-test protocol — v0.7.5

The user asked for a thorough test, written from a new user's point of view. Grounding
every expected output meant running every command against published 0.7.4 on the
mini-issue-tracker stand-in, which turned up four things away from the gate:

- `cleanup` without `--force` raised `EOFError` and printed a traceback when stdin had
  nothing in it. Now caught; the message names `--force`. **The tty test was wrong:**
  an answer piped in must still count (`test_gate_holes.TestCleanupHonoursTheAnswer`),
  so the fix is the `except EOFError`, never an `isatty` guard.
- Every worktree is "dirty" the moment it is created, because `spawn` writes `.lane`
  and `.env` into it — so `cleanup` always asked. `has_uncommitted_changes` now ignores
  bookkeeping files, and `remove_worktree` always passes `--force` to git past that
  guard (git refuses to remove a worktree over its own untracked files).
- `validate` and the missing-cards message recommended `lanekeeper init --force`, which
  would replace ticket-derived lanes with technology layers.
- `diff` counted bookkeeping files then hid them, so the total disagreed with the list.

Tests: `tests/test_new_user_findings.py` (5 of 6 fail on the released code).

**The deep-test protocol** is a second Claude artifact, separate from the 15-minute
tester sheet: 32 steps, ~1 hour, including a "try to slip something past it" part
(rename out of a lane, delete outside it, edit the policy from an ordinary lane, an
undeclared lane, an undiffable base). Both artifacts live outside the repo.

**Still not done:** the live board check; any outside tester; #39 (dependency vs
collision) remains deliberately frozen.

---

## Session of 2026-09-05 (second): the owner ran the protocol — v0.7.6

The owner ran the deep-test protocol himself, on Windows, on a real clone of
mini-issue-tracker, against published 0.7.5. **The gate was never wrong.** Eight
findings, all about what the tool says:

1–2. `status` and `doctor` both opened with "Run 'lanekeeper init' first" — the path
that writes technology-layer lanes. Fixed in `config.load_config`'s error, which is
where both got it. 3. `doctor` then offered `repair`, which cannot create a config
(`DiagnosticCheck(repairable=False)`). 4. The worktree folder appearing in the VS Code
sidebar reads as a fault; one line now says what it is and how to move it
(`worktree_dir`). 5. **The important one:** nothing said *how to do the work*. The
output was all bookkeeping — policy, label, gate — and a first-time user reached a
prepared worktree and stopped. `ticket.how_to_work` and `ticket.agent_prompt` now
print the three actions plus a paste-ready prompt carrying task and file list.
6. The agent read `.lane` by luck, not instruction — the prompt fixes that
deterministically. **Writing a `CLAUDE.md` into the worktree was tried and rejected:**
git's per-worktree `info/exclude` does not apply (the common dir's does), so the file
would either be committed and denied by the gate, or exempted as bookkeeping — which
would let an agent silently rewrite the project's own CLAUDE.md. 7. The "commit the
policy" warning I wrote in 0.7.4 **blamed the agent, and was wrong**: an uncommitted
policy is not visible in the worktree at all (pinned by a test). The hazard is the
person's own `git add -A` in the main checkout. 8. `check --write-workflow` writes a
file and checks nothing → **`lanekeeper install-gate`**, flag kept.

Tests: `tests/test_first_run_findings.py` (10 of 12 fail on 0.7.5). Two older tests
asserted the wording that changed and were updated.

**Also agreed, not built:** an opt-in `commands:` section (`frontend`, `backend`,
`auto`) proposed from `package.json` scripts and any Python manifest, started by
`open --run` on the agent's own ports. Default off — five agents auto-starting five
dev servers unasked is how a tool gets uninstalled.

**Windows note for the protocol:** on Windows Store Python, `pip install lanekeeper`
succeeds and `lanekeeper` is then not on PATH. `python -m lanekeeper.cli` works, or
add the user Scripts directory to PATH.

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
