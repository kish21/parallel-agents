# 5. Coordinating agents with GitHub alone

You do not need an orchestration service. Everything required to run several agents on one
repository without collisions already exists in GitHub — a project board with custom fields,
milestones, issue dependencies, issue forms, and a few files in the repo. This chapter is the
mechanical half of the model: what to create, what each piece is for, and where GitHub cannot
help you.

## 5.1 Three axes, one job each

The single most common mistake is making one field carry two meanings. Keep three, and keep them
disjoint.

| Axis | Question it answers | Failure it prevents |
|---|---|---|
| **Lane** | Which part of the code does this touch? | Two agents editing the same file |
| **Seat** | Who is on it right now? | "Nobody knows who is doing what" |
| **Milestone** | Which shipment does it belong to? | No sense of how close a release is |

A ticket carries all three at once. Lane is the load-bearing one: **one lane, one seat, always.**
That single rule is what makes parallel work safe, and every other decision below exists to keep
it true.

## 5.2 The board

Create a project board and add three single-select fields beyond the built-in Status:

- **Lane** — one option per separable code area. Name them after paths, not features.
- **Owner** — the seniority the work needs. Follows the files, not the difficulty.
- **Seat** — `SR1`, `SR2`, `JR1`, `JR2`. The slot, never the vendor.

Stamp all three at creation. A ticket with a blank Seat is invisible: it belongs to nobody and
nobody notices it exists.

> **A label is not a board field.** Adding an `owner: senior` *label* does not populate the board's
> Owner *column*. They are separate systems that happen to share a word. Teams discover this when a
> lane board renders empty despite every ticket being labelled.

## 5.3 What GitHub cannot do for you

**If every agent pushes under one account, GitHub's people features are useless.** Assignees,
reviewers, CODEOWNERS and review routing all resolve to the same login, so none of them can tell
your seats apart. This is worth stating plainly because CODEOWNERS is the obvious-looking answer
and it does not work here.

The custom **Seat** field is the only thing on GitHub that distinguishes agents on a single-account
repository. Do not build routing on anything else.

**Issue forms cannot fill board fields.** A form can apply a fixed label; it cannot map a dropdown
answer to a project field. The answers land in the issue body as text and somebody still stamps the
card. Say so in the template rather than implying otherwise.

**Templates only apply in the browser.** Creating an issue from the command line bypasses them
entirely — which is how most agent-filed tickets are created. A template raises the floor for
hand-filed tickets and enforces nothing on agents.

## 5.4 Milestones — disjoint, never nested

An issue belongs to exactly **one** milestone, so milestones cannot contain each other. The natural
first sketch — a release milestone that "contains" the others — produces a release whose progress
bar reads a falsely small number, because the tickets are all filed under the children.

Make them **disjoint buckets** and treat the release as shipped when all of them close:

- one for the core capability
- one for the production-safeguards work
- one for whatever else blocks the launch

A milestone must be able to *end*. A permanent area of the system is not a milestone — that is what
Lane is for.

## 5.5 Dependencies and grouping

Two relationships are worth using deliberately.

**Blocked-by** marks a ticket that must not start yet. The card shows a stop icon, so an agent
picking up work sees the constraint before reading the body.

Use it for the case lanes cannot catch: **files that belong to no lane.** A central config file, the
application entry point, the router — these are read by every area, so two tickets in two different
lanes can still collide in them. A dependency is the only thing that serialises that.

**Parent and sub-issue** groups a lot so it lands on one seat. An analysis ticket that spawns three
fixes should parent them; the parent then closes when its children do, and the group cannot be split
across agents by accident. The parent also gets a progress bar for free.

## 5.6 The issue form

The goal is that whoever picks a ticket up next week can tell **when to stop** without asking.

Six required fields do that:

1. **Plain English** — no file paths, no jargon. If it cannot be explained without code, it is not
   understood yet. This is the field most often skipped and the one that makes a ticket readable.
2. **Evidence** — the line, the log, the query result. Separates "I think" from "here is the proof".
3. **Exit criteria** — testable statements someone else can check and get the same answer.
4. **Definition of done** — the standing bar, restated inline so it is visible while writing rather
   than remembered afterwards.
5. **Out of scope** — what this ticket deliberately does not do. This is what stops a ticket growing
   while an agent is inside it.
6. **Files and code areas touched** — this decides the Lane, and the Lane is what prevents
   collisions. Ask filers to name shared files explicitly.

Add Lane and Owner dropdowns whose options match the board exactly, each with an explicit
"not sure — needs a senior call" escape so nobody guesses.

## 5.7 Files in the repo

- **`.github/ISSUE_TEMPLATE/`** — the form above, plus a `config.yml` linking the working agreement
  so a filer meets the bar before typing.
- **An account-level `.github` repository** — a repo literally named `.github` supplies default
  issue and pull-request templates to every repository on the account that does not define its own.
  New projects inherit the setup with no copying. *Verify the behaviour for private repositories
  before relying on it; inheritance rules differ by visibility.*
- **`.githooks/`** — a pre-push hook running the full gate, and a pre-commit hook for the secret
  scan. ⚠️ Pointing git at a hooks directory **replaces** the default one, so a pre-push hook can
  silently disable an existing pre-commit hook unless the new directory provides both.
- **A secret-scan config** — run it on every push, including documentation-only changes. Secrets get
  pasted into markdown as often as into code.

## 5.8 Automation worth switching on

Project boards have built-in workflows. Two of them are worth more than they look:

- **Auto-add to project** — every new issue lands on the board automatically. Without it, tickets
  filed from the command line exist in the repository and nowhere else. This is the single most
  common cause of a board that silently disagrees with the issue list.
- **Item closed → Done** — cards move themselves.

Neither is code. Both are settings, and both prevent a failure that otherwise recurs weekly.

**Neither can be scripted.** Board workflows appear in no REST endpoint and in no part of the
GraphQL schema — there is nothing to call. Everything else in this chapter can be created from one
command; these two are clicks. Treat them as the last step of setting up a board, not as something
to get to later, because a board without auto-add looks correct right up until a batch of tickets
turns out to have never been on it.

## 5.9 Doing all of it in one command

`bootstrap.sh` creates the board, the three fields, the labels and the milestones, then prints the
two workflows above with a direct link. Its inputs live in `bootstrap.conf`; nothing about a
particular repository is baked into the script.

```
cp bootstrap.conf.example bootstrap.conf   # edit the lanes to match your paths
./bootstrap.sh --check                     # report the current state, change nothing
./bootstrap.sh
```

It is idempotent — re-running creates only what is missing — so it doubles as a drift check on a
repository somebody has been editing by hand. Two deliberate limits are worth knowing:

- **It never touches a field that already exists.** There is no command to add an option to a
  single-select field, and rewriting the field would unstamp every card carrying an old option.
  Add missing options on the board.
- **It does not stamp existing tickets.** It builds the empty structure. Backfilling Lane, Owner
  and Seat on a live backlog is a judgement call about which lane owns which paths, and that is not
  a thing to guess in a script.

The value is not the time saved. It is that the setup comes out identical every time, which is what
stops the half-configured board — fields but no auto-add, labels but no Seat — that produces most
of the failures in §5.12.

## 5.10 Gate design

Run the full gate locally on push rather than depending on hosted CI, which on a free plan is a
metered monthly budget and can be unavailable for the back half of every month (§5.11). A red or
absent remote check is not a reason to bypass branch protection — that is exactly when the guard
is doing its job.

One refinement worth making early: **give the gate path awareness.** A flat list of steps taxes a
documentation change with the entire test suite. A docs-only fast path pays for itself quickly, with
three rules that keep it honest:

1. **Fail closed.** Full gate by default; skip only when *every* changed path matches a strict
   allowlist. If the script cannot determine what changed, run everything.
2. **Always run the secret scan.** It is not part of what gets skipped.
3. **Announce the mode loudly.** A green run that skipped the suite must never look like a full pass.

## 5.11 Budgeting hosted minutes

Free minutes on a private repository are a **monthly budget that resets**, not a capability limit.
This distinction matters more than it sounds, because the two states are indistinguishable from the
pull-request page: a repository with a spent allowance and a repository with a broken build both
show a red cross on everything.

**Diagnose it from the run's annotation, not from the job log.** A budget block produces a run whose
jobs all fail within a few seconds, with no runner name and an empty step list, and whose annotation
names payments or the spending limit rather than any test. A real failure has steps. One command
settles it, and it is worth reaching for before reading a single line of code:

```
gh run view <run-id>          # read the ANNOTATIONS block
gh api repos/:owner/:repo/actions/permissions   # proves the feature is enabled at all
```

Two consequences catch people out. **Actions is still enabled** — nothing was switched off, so
checking the settings page finds nothing wrong. And **it fixes itself on the first of the month**,
which means a red cross that meant nothing in the last week of one month means something real in the
first week of the next. A team that has learned to ignore the mark keeps ignoring it.

**Set the spending limit explicitly to zero.** That converts the allowance into a hard stop rather
than an overage bill, and it is the same reasoning as putting a timeout on every hosted job.

### Where the budget actually goes

Minutes are billed against a multiplier, and the multiplier is the largest single lever:

| Runner | Cost per wall-clock minute |
|---|---|
| Linux | 1x |
| Windows | 2x |
| macOS | 10x |

A single macOS leg can eat a month that a Linux-only matrix would have survived. Each job also
rounds **up** to a whole minute individually, so a fan-out of many short jobs bills far more than
its wall-clock time suggests.

Four cuts, in the order they pay off. Together they roughly halve the burn without weakening what a
pull request proves:

1. **Run on pull requests only.** A workflow triggered on both the pull request and the push to the
   default branch tests the same tree twice, because a squash merge lands exactly what the pull
   request already proved green. This is a straight doubling and it is the most common one.
2. **Cancel superseded runs.** Without it, a fixup push leaves the previous run grinding through the
   whole suite on a tree nobody will merge. Seats revise branches constantly, so this compounds.
3. **Skip what a diff cannot affect.** Documentation-only changes skip entirely; a change confined
   to one lane runs that lane. Lanes already partition the repository, so the filter is a few lines
   of `git diff` against the pull request's base — deliberately not a marketplace action, because
   the gate must not grow a dependency that can change behaviour underneath it.
4. **Cache the dependency install.** It is easy to cache one ecosystem's install and leave a second
   one resolving from cold on every run, and easy not to notice, because both look identical in a
   green log.

### The trap in lane-gating a hosted gate

Cut 3 changes what a green check means, and the change is silent. **The hosted gate stops being a
mirror of the local gate and becomes a subset of it.** A green check on a single-lane pull request
has not re-proved the other lane; the pre-push hook has, because that always runs everything.

Three rules keep it honest, and they are the §5.10 rules pointed at hosted CI:

- **Fail open on anything unrecognised.** A changed path outside every known lane — the workflow
  itself, the gate script, root configuration — runs *all* lanes. A change to the gate must be
  proved by the gate, and an unclassifiable path must never resolve to "nothing to test".
- **Never gate the secret scan.** A secret can be committed from any path in the tree, including a
  documentation snippet, and it is the one failure that cannot be undone after a merge.
- **Write the subset rule down where the seats read it**, not only in the workflow file. Otherwise
  the next person reads a green check as a full pass, which is precisely what it no longer is.

## 5.12 Gotchas

Each of these cost real time.

- **A job that fails in four seconds is a bill, not a bug.** Zero steps, no runner, every job in
  the run dying together: that is an exhausted allowance refusing to allocate a runner, and the
  annotation says so in words. Hours get spent bisecting a test suite that never ran.
- **A merged pull request without a closing keyword leaves its ticket open forever.** A ticket can
  sit open through four merges with all its work delivered. Squash merges use the PR *title* as the
  commit subject — scan that for the keyword too.
- **A board and an issue list disagreeing is usually not a board bug.** Filtering issues by project
  only counts issues already on the board, so the two numbers measure different sets. Compare the
  repository's open count against the board's, not one filtered view against another.
- **Re-labelling one ticket to a different seat creates the exact collision lanes prevent** — unless
  it also moves to a lane that seat already owns. Move whole lanes, not single tickets.
- **A backlog is rarely symmetric.** One seat can end up holding most of the work while others idle.
  Check the distribution periodically; visible allocation is not the same as balanced allocation.
- **When one seat's backlog empties, moving tickets will not fix it** if the remaining work genuinely
  requires more seniority. Split along the interface seam — one side owns the presentation files, the
  other owns the service — so neither touches the other's files.
