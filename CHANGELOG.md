# Changelog

All notable changes to the `parallel-agents` framework and scaffolding will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v0.4.0] - 2026-08-31

Usability release, from walking the tool as a first-time user rather than reviewing the
code. Two of the three problems that walkthrough found were defects, not preferences.

### Security

- **Modified files had their paths truncated, letting edits bypass lane and gate checks.**
  `get_changed_files` called `line.strip()` before slicing `line[3:]` out of
  `git status --porcelain`. That format is `XY<space>PATH` with position-significant
  status columns, and an unstaged edit reads `" M path"` — so stripping removed the
  leading space and the slice took the first character of the path with it.
  `secrets/prod.pem` was reported as `ecrets/prod.pem`, which matched no lane or gate
  pattern. **Creating** a file in a denied directory was blocked; **editing or deleting**
  one already there was not. Newly created files are reported as `"?? path"`, with no
  leading space, which parsed correctly — so the entire test suite, which only ever
  created files, passed over this. Both git queries now use `-z`, which also fixes paths
  containing spaces or non-ASCII characters and correctly skips a rename's source path.

### Added

- **`init` derives lanes from the repository's actual layout.** The stock lanes assume
  `backend/`, `src/backend/`, `frontend/`, `web/`; on a normal project they matched
  nothing, so a new user's first `validate` reported legitimate work as out-of-lane.
  Detection reads git-tracked files, treats container directories (`src/`, `packages/`,
  `apps/`) as transparent, classifies each directory by name and then by file-extension
  majority, gives root-level files to `platform`, and generates mutually exclusive deny
  lists so one lane means one owner. Measured coverage across four realistic layouts
  (Python src-layout, Django, Next.js, monorepo): 100%, against 0–40% for the stock lanes.
- **`init` reports lane coverage** and warns when the configuration matches little of the
  repository, or when only one lane exists — the latter being the point of the project's
  first thesis: parallel agents scale with separable lanes, not with agent count.
- **`init --generic`** opts out of detection and keeps the starter lanes.

### Changed

- **The out-of-lane error now names the likely cause.** When no declared lane would accept
  a path, the error says the lanes may not match the project and points at `config.yaml`,
  instead of only reporting the file — which sent users hunting through their diff rather
  than their configuration.

### Testing

- 139 tests (from 108). `test_changed_files.py` (16) covers modified, staged, untracked,
  deleted, renamed, spaced and non-ASCII paths, the porcelain parser directly, and the
  security consequence; it is verified to fail against the previous implementation.
  `test_layout_detection.py` (15) pins full coverage on four realistic layouts, container
  transparency, mutual exclusivity, build-output exclusion, and that a legitimate edit
  validates cleanly end to end.

## [v0.3.0] - 2026-08-31

Implements capability gates — the second of the two theses in `PLAN.md`, specified in
`03-orchestration.md` since the first commit and never enforced. Also fixes a second
fail-open found while building it.

### Added

- **Capability cards are now load-bearing.** A seat's card declares its capabilities in
  the three states from `03-orchestration.md` (`native` / `author-required` /
  `unavailable`), the lanes it may enter, and paths forbidden to it. Cards live in
  `.parallel-agents/capabilities/<seat>.json` and are committed, like the lane policy.
- **`capability_gates` in `config.yaml`** maps path patterns to the capability they
  require. This is what turns a rating into an enforceable rule — the mechanical form of
  the instruction in `01-working-agreement.md` to stop when a change touches money, auth,
  tenant isolation, or a migration. Defaults gate auth/payments/billing/tenant/secrets
  paths on `security_review`, and migration paths on `database_migrations`.
- **`validate` enforces the gates.** `native` passes; `author-required` passes only if a
  quality command declaring `satisfies: <capability>` ran and exited 0; `unavailable` is a
  hard stop with a non-zero exit. A seat rated unavailable for security review can no
  longer get a green validate on auth code, even when the file is inside its lane.
- **`parallel-agents declare <agent>`** generates the PR template's mandatory Gate
  Declaration from recorded state — seat, harness, ratings, gates triggered, and each
  quality command with its real exit code. Previously an honour-system form a human typed.
- **Quality commands may declare `satisfies:`**, which is what makes `author-required`
  operational. Plain string commands still parse, so existing configs are unaffected.
- **`doctor` checks card health**: gates configured with no cards, an agent whose seat has
  no card, a card scoping a lane that does not exist, a gate no card rates, and a lane no
  seat may enter.
- **`init` writes starter cards** for SR1/SR2/JR1/JR2. Junior seats are deliberately
  restricted, so the gates have something to bite on immediately.

### Security

- **`LaneEngine.match_glob` could not match `**/x/**` patterns.** It short-circuited on
  any pattern ending in `/**` and fell back to a prefix comparison, so a pattern that both
  began with `**/` and ended with `/**` matched nothing at all. A lane declaring
  `deny: ["**/secrets/**"]` silently denied nothing, and `src/secrets/prod.pem` validated
  as in-lane. Replaced with a segment-aware translator: `**` spans whole path segments,
  `*` and `?` never cross a separator, and regex metacharacters in patterns are literal.

### Changed

- **`spawn --seat` is a real lookup.** The `"SR1" if "senior" in name.lower() else "JR1"`
  heuristic is gone. An undeclared seat, or a seat whose card excludes the requested lane,
  is rejected before anything is provisioned.
- `validate` output now shows a Capability Gates section listing the gates evaluated, the
  seat's rating, and the file that triggered any block.

### Testing

- 108 tests (from 70), green on Python 3.10–3.13 locally and 3.9–3.13 plus macOS and
  Windows in CI.
- `test_capability_gates.py` (28 tests) covers all three states, the author-required
  script contract, `forbidden_paths` precedence, lane-scope enforcement, and four
  distinct fail-closed paths: unknown seat, missing card, unrated capability, and a
  passing-but-untagged command not satisfying a gate.
- `test_glob_matching.py` pins the matcher, including that `**/auth/**` must not match
  `src/authentic/`, and that a recursive deny pattern actually denies.

## [v0.2.0] - 2026-08-30

Hardening release. Two defects allowed the tool to report unsafe work as safe; both are
fixed, and both are now pinned by regression tests that fail against the old behaviour.

### Security

- **Lane enforcement now fails closed.** An agent whose lane was not declared in
  `config.yaml` was previously validated against a substituted empty allow/deny policy,
  which permits every path. A single typo (`--lane backedn`) therefore disabled lane
  enforcement entirely, and `validate` printed *"VALIDATION PASSED: PR is safe to submit
  and merge"* for an agent that had written to `secrets/` and `.github/workflows/`.
  `spawn` now rejects an undeclared lane before provisioning anything, and `validate` and
  `diff` refuse an agent whose lane is no longer declared. There is no permissive fallback.
- **Generated `.env` and `.lane` files are injection-proof.** Values were interpolated into
  `KEY="{value}"` with no escaping, so a task description containing a quote or a newline
  corrupted the file and could inject arbitrary lines — including commands — into a file
  that is routinely `source`d. All values are now POSIX single-quoted and normalised to a
  single line; config-derived keys are coerced to valid environment variable names.
- **`init` now writes ignore rules.** Agent worktrees live inside the repository, so
  without them an agent running `git add -A` would sweep every other agent's worktree and
  the shared state files into its own commit. Runtime state is ignored; the lane policy
  (`config.yaml`) stays tracked, because it is the team's shared contract.

### Fixed

- **Port allocation rollback destroyed valid reservations.** On a partial allocation
  failure the allocator called `release_ports(agent_id)`, but nothing had been persisted
  yet — so it released the agent's *existing* ports from an earlier successful allocation,
  freeing ports the agent was still serving on.
- **Port conflict detection did not exist.** `audit_ports` hardcoded `conflicts = []` and
  never called `is_port_in_use`, so the ledger drift and occupied-port detection described
  in the README was never performed. Both are now implemented: ledger/agent-state
  disagreement is reported as a conflict, and an orphaned port that is still bound is
  reported as a leaked server.
- **Concurrent spawns raced on git.** `git worktree add` mutates shared repository state
  and is not safe to run concurrently against one repository. It is now serialised under a
  dedicated git lock, held separately from the state lock so that `status` and `validate`
  no longer block behind slow git operations.
- **`StateLock` serialised unrelated locks.** The in-process `RLock` was a single class
  attribute shared by every instance, so independent locks — different repositories, or
  the state lock and the git lock — blocked each other. Locks are now scoped per lock file.
- **`validate` failed without saying why.** Failure modes that produce no per-file
  violation (an undeclared lane, a missing worktree) printed only "VALIDATION FAILED". The
  error list is now always shown.
- `audit_ports` declared a `Dict[str, Any]` return type without importing `Any`.
- Git errors reported only the last line of stderr, which is usually git's progress output
  rather than the actual failure.

### Changed

- **The benchmark reports measured results.** It previously printed a fixed
  "0 collisions / 100% detection" summary regardless of the statistics it had just
  collected, so a regression would have been reported as a clean run. It now reports what
  it measured and exits non-zero on any collision, leak, or undetected violation.
- **CI runs the real matrix.** Python 3.9–3.13 on Linux plus macOS and Windows smoke jobs
  (the locking layer has separate POSIX and Windows paths), byte-compilation, a
  VERSION/`pyproject.toml` consistency gate, and the benchmark as a gating job. The stale
  hardcoded "30 tests passed" message is gone.
- README corrected: the `doctor` and benchmark samples are now genuine captured output,
  and the test inventory matches the suite that exists.

### Testing

- 70 tests (from 37), passing on Python 3.10–3.13 locally and 3.9–3.13 in CI.
- New suites: `test_lane_fail_closed.py`, `test_env_injection.py`, `test_port_conflicts.py`,
  `test_init_gitignore.py`. The injection tests round-trip hostile strings through a real
  `/bin/sh`; the rollback test is verified to fail against the previous implementation.

## [v0.1.0] - 2026-08-30 (Initial v0 Release)

### Added
- **Core Architecture & Guide (Chapters 01–06)**:
  - `01-working-agreement.md`: Definition-of-Done checklist, path boundary contracts, security DoD, and merge discipline.
  - `02-conflict-management.md`: Port allocation matrix (SR1/SR2/JR1/JR2), worktree vs. clone setup, migration collision prevention via ticket IDs, and `.gitattributes` union merge rules.
  - `03-orchestration.md`: 3-state capability model (`native`, `author-required`, `unavailable`), seat vs. vendor separation, scaling rules (2→4→6), and review chains.
  - `04-agent-setup.md`: Drop-in prompts for senior and junior agent sessions, `.lane` configuration specification, and context cost management.
  - `05-github-mechanics.md`: Board single-select fields (`Lane`, `Seat`, `Owner`), disjoint milestones, sub-issues, and single-account routing.
  - `06-free-tier-ops.md`: Public vs. private repository matrix, verified mirror sync scripts, divergence checkers, and CI minute optimizations.
- **Scaffolding & Tooling**:
  - **`parallel-agents` Python CLI (`src/parallel_agents/`)**: Turnkey tool implementing `init`, `doctor`, `spawn`, `status`, `diff`, `validate`, `inspect`, `logs`, `stop`, `restart`, `repair`, and `cleanup`.
  - **Automated Worktree & Branch Manager**: Automatically provisions worktrees (`.parallel-agents/worktrees/`) on deterministic branches (`parallel/<agent-id>/<task>`).
  - **Mechanical Lane Path Engine**: Glob-based `allow`/`deny` validator that fails with non-zero exit codes if an agent touches out-of-lane files.
  - **Collision-Free Port Allocator**: Provisions non-conflicting port pairs and injects them into isolated `.env` and `.lane` files.
  - **Diagnostics & Recovery**: Self-repair and health diagnostic suite (`doctor` and `repair`).
  - `bootstrap.sh` & `bootstrap.conf.example`: Automated idempotent script to create GitHub Project boards, fields, standard labels, and milestones in < 30 seconds.
  - `templates/pull_request_template.md`: PR template with mandatory gate execution declaration and lane verification.
  - `templates/issue-template-task.yml` & `templates/issue-template-bug.yml`: GitHub Issue forms for lane-partitioned tasks and defects.
  - `templates/ci.yml`: GitHub Actions workflow with path filtering and auto-cancellation of superseded runs.
  - `templates/git-hooks/`: Pre-push test verification gate and pre-commit secret/env leak blocker.
  - `templates/dot-lane.example`: Local checkout seat configuration file.
  - `templates/gitattributes`: Union merge rules for generated indexes and registries.
- **Automated Test Suite (`tests/`)**:
  - Unit tests for lane path matching (`tests/test_lanes.py`), port allocation (`tests/test_ports.py`), and end-to-end multi-agent isolation lifecycle in temporary git repositories (`tests/test_e2e.py`).
- **Documentation**:
  - `README.md`: Story-driven quickstart guide, who this is for, and CLI command reference.
  - `EXAMPLES.md`: Full end-to-end walkthrough of Ticket #102.
  - `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`: Open-source community guidelines.
