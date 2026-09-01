# Step 1 of `lanekeeper start`: is the work written down, and does it cover the features?

Issue: #37 · Step 1 of umbrella #36 · Blocks #38 · Resolves most of #30

## 1. The decision this builds to

`lanekeeper start` is the single guided entry point. It runs a **pre-flight FIRST** —
is the work written down, does it cover the features, can modules be identified — and
hands off to product-playbook (`/vision`, `/scope`, `/plan`) when it is not. Only after
that does it do the config-writing `init` does today, then the board (#40) and the
desks (#41).

`init` is **not rewritten and not deleted**. It stays exactly as it is, demoted to a
low-level escape hatch for someone who already knows their lanes. Nobody on v0.6.0
breaks.

This document covers **step 1 only**. `start` ends after step 1 with an honest message
naming what is not built yet. It does not pretend to do steps 2-7.

## 2. Scope of this session

**In scope**

- A new `lanekeeper start` command that runs step 1 and stops.
- A tracker **provider interface**, with GitHub Issues as one implementation.
- A product-spec resolver: `PRODUCT.md` -> README/docs -> nothing.
- A coverage judgement with three honest outcomes, never a dressed-up verdict.
- An issue-usability report (missing file hints, missing labels, probable duplicates,
  one ticket covering many features).
- A recorded, **resumable** result: fix the issues, run `start` again, it continues.
- Plain language in every user-facing string.

**Explicitly out of scope**

- Steps 2-7 (#38, #39, #40, #33, #41, #31/#32). `start` stops after step 1.
- Any change to `init`, `spawn`, `validate`, `diff`, `cleanup`, or the lane engine.
- **Writing to the user's tracker.** Where issues are unusable, step 1 *reports what is
  wrong and what to do*, and points at the project's issue template. It does not edit,
  relabel, split or close anybody's tickets. Rewriting a user's backlog is an
  outward-facing, hard-to-reverse action and belongs in its own issue with its own
  confirmation flow. Recorded as a follow-up.
- Any LLM call. Every judgement here is deterministic and explainable.

## 3. Naming

The step is **not** called `check`: that name is claimed by #31 (validate any
diff/branch/PR). The command is `lanekeeper intake`, and the module is
`lanekeeper.intake`. Intake is the act of receiving work before it is scheduled, which
is exactly what this step does.

`lanekeeper start` is what users are told to run; `lanekeeper intake` is the same gate
run on its own, which is what makes it testable and re-runnable. Both take
`--take-as-is` (this is the whole job, carry on) and `--fresh` (ignore what a previous
run decided).

## 4. Module-interaction map

```
cli.cmd_start ──────► intake.gate.run_intake(root, config, tracker)
       │                       │
       │                       ├─► trackers.IssueTracker            (provider interface)
       │                       │        ├── GitHubIssuesTracker  ── `gh issue list --json …`
       │                       │        └── NullTracker          ── "no tracker configured"
       │                       │
       │                       ├─► intake.spec.resolve_spec(root, config)
       │                       │        PRODUCT.md ▸ README/docs ▸ None
       │                       │
       │                       ├─► intake.coverage.judge(spec, issues, thresholds)
       │                       └─► intake.quality.inspect(issues, thresholds)
       │
       ├─► intake.record.load/save   →  .lanekeeper/start/intake.json   (resumability)
       └─► intake.presenter.render(IntakeResult) → plain-language text
```

**Dependencies point inward.** `intake.*` never imports `cli`, never shells out, and
never reads `argparse`. It is handed a tracker and a config and returns a value object.
The only I/O in the package is `intake.record` (one JSON file) and `intake.spec`
(reading local markdown).

### Typed contracts at every boundary

```python
# trackers/base.py — the provider interface
@dataclass(frozen=True)
class TrackedIssue:
    ref: str                 # "42" on GitHub; opaque elsewhere
    title: str
    body: str
    labels: tuple[str, ...]
    state: str
    url: str

class IssueTracker(ABC):
    name: str
    def is_available(self) -> AvailabilityReport: ...   # why not, in plain words
    def list_issues(self) -> list[TrackedIssue]: ...

# intake/models.py
class SpecSource(Enum):       PRODUCT_MD | DOCS | NONE
class Verdict(Enum):          READY | NEEDS_PLAYBOOK | NEEDS_TIDYING
class CoverageVerdict(Enum):  COVERED | GAPS | CANNOT_JUDGE

@dataclass(frozen=True) class Feature:        name: str; source_line: str
@dataclass(frozen=True) class FeatureMatch:   feature: Feature; issue_refs: tuple[str, ...]
@dataclass(frozen=True) class CoverageReport: verdict: CoverageVerdict; source: SpecSource
                                              source_path: str | None
                                              matches: tuple[FeatureMatch, ...]
                                              uncovered: tuple[Feature, ...]
@dataclass(frozen=True) class QualityFlag:    kind: str; issue_refs: tuple[str, ...]; detail: str
@dataclass(frozen=True) class IntakeResult:   verdict: Verdict; issue_count: int
                                              coverage: CoverageReport
                                              flags: tuple[QualityFlag, ...]
                                              fingerprint: str; recorded_at: str
```

No raw dicts cross a boundary. `IntakeResult` is the whole of what step 2 (#38) will be
handed.

## 5. The honest cases

| What is on the ground | Verdict | What the user is told |
|---|---|---|
| No issues at all | `NEEDS_PLAYBOOK` | What product-playbook is and what to run (`/vision`, `/scope`, `/plan`), in plain language. **Writes nothing.** |
| Issues + a spec, every feature has tickets | `READY` | The count, the source it compared against, and that it will continue |
| Issues + a spec, features with no ticket | `NEEDS_PLAYBOOK` | Exactly which features appear to have nothing written against them, and the offer to go back to the playbook |
| Issues, nothing to compare against | `NEEDS_TIDYING`* | *"I count 12 pieces of work and I cannot tell whether that is all of them."* The counts and labels, and the user decides. |
| The tracker cannot be read at all | `NEEDS_TIDYING` | Why, in plain words. Unreadable is not empty: telling someone to write down work they already have would be the worst possible wrong answer here. |
| Issues that exist but are unusable | `NEEDS_TIDYING` | Which tickets are missing a file/area hint, missing labels, look duplicated, or cover several features at once — plus the project's issue template if it has one |

\* `CANNOT_JUDGE` is a stop-and-ask, not a refusal — refusing would make the tool
unusable on every project that has a backlog and no `PRODUCT.md`. The user answers it
with `lanekeeper start --take-as-is`, which is recorded and bound to the fingerprint, so
changing the work asks again rather than staying accepted. It never overrides a coverage
gap or an unreadable tracker: neither of those is the user's opinion to give.

## 6. Resumability

`.lanekeeper/start/intake.json` records the `IntakeResult` plus a **fingerprint** of its
inputs: the tracker name, the issue count, a hash of `(ref, title, labels)` for every
issue, and the hash of the spec file. On the next `start`:

- fingerprint matches and the verdict was `READY` → step 1 is skipped with one line
  saying so, and `start` continues at step 2;
- fingerprint differs → step 1 re-runs (it is cheap) and the record is replaced;
- no record → step 1 runs;
- `--fresh` → the record is ignored and the check runs again from scratch.

**Only a passing result is recorded.** A run that stopped at the gate wrote nothing,
which is what lets `start` promise it changed nothing on a project it cannot help yet —
and is asserted by comparing the file tree before and after.

That is what "fix your issues, run `start` again, it continues rather than restarts"
means mechanically. The record lives under `.lanekeeper/`, which `.gitignore` already
excludes except for `config.yaml`, so no runtime state gets committed.

## 7. Configuration — nothing hardcoded

A new `intake:` section, absent from every v0.6.0 config and therefore fully defaulted
on load (backward compatible; `init` does not need to change to write it):

```yaml
intake:
  tracker: github               # github | none — selects the provider
  github:
    repo: ""                    # blank: infer from the git remote
    state: open
    limit: 500
    command: gh                 # the executable, so it is stubbable and overridable
  spec_sources:                 # in order of preference
    - PRODUCT.md
    - README.md
    - docs/PRODUCT.md
  spec_sections: [Scope, Plan, Features]
  thresholds:
    thin_issue_count: 3         # fewer than this against a whole product reads as thin
    feature_match_score: 0.5    # token overlap needed to call a ticket a feature's
    duplicate_title_score: 0.85
    duplicate_report_limit: 10  # closest near-duplicate pairs worth showing
```

Tracker source, paths, executable and every threshold are config. The GitHub
implementation is selected by `intake.tracker`, never assumed by the calling code.

A value that cannot be used as written raises `InvalidIntakeSettingError` naming the
setting and what was expected — `start` is the first command a new user runs, and a
traceback out of it is not a message. An explicitly empty `spec_sources: []` is honoured
rather than replaced by the default: "compare against nothing" is a legitimate ask.

## 8. Language constraint, made testable

Nothing printed by step 1 may require knowing what a lane, worktree, seat, glob or
branch is. Every user-facing string lives in `intake/presenter.py`, and a unit test
asserts that the rendered output for each case above contains none of a configured
banned-vocabulary list. That turns a style rule into a failing test.

Step 1 also **never tells the user to restructure their repository.** Lanes are globs
and can carve feature slices out of a messy tree without moving a file; that is #38's
business anyway, and nothing here comments on the folder layout.

## 9. Exit criteria (from #37's definition of done)

1. On a repository with **no issues**, `lanekeeper start` explains what product-playbook
   is and what to run, in plain language, and **exits without writing anything** —
   asserted by comparing the file tree before and after.
2. On a repository with `PRODUCT.md` **and** issues, it reports which listed features
   have no issue against them, naming them.
3. On a repository with issues and **nothing to compare them to**, it says it cannot
   judge coverage, reports counts and labels only, and does not guess.
4. **Nothing in this step requires the user to know what a lane is** — enforced by the
   vocabulary test.
5. Running `start` twice **resumes**: the second run skips a passed step 1 unless the
   issues or the spec changed.
6. The tracker sits behind an interface; a `FakeTracker` drives every test and no test
   touches the network.
7. `init` is unchanged and its existing tests still pass.
8. `lanekeeper start` never writes `config.yaml` within this session's scope.

## 10. Test plan

**Unit** (all dependencies injected, no network, no `gh`)

- `test_intake_trackers.py` — `NullTracker` availability wording; `GitHubIssuesTracker`
  builds the right argv and parses `gh` JSON, driven by an injected fake runner; a
  non-zero `gh` exit becomes unavailable-with-reason, never a crash; repo inferred from
  the remote and overridden by config.
- `test_intake_spec.py` — `PRODUCT.md` preferred over README; README used when there is
  no `PRODUCT.md`; `SpecSource.NONE` when neither; section parsing pulls features from
  Scope/Plan; a `PRODUCT.md` with no Scope section falls through honestly.
- `test_intake_coverage.py` — all features matched → `COVERED`; one feature with no
  ticket → `GAPS` naming it; no spec → `CANNOT_JUDGE` with an empty match list and no
  invented features; changing the threshold changes the matching (proves it is
  config-driven).
- `test_intake_quality.py` — flags for no-file-hint, no-labels, near-duplicate titles,
  one ticket naming several features; a clean backlog produces no flags.
- `test_intake_record.py` — round-trip; fingerprint stable across reruns; changing one
  issue title changes it; a corrupt record is discarded rather than crashing.
- `test_intake_language.py` — the vocabulary guard over every rendered case, a second
  guard that no case tells the user to reorganise their project, and the required
  sentences for each case.
- `test_intake_hardening.py` — the regressions from this feature's own review, grouped
  by the lie each one told: a stale record resumed after the ticket bodies or the
  thresholds changed; a stop with no stated reason; a `--take-as-is` pass replayed as a
  coverage finding; a URL or `Node.js` counted as a statement about which code a ticket
  touches; near-duplicate detection swamping the report on a large backlog; an unusable
  configured value raising a traceback.
- `test_config.py` (extend) — a v0.6.0 config with no `intake:` section loads with full
  defaults; round-trip preserves an edited `intake:` section.

**Integration** (real temp git repos, real files, fake tracker only)

- `test_start_step1.py` — the ground cases end-to-end through `cmd_start`, asserting
  exit codes and the presence of the required sentences; the no-issues case asserts an
  unchanged file tree; a two-run case asserting resume; a run asserting
  `.lanekeeper/config.yaml` is neither created nor modified.

**Regression** — the existing suite (`init`, capability gates, lanes, ports) stays
green; step 1 adds no import into any existing module's hot path.

## 11. Risks

- **Feature matching is heuristic.** Token overlap will miss a ticket titled in words
  the spec does not use. Mitigation: the report always names the issues it matched, so a
  wrong match is visible; `GAPS` is phrased as *"appears to have nothing written against
  it"*, not as a fact; and the threshold is config.
- **`gh` may be missing or unauthenticated.** That is an availability answer, not an
  error: the tracker reports why in plain words and step 1 falls to the "nothing to
  compare" path rather than crashing.
- **Spec parsing is markdown-shaped.** A `PRODUCT.md` written differently yields few
  features; the report says which file and which section it read, so a bad read is
  visible rather than silent.
