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
| 2 | Divide the work: group where it groups, otherwise ask which tickets to hand out | #38 | **next — rewritten, see below** |
| 3 | Separate a dependency from a collision; fuse or share | #39 | not started |
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

## Session of 2026-09-01 (this one): the ticket form — PR #46

**Done.** PR #45 merged (#37 closed). #38 and #36 rewritten as comments. Then one
subtask: the ticket form stopped asking for a technology layer.

`Lane` was a dropdown of `interface / service / data / platform` — the model #23 and the
README reject, in the one place the user *has* to fill in. Now free text and **optional**;
`Allowed File Paths` is the **required** field in its place, in `bug.yml` too, which never
asked for it. Six files, not two: `templates/issue-template-*.yml` ship to users and had
drifted, `CONTRIBUTING.md` taught the enum before the form, `05-github-mechanics.md` told
readers to *build* the dropdown. Design doc:
[`docs/ticket-template.md`](docs/ticket-template.md); guard:
`tests/test_issue_template.py`. No `src/` change.

**PR #46 does not say `Closes #23`** — deliberately. `layout.py`'s `ROLE_BY_DIR_NAME` is
the other, larger half of #23 and is #38's to displace. The tickets stop teaching layers;
the detection has not.

---

## NEXT SESSION PLAN — #38, step 2: divide the work

**Do this and only this.** It is the step the whole tool rests on.

**How to resume**

1. `git checkout main && git pull` — PR #46 should be merged first.
2. Read the **#38 rewrite comment**, then `docs/ticket-template.md` (the input contract),
   then `docs/start-step1-intake.md` for the shape step 2 inherits.
3. Step 2 is handed an `IntakeResult` (`lanekeeper.intake.models`). **Do not re-read the
   tracker from step 2.**
4. Write `docs/start-step2-divide.md` (exit criteria, interaction map, test plan)
   **before** coding, and confirm it with the user.

**What #38 must get right**

- Feature slices, never backend/frontend. `layout.py`'s `ROLE_BY_DIR_NAME` must stop
  being the default (#23) — this is where that happens.
- Two sources: the tickets on a new project, the **code** on a half-built one. Where both
  exist use both and say which source each came from. If the user is unsure, go and read
  the code — that is the fallback, not an error.
- **Propose, then confirm.** Never a blank form; never a silent decision.
- A backlog that does not group produces a **pick list**, not a stop.
- Every ticket lands in exactly one entry or an explicit "could not place these" list.
- Report any two picks touching the same files, before writing the lane file (#34).
- Run against MarkVid, the proposal should be recognisably its 17 lanes.

**Two things this session found and left for #38** (both in `docs/ticket-template.md` §7)

- `intake.quality`'s `broad_ticket_areas` defaults to **3**, but a correct feature slice
  spans `backend` + `frontend` + `tests` — exactly 3. The default sits on the boundary of
  the model the form now teaches. Measured: current placeholders do not trip it, one more
  line does. It is config; decide what it should be now a lane spans the stack by design.
- **Asking for missing file paths is #38's job.** A draft of `bug.yml` promised the filer
  would "be asked about" — nothing does that, and `quality._file_hints` scans the whole
  body, so a stack trace in the Evidence field supplies a path and no flag is raised at
  all. The promise was cut rather than faked.

**Constraints that carry over**

- **Never tell the user to restructure their repository.** Lanes are globs and can carve
  a feature slice out of a messy tree without moving a file. At most *mention* that a
  tidier layout would sharpen things. Anything stronger locks out the legacy projects
  that need this most. `tests/test_issue_template.py` guards this in the form's wording.
- **The gate never calls a model.** Enforce with rules, propose with intelligence. A
  verdict that changes between runs is not a guarantee. Any advisor sits behind
  `advisor: none` by default.
- `check` is #31's name. Do not reuse it.
- No hardcoding: sources, paths and thresholds are config; externals behind a provider
  interface (`src/lanekeeper/trackers/`).
- Plain language in every user-facing string. `intake/presenter.py` and
  `test_intake_language.py` are the pattern to copy.

**Blockers:** none. #38 depends on #37 (merged) and on PR #46 (open).

**Known local noise:** `test_ports`, `test_cleanup` and `test_state_lock` fail on this
Windows machine with `os.replace` `PermissionError`. Confirmed pre-existing on clean
`main`; CI's windows-latest is green. Not a regression — do not chase it.

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
