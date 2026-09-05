# Changelog

All notable changes to the `lanekeeper` framework and scaffolding will be documented in this file.

Entries before v0.5.0 describe a project that was then called `parallel-agents`; they
use the current names for the things they describe.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v0.7.5] — 2026-09-05

Found while writing a thorough, first-time-user test protocol and running every
command in it against published 0.7.4. None of these is a hole in the gate; each is
the tool telling a new user something false or unhelpful.

### Fixed

- **`cleanup` crashed with a traceback when nothing could answer its question.** Run
  from a script or a pipe with no input, `input()` raised `EOFError` and the user got
  a stack trace. It now aborts, keeps the work, and names `--force`. An answer that
  *is* piped in still counts, as before.
- **A worktree holding only lanekeeper's own files counted as dirty.** `.lane` and
  `.env` are written by `spawn`, so `cleanup` demanded `--force` for an agent that had
  never run — which teaches people to pass `--force` always, exactly the habit the
  question exists to prevent. `has_uncommitted_changes` now ignores those two files,
  and the git removal past that guard is forced, since git will not remove a worktree
  over its own untracked files.
- **Two messages recommended `lanekeeper init --force`**, which replaces a policy
  built from tickets with technology-layer lanes. `validate` now says to add the path
  to the lane that needs it; the missing-cards message says to restore the cards from
  git or drop `capability_gates`, and says what `init --force` would cost.
- **`lanekeeper diff` printed a file count higher than the list below it**, because
  bookkeeping files were counted and then hidden.

## [v0.7.4] — 2026-09-02

Everything here was found by running the tester sheet, start to finish, on a fresh
clone of a real project (`kish21/mini-issue-tracker` and its three product-playbook
tickets). The gate itself was right every time; the flow around it was not.

### Fixed

- **A check inside an agent's worktree could not find the policy.** `spawn --ticket`
  writes the policy into the main checkout and branches the agent from a commit that
  does not carry it, so the boundary check in the worktree — the one the sheet asks
  for before pushing — failed with "this checkout has no policy". It now reads the
  policy from the repository's main checkout (`WorktreeManager.main_worktree_root`)
  and says both that it did and that the policy still has to be committed for CI. A
  checkout with no policy anywhere still fails closed.
- **The uncommitted policy turned the agent's first commit red.** `git add -A` in the
  worktree swept `.lanekeeper/config.yaml` into the agent's branch, where the gate
  denied it — correctly, since a policy change is its own lane, and bafflingly, since
  nobody had touched it. `spawn --ticket` now says to commit the policy first, with
  the command, before it mentions the label.
- A branch name no longer ends in a separator when the task title is cut to length.
- "All 1 changed file stays inside the lane", not "stay".

## [v0.7.3] — 2026-09-02

### Added

- **One command per ticket.** `lanekeeper spawn --ticket 12` no longer needs a board:
  the ticket's own file list (*Allowed File Paths* or product-playbook's *Target
  Modules*) becomes a lane named by the ticket's tag (`[FEAT-02]` → `feat-02`, else
  `issue-12`), written into the policy so `check` in CI enforces the same boundary.
  A ticket that names no files is refused with the fix: `--allow <glob>` to say the
  files yourself, or `--propose` to have Claude Code suggest them, shown before use
  and accepted only by a terminal answer or `--yes`. A lane already in the policy is
  reused as it is. A possible collision with another lane is reported, not blocked
  on. On a project with no policy, the command writes one holding only this lane.
  The board is consulted only with `board.read: true`; a ticket the board lacks
  falls back to the ticket itself. Trackers gain `get_issue`; GitHub reads it with
  `gh issue view`.

## [v0.7.2] — 2026-09-02

### Fixed

- **Every `lanekeeper-*.yml` workflow is policy.** The `policy` lane listed only the
  gate's own workflow file, so adding a second lanekeeper workflow (the manual board
  runner) to the pull request that installs lanekeeper turned that PR's gate red.
  Found on the first real project, the day after v0.7.1.

## [v0.7.1] — 2026-09-01

Everything here comes from the first end-to-end run on a real project —
[kish21/mini-issue-tracker](https://github.com/kish21/mini-issue-tracker), a React app
with a product-playbook `PRODUCT.md` and three product-playbook tickets. v0.7.0 stopped
at step 1 with a false coverage gap and, with that switched off, read zero file paths
out of all three tickets. Every item below was found by that run and is pinned by a test.

### Fixed

- **A coverage gap no longer stops `start`.** Coverage is a word match between a
  feature's name and the tickets' text. It read three sub-bullets of one feature
  ("Problem summary & context" …) as three missing features and refused to continue,
  with no flag that could answer it. Nested bullets are now details, not features, and a
  remaining gap is reported as advice — *"That is a word match, not a judgement"* — while
  the run carries on.
- **product-playbook's own ticket format is read.** Its file section is headed
  *📁 Target Modules & Exact File Names* and each line is a checkbox with a bold label
  and a backticked path. The heading's emoji hid it from the parser, and the label made
  every line "prose". Headings are matched on their words; a line with backticked spans
  yields those spans as paths; `target modules` and `target files` are default headings.
- **A markdown rule (`---`) between form fields was read as a path** and written into
  the lane. Rules are skipped.
- **A single-ticket lane is named by the ticket's tag** (`[FEAT-02]` → `feat-02`), not
  by one directory it happens to touch. The trial produced lanes called `prompt` and
  `prompts`.
- **The draft offers the shared zone a collision is asking for**, switched off, so the
  fix for *"prompt and feat-02 both cover src/domain/contracts.ts"* is a matter of
  deleting two characters rather than knowing the schema.
- **A policy created by `divide --confirm` gets the same first-time setup as `init`:**
  seat cards, ignore rules, the worktree directory. Without the cards, its default
  capability gates refused every `spawn`.
- **The seat cards are no longer gitignored.** The rules `init` wrote ignored
  `.lanekeeper/capabilities/`, so the cards could never be committed and the gate had
  nothing to read in CI.
- **The `policy` lane may also touch `.gitignore`, `lanes.yaml` and the gate's own
  workflow**, so the pull request that installs lanekeeper can pass the gate it installs.
- **`check` finds the repository root from any subdirectory**, and when the checkout
  has no policy it says why: the policy must be on the base branch before agents branch
  from it.
- **`cleanup` deletes the agent's branch when it is fully merged** and names it when it
  is not. Branches used to accumulate forever, and a re-spawned agent silently resumed
  an old one.
- **The "no labels" quality flag is gone.** Nothing groups by label, so it complained
  about a clue nobody used, on every real backlog.

### Changed

- **The README opens with five minutes, start to gate**, using the trial's real output.
  The reference follows. The backend/frontend diagram is gone.
- **The six process documents and the walkthrough moved to `docs/legacy/`** with a
  note: they describe the pre-tool, layer-lane way of working. `init` now says out loud
  that its detected lanes are technology layers and a starting point only. The `.lane`
  template shows what `spawn` actually writes; the PR template asks for the `lane:`
  label instead of a layer checkbox.

## [v0.7.0] — 2026-09-01

### Fixed — the boundary check now holds

A review of v0.6.0 against a real repository found five ways a change could leave its
lane and `validate` would pass it. All five are closed, each pinned by a test in
`tests/test_gate_holes.py` that reproduces the escape first.

- **A rename out of another lane was invisible.** Git's rename detection reported only
  the destination, and the porcelain parser skipped the source on purpose. `git mv
  src/frontend/App.tsx src/backend/App.tsx` validated clean for the backend lane; so did
  moving a file out of `secrets/`. Both sides of a rename are now reported.
- **A base branch git could not diff against produced an empty change list**, and an
  empty change list validates clean: "All 0 changed files are within allowed lane
  paths." A diff that cannot be computed is now a failed validation that says so.
- **The lane policy was exempt from the lane check.** Everything under `.lanekeeper/`
  was skipped, including the tracked `config.yaml` and the seat cards, so an agent could
  widen its own lane in the same pull request. Only the runtime subdirectories are
  exempt now; the policy files are denied to every lane. `.gitignore` is ordinary work.
- **A lane with no `allow` patterns allowed everything.** Refused at load, by name.
- **A deny written as a directory (`secrets/`) matched nothing** in a lane, while the
  capability gates expanded the same spelling to `secrets/**`. One reading now.
- **An unreadable state ledger was read as empty**, so a damaged `ports.json` freed
  every port and the next save replaced the file. It now stops every command with a
  message and changes nothing.
- **`cleanup` asked for confirmation and ignored the answer.** Answering `y` removed
  nothing and marked the agent as failing cleanup. `y` now means what `--force` means.

### Added

- **`lanekeeper check` — the boundary check as a pull-request gate.** The same lane
  engine, handed a lane name and a diff instead of an agent record, so it runs anywhere
  there is a checkout. `--write-workflow` installs a GitHub Actions workflow that runs it
  on every pull request, reading the lane from a `lane: <name>` label — the label family
  `bootstrap.sh` creates — and failing closed when there is not exactly one. A change to
  the policy files is checked under the reserved lane `policy`, which may touch those
  files and nothing else.

- **`lanekeeper open` and `spawn --open` — the desk.** Opens the agent's worktree in
  the configured editor (`editor.command`, default `code`). The worktree's `.lane` file
  now carries the task and the lane's `ALLOW` and `DENY` patterns, so an agent told to
  read it knows its boundary without the configuration.

- **`lanekeeper board` — the board, from the configuration.** `bootstrap.sh` has
  created the GitHub project board with its Lane, Owner and Seat fields since before
  lanekeeper had a Python line in it, and nothing ever called it. It now ships inside
  the package, and `board` generates its inputs from `config.yaml`: the lanes are the
  configured lanes, the seats are the seats with capability cards. The example's layer
  lanes (interface, service, data, platform) are gone. `board --show` reads every
  card's Lane, Owner and Seat back; with `board.read: true`, dividing the work takes a
  card's Lane over the ticket form's free-text field; and `spawn --ticket <number>`
  takes lane and seat from the card, refusing a card whose Lane is blank.

- **`start` hands off to product-playbook.** When nothing is written down, `start`
  opens Claude Code in the project with `/vision` as the opening prompt, waits for the
  session to end, and looks at the tickets again. Only on a terminal with a person at
  it; `--no-handoff` keeps the old behaviour of printing the steps, `--handoff` forces
  it. `intake.playbook` in the configuration names the command and the steps.

- **`divide.advisor: claude-code`.** The first advisor, and it is asked one question:
  what does a ticket that names no files, and that nothing in the code matches,
  probably touch? It runs `claude -p` on the user's own Claude Code login — a
  subscription or an API key, lanekeeper holds neither — and its answer is kept only
  where it names something that exists in the project. The suggestion lands in the
  draft switched off, marked as proposed, for the user to confirm. It never reaches the
  gate, which stays a set intersection over globs.

- **`divide --confirm` now changes who may touch what.** `lanes.yaml` was written and
  read by nothing; the confirmation said "this is what I read from now on" and it was
  not. Confirming now also writes the lanes into `config.yaml`, the policy `spawn`,
  `validate` and `check` enforce, creating the file with defaults when a project has
  none. A `claims: unowned` lane is honoured in the draft check and left out of the
  policy, with a line saying so.

- **The project's own worked example confirms.** Two wildcard segments were assumed to
  collide, so `carrier_*.py` and `email_*.py` were reported as one overlap and
  `examples/feature-lanes.yaml` could not pass `--confirm`. Wildcard segments are now
  compared character by character; a test confirms the example against its own tree.


- **`lanekeeper start`, and the question it asks before anything else.** Everything the
  tool does downstream — how the work divides, who owns what, what the merge gate
  enforces — is derived from the issues. If the issues are missing or thin, dividing them
  produces a confident-looking split of nothing. `start` is now the guided entry point,
  and its first step is that check: is the work written down, and does it cover what this
  product is meant to do? On a project with nothing written down it explains what
  product-playbook is and what to run (`/vision`, `/scope`, `/plan`), and exits having
  changed nothing at all.

  Coverage is judged against `PRODUCT.md` first — product-playbook's own output, and the
  reason the two tools are a pair — then a README, and if there is neither, it says so
  plainly: *"I count 12 pieces of work and I cannot tell whether that is all of them."*
  That third case is never dressed up as a verdict. Answer it with `--take-as-is`.

  The result is recorded with a fingerprint of the work it was based on, so fixing your
  issues and running `start` again continues rather than restarting. `lanekeeper intake`
  runs the same check on its own.

- **An issue-tracker provider interface** (`lanekeeper.trackers`). GitHub Issues is one
  implementation of it, selected by `intake.tracker` in `config.yaml`, not an assumption
  baked into the logic that reads it. A tracker that cannot be read reports *why* in plain
  words — unreadable is not the same as empty, and telling someone to write down work they
  already have would be the worst available wrong answer.

- **An `intake` section in `config.yaml`.** Where the work is read from, which documents
  describe the product, and every threshold the check judges by. It is absent from every
  configuration written before this release and is fully defaulted on load, so existing
  projects are unaffected.

### Unchanged

- **`init` is exactly as it was.** It is no longer the front door — `start` is — but it is
  neither rewritten nor deprecated, and nothing about its behaviour changed. It remains
  the direct route for someone who already knows how their work divides. Nobody on v0.6.0
  breaks.

---

## [v0.6.0]

Everything here comes from running the CLI against a real full-stack application — a live
backend and a live Vite dev server per agent — rather than against temporary directories
and stub agents. Three of the guarantees the tool advertises did not survive that.

It is also the first release prepared for distribution on PyPI, so the packaging metadata
had to become true.

### Fixed

- **A generated `.env` did not connect a frontend to its own backend.** It wrote port
  numbers only. Browser build tools expose just their own prefixed variables to client
  code, so a Vite bundle could see `VITE_PORT` — its *own* dev-server port — but not
  `API_PORT`, and fell through to the server compiled into its source. Two agents' running
  frontends both addressed a third, unrelated process. `init` now reads the repository's
  declared dependencies and writes the URL variables that stack can actually read; the
  names live in `config.yaml` under `environment.url_templates` and are expanded against
  each agent's own ports. A template naming a port category the project does not define is
  dropped, never emitted half-expanded.

- **`repair` could not converge.** Marking a dead agent `FAILED` turned its live port
  reservations into orphans, and the port-cleanup pass only released ports belonging to
  agents missing from state altogether — so it never cleared what it had just created.
  `doctor` said "run repair", repair reported success, and the same problems were reported
  indefinitely. Every state the pass can create, it now also resolves: ports held by
  terminal agents are released, an agent whose worktree has vanished is reconciled, and a
  finished agent with no worktree is no longer reported as a fault at all.

- **`cleanup` reported success it had not achieved.** A failed `git worktree remove` was
  downgraded to a warning while the summary still printed success and exited 0; ports were
  released while a server was still bound to them, and the state record was deleted, after
  which nothing named the leftover directory. It removes the worktree first and treats
  failure as failure — keeping the ports, the record and a `cleanup_failed` marker so
  `doctor` can still see the problem and `repair` knows not to release resources that are
  deliberately retained. A directory git has already disowned is removed directly, so a
  retried cleanup can finish instead of failing forever on "is not a working tree".

- **Agent ids were reused.** An id names a directory, so a recycled id resolved to a path a
  previous agent might still occupy, and `git worktree add` failed on a directory nothing
  in state referred to. Ids are now monotonic, backed by a persisted high-water mark that
  is reconciled against live state so a lost counter can only resume the sequence.

- **The package reported the wrong version.** `__version__` was a literal reading `0.1.0`
  while pyproject and `VERSION` both said `0.6.0` — five releases stale, and undetectable,
  because nothing compared it to anything. It is now derived: the `VERSION` file in a
  source checkout, the installed distribution's own metadata otherwise. A test asserts all
  three agree.

- **The README's install section contradicted itself.** The v0.5.0 rename rewrote the
  paragraph mechanically, leaving it claiming the distribution is published under
  `lanekeeper` *and* that `lanekeeper` is taken on PyPI by someone else. It also still
  advertised a `parallel-agents` alias that the same release had removed. This matters
  beyond the repository: PyPI renders the README as the project page.

### Added

- `lanekeeper.frameworks` — detects the client-visible environment prefixes a repository's
  frontends read (Vite, Next.js, CRA, Nuxt, SvelteKit, Astro, Remix, Gatsby, Expo,
  Angular), used to seed `environment.url_templates` at `init`.
- `doctor` reports directories under the worktree root that no agent claims, and agents
  whose cleanup did not finish. Both are marked as *not* automatically repairable, and
  `doctor` now only recommends `repair` when something is actually repairable.
- `spawn` refuses a target path that already exists, naming the cause, instead of failing
  inside git.
- `lanekeeper --version`, so an installed copy can state which build it is. The first
  thing anyone asks of a CLI they did not build from source.

---

## [v0.5.0]

The project is now called **lanekeeper**. Nothing had been published under the previous
name, so this release makes the change everywhere at once rather than carrying an alias.

### Changed

- **Renamed to `lanekeeper`.** The previous distribution name, `parallel-agents`, is
  registered on PyPI by an unrelated project, so `pip install parallel-agents` fetched
  someone else's package and this one could not be installed by name at all.
- **The rename is complete rather than cosmetic.** The import package is now
  `lanekeeper` (was `parallel_agents`), and the directory the tool keeps its files in is
  now `.lanekeeper/` (was `.parallel-agents/`).
- **`lanekeeper` is the only command.** A `parallel-agents` alias was briefly kept for
  compatibility and has been removed: nothing was ever published under that name, so no
  installation existed for it to protect.
- The GitHub repository keeps its name, and the guide's prose about running agents *in
  parallel* is unchanged — that is the subject matter, not the product name.

### Added

- **`LANEKEEPER_HOME`** sets the directory lanekeeper keeps its files in, relative to the
  repository root. Config, state, logs, capability cards, the default worktree location
  and the rules `init` writes into `.gitignore` all follow it. An absolute path, or one
  containing `..`, is refused rather than allowed to write outside the repository.
- `[project.urls]`, so the PyPI page links back to the repository and changelog.

### Fixed

- `audit_ports` annotated a return type of `Dict[str, Any]` without importing `Any`.
  Deferred annotation evaluation kept it from raising at runtime, but
  `typing.get_type_hints()` on that method failed with a `NameError`.
- The README's sample terminal output showed banners the commands no longer print, and
  its version badge and file links were stale.

### Internal

- The directory name was previously spelled out in eight source files, including
  user-facing messages and the generated `.gitignore` block. It is now derived in one
  place, `lanekeeper.paths`. A stale name in the ignore block would have let one agent's
  worktree reach another's commit, which is the failure that block exists to prevent.

## [v0.4.0]

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

## [v0.3.0]

Implements capability gates — the second of the two theses in `PLAN.md`, specified in
`03-orchestration.md` since the first commit and never enforced. Also fixes a second
fail-open found while building it.

### Added

- **Capability cards are now load-bearing.** A seat's card declares its capabilities in
  the three states from `03-orchestration.md` (`native` / `author-required` /
  `unavailable`), the lanes it may enter, and paths forbidden to it. Cards live in
  `.lanekeeper/capabilities/<seat>.json` and are committed, like the lane policy.
- **`capability_gates` in `config.yaml`** maps path patterns to the capability they
  require. This is what turns a rating into an enforceable rule — the mechanical form of
  the instruction in `01-working-agreement.md` to stop when a change touches money, auth,
  tenant isolation, or a migration. Defaults gate auth/payments/billing/tenant/secrets
  paths on `security_review`, and migration paths on `database_migrations`.
- **`validate` enforces the gates.** `native` passes; `author-required` passes only if a
  quality command declaring `satisfies: <capability>` ran and exited 0; `unavailable` is a
  hard stop with a non-zero exit. A seat rated unavailable for security review can no
  longer get a green validate on auth code, even when the file is inside its lane.
- **`lanekeeper declare <agent>`** generates the PR template's mandatory Gate
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

## [v0.2.0]

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

## [v0.1.0] — Initial v0 Release

### Added
- **Core Architecture & Guide (Chapters 01–06)**:
  - `01-working-agreement.md`: Definition-of-Done checklist, path boundary contracts, security DoD, and merge discipline.
  - `02-conflict-management.md`: Port allocation matrix (SR1/SR2/JR1/JR2), worktree vs. clone setup, migration collision prevention via ticket IDs, and `.gitattributes` union merge rules.
  - `03-orchestration.md`: 3-state capability model (`native`, `author-required`, `unavailable`), seat vs. vendor separation, scaling rules (2→4→6), and review chains.
  - `04-agent-setup.md`: Drop-in prompts for senior and junior agent sessions, `.lane` configuration specification, and context cost management.
  - `05-github-mechanics.md`: Board single-select fields (`Lane`, `Seat`, `Owner`), disjoint milestones, sub-issues, and single-account routing.
  - `06-free-tier-ops.md`: Public vs. private repository matrix, verified mirror sync scripts, divergence checkers, and CI minute optimizations.
- **Scaffolding & Tooling**:
  - **`lanekeeper` Python CLI (`src/lanekeeper/`)**: Turnkey tool implementing `init`, `doctor`, `spawn`, `status`, `diff`, `validate`, `inspect`, `logs`, `stop`, `restart`, `repair`, and `cleanup`.
  - **Automated Worktree & Branch Manager**: Automatically provisions worktrees (`.lanekeeper/worktrees/`) on deterministic branches (`parallel/<agent-id>/<task>`).
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
