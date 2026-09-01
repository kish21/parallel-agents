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

**This session (#37, step 1 of the #36 umbrella):** `lanekeeper start` and
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
| 1 | Is the work written down, and does it cover the features? | #37 | **done this session** |
| 2 | Group the features into modules — from the issues, or from the code | #38 | **next** |
| 3 | Separate a dependency from a collision; fuse or share | #39 | not started |
| 4 | Create the board and fill Lane, Owner, Seat on every card | #40 | not started |
| 5 | Ask how many agents exist and how many to activate now | #33 | not started |
| 6 | Prepare a desk per activated agent | #41 | not started |
| 7 | Enforce the boundary on every change (`check`, the PR gate) | #31, #32 | not started |

---

## NEXT SESSION PLAN — #38, step 2: group the features into modules

**Do this and only this.** It is the step the whole tool rests on.

**How to resume**

1. `git checkout main && git pull` — #37's PR should be merged first.
2. Read `docs/start-step1-intake.md` for the shape step 2 inherits, then issue #38.
3. Step 2 is handed an `IntakeResult` (`lanekeeper.intake.models`) — the issues, the
   product description that was read, and which features matched which tickets. That is
   the contract; do not re-read the tracker from step 2.
4. Write `docs/start-step2-modules.md` (exit criteria, interaction map, test plan)
   **before** coding, and confirm it with the user.

**What #38 must get right**

- The proposal is **feature slices, never backend/frontend**. `layout.py`'s
  `ROLE_BY_DIR_NAME` must stop being the default (#23).
- Two sources: the issues on a new project, the **code** on a half-built one. Where both
  exist, use both and say which source each module came from. If the user is unsure,
  go and read the code — that is the fallback, not an error.
- **Propose, then confirm.** Never a blank form; never a silent decision.
- Every issue lands in exactly one module or in an explicit "could not place these" list.
- Confirmed output is written to the lane file (#34) before #39 runs.
- Run against MarkVid, the proposal should be recognisably its 17 lanes.

**Constraints that carry over from this session**

- **Never tell the user to restructure their repository.** Lanes are globs and can carve
  a feature slice out of a messy tree without moving a file. Propose over the tree as it
  stands; at most *mention* that a tidier layout would sharpen things. Anything stronger
  locks out the legacy projects that need this most.
- `check` is #31's name. Do not reuse it.
- No hardcoding: sources, paths and thresholds are config; externals sit behind a
  provider interface.
- Plain language in every user-facing string — the user should not need to know what a
  lane or a worktree is. `intake/presenter.py` and `test_intake_language.py` are the
  pattern to copy.

**Blockers:** none. #38 depends only on #37, which is done.

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
