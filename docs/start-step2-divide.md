# Step 2 of `lanekeeper start`: divide the work

Issue: #38 · Step 2 of umbrella #36 · Depends on #37 (merged) and the ticket form (#46,
merged) · Blocks #39 · Advances #23

Read [#38's rewrite comment](https://github.com/kish21/parallel-agents/issues/38#issuecomment-5494124416),
not its description. This document is the contract that comment asks for.

## 1. The decision this builds to

> Group the tickets where they group. Where they do not, **show them and ask** which
> ones to hand to a separate agent. Never block, never guess.

Three consequences carry the whole design:

- **A lane can be a single ticket**, bounded by that ticket's own Allowed File Paths. It
  is a complete lane, not a degraded one, and the output gives it no apology.
- **A picked ticket with no file paths has nothing to enforce.** No boundary means no
  gate, so handing it over ships a safety guarantee that quietly does not exist. Paths
  are asked for, or proposed for confirmation.
- **The mechanical collision check lives here**, earlier than #39 planned: do any two
  picks touch the same files, yes or no. A set intersection, no judgement. #39 keeps the
  hard half — is an overlap a dependency or a collision, and should the lanes fuse or
  share a zone.

And the model, unchanged since #23: **lanes are feature slices, never technology layers.**

## 2. Naming

The command is **`lanekeeper divide`**, and the package `lanekeeper.divide`. `check` is
#31's. `group` understates it: the step also asks, collides and proposes a boundary.
`lanekeeper start` runs step 1 then step 2 and stops; `divide` is the same step run on
its own, which is what makes it re-runnable after the user edits tickets.

## 3. Scope of this session

**In scope**

- `lanekeeper.divide`: parse ticket boundaries, propose a division, list what could not
  be placed, report collisions, write a draft lane file, confirm it into `lanes.yaml`.
- A `divide:` config section — every threshold, ignore-list and path settable.
- `lanekeeper divide` and `divide --confirm`; `start` gains step 2.
- The code-reading source of feature slices, which does **not** use
  `layout.ROLE_BY_DIR_NAME`.
- Plain-language output, guarded by a vocabulary test as step 1's is.

**Explicitly out of scope**

- **#39's judgement.** An overlap is reported as an overlap. Whether it is a dependency,
  and whether the answer is to fuse the lanes or declare a shared zone, is #39.
- **Rewriting the user's tickets.** Missing paths are asked for and, if the user
  supplies them, written into the lane file — never back into the tracker. Step 1 drew
  this line and it holds.
- **`init` and `layout.py`.** `init` keeps detecting backend/frontend; it is the
  low-level escape hatch. What changes is that the **guided path stops going through
  it** (§7).
- Seats, boards, worktrees (#33, #40, #41) and the merge gate (#31/#32).
- Any model call, anywhere, for any reason.

## 4. Module-interaction map

```
cli.cmd_divide ─┬─► intake.run_intake(...)          (step 1, unchanged; must pass)
                │        └─ returns IntakeResult, now carrying the tickets it read
                │
                └─► divide.proposal.propose(root, settings, intake_result)
                          │
                          ├─► divide.boundary.read(TrackedIssue)  ──► TicketBoundary
                          │       parses "Allowed File Paths" per docs/ticket-template.md §4
                          │
                          ├─► divide.codebase.slices(root, settings) ──► CodeSlice[]
                          │       git-tracked files ▸ repeated feature directory names
                          │       NEVER layout.ROLE_BY_DIR_NAME
                          │
                          ├─► divide.grouping.group(boundaries, slices, settings)
                          │                                    ──► ProposedLane[]
                          └─► divide.collision.report(lanes, tracked_files)
                                                               ──► Overlap[]
                          returns DivisionProposal

cli.cmd_divide --confirm ─► divide.draft.load(path)  (the user's edited draft)
                          ─► divide.draft.validate(...)   placement + paths + collisions
                          ─► divide.draft.write_lane_file(root)   ──► lanes.yaml (#34 v1)

divide.presenter.render(DivisionProposal | ValidationReport) ──► plain language
```

**Dependencies point inward.** `divide.*` imports `trackers.base` for the ticket type,
`lanes.LaneEngine` for glob matching and `config` for its settings. It never imports
`cli`, never shells out except through `codebase`'s one `git ls-files` call (reused from
`layout.tracked_files`), and never reads `argparse`. Every function is handed its inputs
and returns a value.

### The input contract, and the one change it needs upstream

Step 2 is handed an `IntakeResult` and **does not re-read the tracker**. But
`IntakeResult` today carries `issue_count`, not the issues, and step 2 needs the bodies —
that is where Allowed File Paths lives.

`gate.run_intake` already lists the issues before it consults the record, so the tickets
are in hand on every path including a resumed one. So:

```python
@dataclass(frozen=True)
class IntakeResult:
    ...
    #: The tickets step 1 read. Runtime only: never recorded, and re-attached from the
    #: live listing on a resumed run, so a resumed step 2 reads today's ticket bodies
    #: rather than a snapshot of yesterday's.
    issues: Tuple[TrackedIssue, ...] = field(default=(), compare=False, repr=False)
```

`record.save` does not write it and `record.load` does not read it; `run_intake`
attaches it on return, in both the fresh and the resumed branch. The fingerprint is
untouched. This is the only change to #37's code.

### Typed contracts

```python
class PathSource(Enum):    TICKET | CODE | PROPOSED     # where a boundary came from
class Placement(Enum):     GROUPED | SINGLE_TICKET | UNPLACED

@dataclass(frozen=True)
class TicketBoundary:
    ref: str; title: str
    paths: Tuple[str, ...]        # normalised globs, () when the ticket named none
    declared_lane: str            # the form's optional free-text Lane; "" is ordinary
    source: PathSource

@dataclass(frozen=True)
class CodeSlice:
    name: str
    paths: Tuple[str, ...]
    file_count: int
    evidence: Tuple[str, ...]     # the directories that produced the name

@dataclass(frozen=True)
class ProposedLane:
    name: str
    paths: Tuple[str, ...]
    tickets: Tuple[str, ...]      # refs, in exactly one lane across the proposal
    source: PathSource            # which of the two sources the paths came from
    placement: Placement
    why: str                      # one plain sentence: why these belong together

@dataclass(frozen=True)
class Overlap:
    left: str; right: str
    patterns: Tuple[Tuple[str, str], ...]
    example_files: Tuple[str, ...]        # real tracked files matching both
    kind: str                             # "files" | "patterns-only"

@dataclass(frozen=True)
class DivisionProposal:
    lanes: Tuple[ProposedLane, ...]
    unplaced: Tuple[TicketBoundary, ...]     # every ticket not in a lane, named
    needs_paths: Tuple[TicketBoundary, ...]  # picked, but nothing to enforce
    overlaps: Tuple[Overlap, ...]
    code_slices: Tuple[CodeSlice, ...]
    unclaimed_examples: Tuple[str, ...]      # tracked files no lane claims
```

No raw dicts cross a boundary, and `unplaced` exists so that "every ticket lands in
exactly one entry or an explicit could-not-place list" is a property of the type, not of
a code path someone has to remember to run.

## 5. How the division is actually computed — deterministic, no model

**a. The ticket's own paths are the primary source.** `boundary.read` finds the
`Allowed File Paths` section of the issue body — the form's own heading — and takes one
path or glob per line, per the contract in `docs/ticket-template.md` §4. Lines are
normalised (backslashes, leading `./` and `/`, a trailing `/` becoming `/**`). A ticket
whose section is absent or empty yields no paths.

**b. Feature names come from the paths, not from directory roles.** Each path
contributes candidate slice names: the path segments that are neither a top-level
container (`src`, `app`, `packages`, `backend`, `frontend`, `tests`, …, all config) nor a
generic bucket (`api`, `components`, `pages`, `lib`, `hooks`, `schemas`, `db`, …, all
config), plus the file stem with generic suffixes stripped (`CheckoutPage.tsx` →
`checkout`). `backend/app/domains/checkout/**` and
`frontend/src/components/checkout/**` both yield `checkout`, which is exactly why this
produces slices and `ROLE_BY_DIR_NAME` produces layers.

**c. Group where they group.** Tickets sharing a candidate name become one
`ProposedLane` when at least `divide.thresholds.min_group_tickets` (default 2) tickets
share it. An explicit free-text `Lane` on a ticket is stronger evidence than an inferred
name and groups on its own. A ticket matching several names goes to the most specific —
the name with the fewest tickets — and ties fall to the alphabetically first, so the
proposal is stable across runs.

**d. Where they do not group, the ticket is its own lane.** `SINGLE_TICKET`, bounded by
its own paths, presented with no apology and no "degraded" label. This is the pick list:
the output says *these did not group; each one can go to its own agent — which do you
want to hand out?* It is never a stop.

**e. The code is the second source, and the fallback.** `codebase.slices` reads
git-tracked files and finds directory names that recur under **more than one** top-level
root (`domains/catalog` and `components/catalog` → `catalog`), plus leaf directories
under a configured feature container (`domains`, `features`, `modules`). A name that
appears under only one root is not a slice — that is a layer, and this is where
`ROLE_BY_DIR_NAME` is displaced. A feature does not always own a directory on both sides — `auth` has a whole
`backend/app/auth/` and, on the front end, `useAuth.ts` and `authStore.ts` sitting loose
among their neighbours — so a filename counts as evidence too, but only for a name some
directory has already established. A filename alone names nothing worth splitting.

Code slices are used to (i) **offer** a wider boundary to a lane whose tickets named
files one by one, (ii) propose paths for a ticket that named none, and (iii) carry the
whole proposal on a repository whose tickets have no paths at all. Every lane says which
source it came from, in the output.

**Offer, not widen — a deliberate change from this document's first draft.** Applying
the wider claim would hand an agent more than any ticket asked for, which is the
opposite of what a boundary is for. So it goes into the draft as commented lines under
the entry, for the user to accept. The reason it is offered at all: a boundary made of
exactly today's files leaves the first new file the work creates outside it.

**f. Nothing is invented for a ticket with no paths.** It appears in `needs_paths` with
whatever the code source suggests, marked `PROPOSED`, for confirmation. Not confirmed is
not enforced.

**g. A ticket with no paths is matched against the entries that exist, not given its
own.** When the files it would get are already an entry's, the draft says *add its
number to that entry* rather than offering a second entry over the same files — which,
accepted, is a clash by construction and a refusal to write anything.

**h. Collisions are set intersections.** Two lanes collide when a tracked file matches a
pattern in each (`LaneEngine.match_glob`, already correct and tested), which is the
evidence-carrying answer. Patterns that no current file matches are additionally
compared structurally, so a collision over files that do not exist yet is still
reported, marked `patterns-only`. Reported before the lane file is written, every time.

`deny` and a shared zone are the two documented ways to answer an overlap (README, §The
lane file), so both are honoured: a file a lane denies is not that lane's, and a file
inside a zone belongs to the zone however specifically a lane claims it. They answer the
pairs they actually cover and no others — blanking every structural finding because a
zone exists somewhere would let one answered overlap hide all the unanswered ones. A
collision proved by a file that exists is never suppressed this way.

## 6. Propose, then confirm — the interaction

Never a blank form, never a silent decision, and no interactive prompt to test around:

1. `lanekeeper divide` prints the proposal — the lanes, the tickets in each, the source
   of each boundary, the tickets it could not place, the tickets with nothing to
   enforce, and any collisions — and writes a **draft** to
   `.lanekeeper/start/lanes.draft.yaml`: a complete, commented lane file in the #34 v1
   schema, with the could-not-place list and the missing-path tickets present as
   commented blocks so keeping one is an edit, not a retype. It does **not** write
   `lanes.yaml`.
2. The user edits the draft — merge, split, rename, delete, add paths — which is where
   "the user picks" happens. Hand-editing a lane file is the act the README already
   calls expected.
3. `lanekeeper divide --confirm` loads the draft, re-runs every mechanical check on
   **what the user actually wrote** (placement, empty boundaries, collisions), and on a
   clean result writes `lanes.yaml` and says what it wrote. A collision or an empty
   boundary is reported and `lanes.yaml` is not written — the user adjusts and confirms
   again. *(v0.7.0: confirming also writes the lanes into `config.yaml`, the policy
   `spawn`, `validate` and `check` read. `lanes.yaml` is the human record; the policy
   file is what is enforced.)*

Two rules hold this together, both learned from the review of this step:

- **Re-running never destroys an edit.** `start` runs step 2 every time it is run, so
  the draft is written once and afterwards left exactly as the user left it; `--fresh`
  is how they ask for lanekeeper's suggestion back.
- **Confirming writes the user's own document**, minus the draft's `tickets`
  bookkeeping. `deny`, `shared`, `unowned`, `owner` and `harness` are all part of the
  documented schema and are the two documented ways to answer a reported overlap, so
  re-rendering the file from the entries step 2 understood would delete the fix and
  report the same collision again. An existing `lanes.yaml` is never replaced without
  `--force`: it may have been written by hand, and this command did not write it.

**Not built, and not promised anywhere in the output:** shorthand flags for picking
(`--separate`, `--group`). The draft is the pick list, and editing it is the answer. If
the real run shows that is friction, the finding goes to #40 with evidence.

## 7. What this does to #23

`layout.ROLE_BY_DIR_NAME` is not deleted, and `init` still uses it. What changes is that
**the guided path no longer goes near it**: `start` → `divide` derives feature slices
from tickets and from recurring feature directories, and `init` is documented as the
escape hatch it was demoted to in #36. This is the half of #23 that #46 could not do and
this step can. #23 stays open for the `init` default itself, which is a separate change
with real blast radius on v0.6.0 users.

## 8. The two items parked in `docs/ticket-template.md` §7

**`broad_ticket_areas` default 3 → 5.** The flag exists to catch a ticket that is really
several pieces of work. It counts distinct top-level directories, and a correctly
written feature slice legitimately spans `backend`, `frontend`, `tests`, and often
`docs` and a migrations root — five. At 3 the default flags the exact model the form now
teaches. 5 keeps the flag meaningful for a genuinely sprawling ticket while a normal
slice passes. It is config; the change is to the default and to the sentence explaining
it.

**Asking for missing paths is this step's job, and here it is done.** `needs_paths` is
the mechanism, and it is deliberately *not* built on `quality._file_hints`: that scans
the whole body, so a stack trace in the Evidence field counts as a boundary.
`boundary.read` reads **only the Allowed File Paths section**, so "the filer stated a
boundary" and "the body happens to contain a path" stop being the same question. The
`NO_FILE_HINT` flag in step 1 keeps its looser meaning and is left alone.

A line in that section which does not read as a path is **reported, not dropped**. It is
usually a note the filer added; occasionally it is a file they meant to include, and a
boundary quietly narrower than the one they wrote is the same defect as one quietly
wider. Both end at the merge gate.

## 9. Exit criteria — from #38's definition of done

Not done until each is verified, by a test and, where marked, by a real run:

1. On a feature-organised repository the proposal is **feature slices**, not
   backend/frontend — asserted on a fixture tree that would produce layers under
   `ROLE_BY_DIR_NAME`, with the layer names asserted absent.
2. A backlog that does not group produces a **pick list**, not a stop: exit code 0, one
   `SINGLE_TICKET` lane per ticket, and no sentence telling the user to go away.
3. A single picked ticket is a valid lane bounded by its own Allowed File Paths, and the
   written `lanes.yaml` reloads through `config`.
4. A picked ticket with no file paths is never handed over silently: it lands in
   `needs_paths`, `--confirm` refuses to write a lane with an empty boundary, and the
   refusal names the ticket.
5. Any two picks touching the same files are reported **before** the lane file is
   written — asserted by a case where `lanes.yaml` does not exist after the run.
6. Every ticket lands in exactly one lane or in `unplaced` — asserted as a set identity
   over the whole input on every proposal test, not on one case.
7. Nothing in step 2 calls a model, and no output requires knowing what a lane, a
   worktree, a seat, a glob or a branch is (vocabulary test, step 1's list).
8. No output tells the user to move a file or reorganise a folder.
9. Re-running `divide` on unchanged input produces a byte-identical proposal.
10. `lanekeeper divide` runs green against **this repository**, whose backlog is filed
    through the template, and the proposal is inspected by hand rather than assumed.
11. The existing suite stays green, `init` is unchanged, and a v0.6.0 config with no
    `divide:` section loads with full defaults.

**The MarkVid criterion, and what the substitute actually measured.** #38 asks that the
proposal be recognisably MarkVid's 17 lanes. MarkVid's source is not on this machine
(only `Downloads/markvid-*` artefacts), so as written it cannot be run here. The
stand-in, labelled as one in `tests/test_divide_worked_example.py`: the 356 paths in
`examples/feature-lanes.yaml` — that product's own 17-lane split — turned back into a
file tree, with the reading given nothing else to go on.

It recovers **nine lane names exactly** (`auth`, `cart`, `catalog`, `checkout`,
`fulfilment`, `notifications`, `payments`, `reviews`, `search`) and **four more as the
head word of a compound name** (`admin` for `admin-console`, `seller` for
`seller-portal`, `pricing` and `promotions` for `pricing-promotions`, `recommendations`
for `recommendations-cost`). Thirteen of seventeen, recognisably the same split.

The four it does not find are `platform`, `storefront`, `new-modules` and
`market-research` — and the example's own annotations call every one of them a residue
or greenfield lane rather than a feature slice. A reading of files should not invent
them, so a test asserts they are **not** proposed. `auth` was a real miss until
filenames were allowed to count as evidence (§5e); that is what the case is there to
hold.

## 10. Test plan

**Unit** (no network, no `gh`, no subprocess except a real temp git repo)

- `test_divide_boundary.py` — the Allowed File Paths section is found under the form's
  heading and nowhere else; a stack trace elsewhere in the body yields no paths; blank
  and absent sections yield nothing; normalisation of `\`, `./`, leading and trailing
  `/`; a free-text Lane is carried through and a blank one is not a defect.
- `test_divide_codebase.py` — a name recurring under two roots is a slice; a name under
  one root is not; `domains/` and `features/` leaves are slices; a repository laid out
  as `backend/` and `frontend/` alone yields **no** slices rather than two layer lanes
  (the #23 assertion); ignore-lists are config-driven, proved by changing one.
- `test_divide_grouping.py` — tickets sharing a feature name group; below
  `min_group_tickets` they become single-ticket lanes; an explicit Lane groups on its
  own; every ticket appears exactly once across lanes plus unplaced; a ticket with no
  paths reaches `needs_paths` and never a lane; output stable across runs and across
  input order.
- `test_divide_collision.py` — two lanes claiming one real file collide with that file
  as evidence; disjoint lanes do not; overlapping patterns matching no existing file are
  reported as `patterns-only`; `**` cases through `LaneEngine.match_glob`.
- `test_divide_draft.py` — draft renders as valid YAML in the v1 schema and reloads; an
  edited draft round-trips; `--confirm` refuses an empty boundary, refuses a collision,
  writes `lanes.yaml` on a clean draft; a refused confirm writes nothing.
- `test_divide_language.py` — step 1's `BANNED_WORDS` over every rendered case, plus the
  no-restructuring guard, plus the required sentences for the pick-list case.
- `test_config.py` (extend) — no `divide:` section loads defaulted; round-trip;
  `broad_ticket_areas` default is 5 and a v0.6.0 config that sets 3 keeps 3.

**Integration** (real temp git repos, fake tracker only)

- `test_start_step2.py` — `cmd_divide` end to end on: a feature-organised repo with
  paths on every ticket; a backlog with no paths at all falling back to the code; a
  backlog that does not group; a collision case; the two-command propose → confirm flow;
  `start` running step 1 then step 2 and stopping honestly.
- `test_intake_hardening.py` (extend) — a resumed `IntakeResult` still carries the live
  tickets, so a resumed `start` divides today's backlog and not a recorded one.

**Regression** — the existing suite, `init` and `layout.py` untouched.

**Run the real command** — `lanekeeper divide` against this repository, and the proposal
read by a human. Green tests on fakes missed both cases the last ticket was written for.

## 11. Configuration — nothing hardcoded

```yaml
divide:
  advisor: none               # the only value implemented; no model is ever called
  draft_path: start/lanes.draft.yaml     # under .lanekeeper/
  containers: [src, app, apps, packages, modules, lib, libs, cmd, internal,
               backend, frontend, web, client, server, api, services, tests, test]
  generic_dirs: [components, pages, routes, hooks, utils, helpers, schemas, models,
                 db, migrations, static, assets, styles, types, config]
  feature_containers: [domains, features, modules, packages]
  path_headings: [allowed file paths]   # the heading a ticket states its boundary under
  lane_headings: [lane]
  thresholds:
    min_group_tickets: 2      # tickets sharing a name before it is a group
    min_slice_files: 2        # files under a directory before it is a slice
    min_slice_roots: 2        # top-level roots a name must appear under
    overlap_report_limit: 20
    unclaimed_examples: 5
```

`draft_path` and `lane_file` are checked to be inside the project: both are joined onto
the repository root and then written to, and an absolute path or one climbing out with
`..` would have this command writing outside the project it was pointed at. Same rule
`LANEKEEPER_HOME` already enforces, for the same reason.

Every list and number above is what makes this step's judgement a setting rather than an
opinion baked into a regex. `advisor` exists so that when an advisor is added it arrives
switched off, as #38 requires.

## 12. Risks

- **Name inference is heuristic.** A project whose paths carry no feature words yields
  single-ticket lanes. That is the honest answer and the design's fallback, not a
  failure — but it will look thin on such a repository, and the output says why.
- **The draft-file interaction is a design bet.** It trades an interactive picker for
  something testable and re-runnable. If it reads as friction in the real run, the
  finding goes to #40 with evidence rather than being guessed at now.
- **Collision evidence depends on tracked files.** A collision purely over yet-to-exist
  paths is reported structurally, which is weaker. Stated in the output rather than
  smoothed over.
