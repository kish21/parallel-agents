# parallel-agents — build plan

> Local working folder. **Not a git repo yet.** Created 2026-08-25.
> Push to a PRIVATE GitHub repo on **Saturday 2026-08-29**. Public later, only if decided.
>
> **Vendor-neutral and project-neutral.** No project names, no dates, no incident references,
> no employer signals. Findings are described generically. This applies to every file here,
> including this one.

## What this repo is

A guide for running several AI coding agents in parallel on one codebase without them
colliding — seats, lanes, worktrees, ports, review chains, and what to do when one agent's
harness is weaker than another's.

## The two ideas it exists to publish

1. **Seats are capped by non-overlapping code lanes, not by how many agent subscriptions you
   own.** If the codebase has four clean lanes, a fifth seat produces collisions, not a fifth
   stream. You scale by finding more separable lanes — which usually means the architecture
   got more modular, not that you bought more seats.

2. **You cannot make a weaker harness produce equal work — so you make it declare itself.**
   A seat whose capability card says `author-required` does not quietly hand in a thinner
   review. It names in the PR which gate it actually ran, and stops entirely when the change
   touches money, auth, tenant isolation, or a migration.

## Core design (validated in practice, not theory)

- **Seat = slot. Vendor = a line on a card.** Seats are `SR1`, `SR2`, `JR1`, `JR2`. Which
  agent fills a slot lives in a per-checkout `.lane` file. Swapping vendors edits one file:
  no branch renames, no folder moves, no board churn.
- **Lane = a set of file paths**, never a topic and never a seniority level. One lane, one
  owner. Grouping work by feature is what causes collisions; grouping by the paths a ticket
  touches is what prevents them.
- **Orchestrator is defined by capability, not by name**: the seat whose card reads `native`
  for both deep-review and security-review. Vendor-neutral rule, vendor-specific answer.
- **Capability states are three, not two**: `native` / `author-required` / `unavailable`.
  `author-required` means the harness *can* do it but nobody has written it yet — a very
  different risk from "cannot", and the distinction is load-bearing.
- **One process document, thin per-agent wrappers.** Never fork the process file per vendor.
- **Swap vendors only at a ticket boundary**, never mid-ticket — a half-finished branch
  carries context that lives in the agent's session, not in the repo.
- **Decide the trial test before the trial**, not on day six.

## Outline

1. **Working agreement** — the bar, per-feature contract, security definition-of-done,
   never-merge-without-the-owner.
2. **Conflict management** — worktrees vs clones, one lane one owner, the ports table,
   migration-number collisions, never two branches in one lane.
3. **Orchestration** — seats, capability cards, orchestrator rule, scaling 2 → 4 → 6,
   reviewer mapping, the trial test.
4. **Per-agent setup** — the exact prompt for each harness, and how to write a capability card.
5. **Coordinating with GitHub alone** — board fields (lane/seat/owner), disjoint milestones,
   blocked-by and sub-issue grouping, the issue form, account-level defaults, hooks, and gate
   design. WRITTEN: `05-github-mechanics.md`.
6. **Running on the free tier** — what the free plan withholds (server-side rules, metered runs),
   the prevent/detect/recover split, the verified mirror, and why the gate allowance divides by the
   number of seats.

## Findings — the GitHub coordination layer

Written up in section 5. Listed here so none is lost.

- **A board and an issue list can disagree for a boring reason.** Filtering issues by project only
  counts issues already on the board, so two views measure different sets. A batch of tickets had
  never been added at all, and nothing surfaced it.
- **A ticket can stay open through four merges of its own work** because no pull request carried a
  closing keyword.
- **On a single-account repository, every people-based routing feature collapses.** Assignees,
  reviewers and CODEOWNERS all resolve to one login. Only a custom board field separates seats.
- **Milestones cannot nest** — one per issue — so a release milestone that "contains" others reports
  a falsely small progress number. Make them disjoint and treat the release as the union.
- **Lanes do not cover files that belong to no lane.** A central config file or the application
  entry point is read by every area; two tickets in different lanes still collide there. A
  blocked-by dependency is the only thing that serialises it.
- **Re-labelling a single ticket to another seat creates the collision lanes exist to prevent**
  unless the lane moves with it. Move whole lanes.
- **A seat's backlog emptying is not a distribution problem** when the remaining work genuinely
  needs more seniority. The fix is splitting along the interface seam, not moving tickets.
- **Pointing git at a hooks directory replaces the default one**, so adding a push gate can silently
  disable an existing pre-commit secret scan.
- **A gate with no path awareness taxes every documentation change with the full test suite.** A
  docs-only fast path is worth it, but only fail-closed, with the secret scan always running and the
  skip announced loudly.
- **Board workflows have no API.** Auto-add and closed-to-Done appear in neither REST nor GraphQL,
  so the one part of the setup that most needs automating is the one part that cannot be. A bootstrap
  script has to end by naming them rather than quietly leaving the board half configured.
- **Issue forms cannot fill board fields and do not apply to command-line filing.** They raise the
  floor for hand-filed tickets and enforce nothing on agents. Say so in the template.

## Findings — shared state and collisions (section 2)

Harvested from the same setup. None of these is written up yet; section 2 is where they land.
Lanes partition the *repository*. Every one of these is a thing the seats still share.

### The self-chosen identifier

- **Never let a seat choose an identifier by looking at what already exists.** Each seat named its
  write-up with the next number after the highest in the folder. Three seats looked at the same
  moment and picked the same number. "Check again just before you file" cannot fix it: the gate run
  between looking and landing takes several minutes, and that gap is exactly when somebody else
  files. With four seats it is arithmetic, not carelessness. Name artefacts after an identifier the
  forge already guarantees unique — the ticket number — so there is nothing to look up.

- **A shared index file is the worse half of that problem, and the half nobody predicts.** Beside
  the numbered folder sat one contents page that every entry adds a line to, at the same spot.
  Every hold-up in the incident was the contents page; the number was only what the argument was
  about. Fix it in three layers: generate the page from the folder so nobody hand-edits it, add a
  test that fails when it drifts, and set the merge strategy for that one path to keep both sides.
  Filing then touches only your own new file.

- **A rule learned for one generated artefact must be applied to every artefact of the same shape.**
  The same repository already carried a written rule against hand-editing one generated folder, with
  a test enforcing it. The sibling folder with the identical shape was never covered, and produced
  the incident. When you write a rule like this, grep for the shape, not the folder.

- **The process file is usually the mechanism.** The instruction every session followed said, in as
  many words, to pick the next number by looking at the folder. Fixing the folder without fixing
  that line means the next session recreates the collision on day one. Same family as the rotting
  prompt below, but sharper: the process document was not merely stale, it was the cause.

### One repository, one runtime

- **Lanes split the code. They do not split the database.** Every seat points at one live schema. A
  seat that applies a schema change from an unmerged branch puts the live database ahead of the
  default branch and blocks every other seat's changes, and the vendor tool's own suggested repair
  makes it worse by recording an applied change as never-run. Hold schema changes until the branch
  merges, confirm state with a read-only listing rather than a plan, and design them to be safe in
  either order where you can.

- **Two seats independently stamped the same timestamp on a schema change, and the second was
  silently skipped.** Both picked a round hour. The tool keys on the number, not the filename or the
  contents, so it reported nothing pending — which looks exactly like a missing file or a wrong
  branch. Same disease as the self-chosen counter above, in a different organ. Stamp to the minute,
  and list both checkouts before applying: the other lane's file is invisible from this one.

- **Worktrees share one repository, so only one can hold the default branch — and usually none
  does.** Merge tooling then fails on a step *after* the merge already succeeded, which reads as a
  failed merge and invites a retry. Check which worktree holds what rather than assuming a layout;
  it is a race, not a fixed arrangement. Move the local pointer without checking the branch out.

- **The stash is shared across worktrees, and a path-scoped stash can silently create no entry.**
  The pop then applies somebody else's, conflicting unrelated files in one command. Rule: never
  stash in a multi-seat checkout. Read the diff or copy the file aside instead.

### The tree somebody is standing in

- **Writing into a checkout while a human is testing in it destroys their unsaved work.** The dev
  server watches the tree, reloads the browser, and the symptom presents as the feature failing to
  save. Park edits elsewhere until they report back.

- **Branch churn in a running tree leaves the process serving a mixture of old and new code.** The
  code on disk is correct and consistent, so reading it will never find the fault. Suspect a stale
  process before a stale understanding, and restart cleanly rather than relying on a reloader.

- **When several seats merge continuously, a branch more than a few hours old is behind by
  construction.** So a ticket that disagrees with the code in front of you is a branch-point
  question first and a stale-ticket question second. Fetch and diff against the default branch
  before analysing anything, and re-run a published measurement rather than patching its conclusion.

### Belongs elsewhere, parked here so it is not lost

- **Agent session cost grows faster than session length, because every step re-reads the whole
  history.** Nearly all of one month's spend was re-reading context in a handful of very long
  sessions, not producing output. This is the real argument for ending at a ticket boundary, and it
  belongs in section 3 beside the seat model, not here.

## Source material — findings from a real 4-seat setup

Each of these is a war story the guide needs. All stated generically.

- **A hand-copied prompt rots.** One in real use carried three stale rules: it named a test
  gate that had been replaced *because it measured the wrong thing*, it taught a
  file-follow-ups rule that had been reversed the same day, and its issue-filing recipe
  skipped the steps that make a follow-up visible on the board. The fix is not discipline —
  it is to stop inlining rules and point at the source instead.
- **Swapping a vendor between seats cost exactly one file**, and the stamped tickets never
  moved. Evidence that slot-vs-vendor separation pays for itself immediately.
- **A tracked Makefile hardcoded the backend port**, so every worktree claimed the same one.
  Seats only worked because a human remembered a flag.
- **The backend port was baked into the frontend env file 25 times.** Copying that file to a
  new seat silently points one seat's browser at another seat's server — it looks like it
  works.
- **The dev server had no port pinned**, so it auto-incremented. Ports were accidental, not
  configured, which defeats "check the port before debugging the feature".
- **A backlog is rarely symmetric.** Seats should follow the ratio of the work, not be
  created in matched senior/junior pairs.
- **A board field for the seat should be explicit, not an exception list** — the owner asked
  for every item stamped rather than relying on a negation filter, and was right: explicit
  filters are easier to reason about than "everything except".

## Feature inventory — what the platform actually gave us

Measured against a live four-seat repository, not recalled. Each row says what the feature bought
*for parallel work specifically* — a feature can be excellent and still be worth nothing here.
This is raw material for a chapter, and an audit anyone can re-run on their own repository.

### Earned its place

| Feature | What it bought in parallel work |
|---|---|
| **Project board, three custom single-select fields** | The whole coordination layer. On a single-account repository this is the *only* thing that separates seats. Written up in section 5. |
| **Milestones, kept disjoint** | A truthful progress number per shipment. Three buckets, no nesting, release = all of them closing. |
| **Sub-issues / parent-child** | Keeps a group of related work on one seat so it cannot be split by accident, and gives the parent a progress bar for free. The board surfaces both as columns without configuration. |
| **Issue form** | Raises the floor on hand-filed tickets. Enforces nothing on command-line filing, which is how agents file. |
| **Pull-request template** | The one place a seat declares which gate it actually ran. Load-bearing for the weaker-harness rule in section 3. |
| **Labels** | Filtering the issue *list*, which the board cannot do. Not a substitute for a board field, and the count grows unmanaged — an audit is overdue. |
| **A hooks directory in the repo** | The real gate. Both hooks must live there together: pointing git at the directory *replaces* the default one. |
| **Line-ending and merge attributes** | Two distinct wins. Pinning shell scripts to one line ending is what makes the gate installable at all on a mixed-platform team. Setting the generated index to keep both sides is what stopped the shared-index collision. |
| **Dependency update bot** | Free, and the one piece of maintenance no seat has to own. |
| **Process documents committed in the repo** | The fix for the rotting hand-copied prompt: seats point at a path instead of carrying a copy. |

### Paid for, delivered nothing

- **Hosted CI is present but never actually runs.** A workflow file exists, pushes and pull requests
  trigger runs, and every job comes back failed with **zero steps and no logs** — the signature of a
  job that was never scheduled, not one that ran and found a bug. The effect is worse than having no
  CI: **every pull request carries a red mark that means nothing**, which trains a team to ignore red
  marks, including a real one later. If you cannot make hosted CI run, delete the workflow rather
  than leave a permanent false signal.

- **Branch protection and repository rulesets are both unavailable** on a private repository on the
  free tier — the API refuses with an upgrade notice. So there is **no server-side merge gate at
  all**. Worth stating plainly because the standing rule "never bypass branch protection" quietly
  assumes something is there to bypass. What exists is a local pre-push hook, which is a *convention*
  any seat can skip with one flag. Either pay for the tier, make the repository public, or write the
  guide's merge discipline as what it actually is: an honour system with a helpful local check.

### Not used, ranked by what they would buy

1. **Saved board views, one per seat.** Filter on the Seat field, save as a tab, or group by Seat for
   swimlanes. Costs nothing, needs no code, and removes the daily friction of every seat scanning one
   long shared column. Highest value of anything on this list.
2. **The two board workflows** — auto-add, and closed moves to done. Cannot be scripted, must be
   clicked, and their absence is the single most common cause of tickets that exist and are on no
   board.
3. **Issue types**, a newer platform field that is a first-class attribute rather than a label. Worth
   evaluating as a replacement for one label axis, which would shrink an unmanaged label set.
4. **An account-level defaults repository**, so new projects inherit the templates instead of copying
   them. Verify the behaviour for private repositories before relying on it.
5. **Code owners.** Listed for completeness and probably not worth doing: on a single-account
   repository every path resolves to one login, and nobody is asked to review their own pull request.
   Cheap to disprove, so disprove it rather than assuming either way.
6. **Merge queue.** Unavailable without branch protection, so blocked behind the tier question above.

### Action items — decide later, do not silently drop

- [ ] Add the saved per-seat views and confirm whether grouping beats tabs in practice.
- [ ] Settle the hosted-CI question: make it run, or delete the workflow so the red mark stops lying.
- [ ] Settle the tier question, then rewrite the merge discipline to match what is actually enforced.
- [ ] Test whether code owners does anything at all on a single-account repository, and record the
      answer either way — the guide currently asserts it does not.
- [ ] Audit the label set against the three board fields; delete anything that duplicates a field.
- [ ] Evaluate issue types against the label axis they would replace.
- [ ] Re-run this inventory as a checklist in the finished guide, so a reader can audit their own
      repository rather than read ours.

## Running this on the free tier

Most writing about multi-agent setups quietly assumes a paid plan. The two controls this guide
leans on hardest — a protected branch and a hosted gate — are exactly the two the free tier
withholds on a private repository. That is worth a chapter of its own, because the answer is not
"pay up", and it is not "do without".

### First, stop conflating three different controls

The instinct is to call a backup an alternative to branch protection. It is not, and the guide must
not say so. They sit at different points and you need to name which one you are buying:

| Control | Question | Free tier, private repo |
|---|---|---|
| **Prevent** | Can a bad change land on the default branch? | **Not available.** Server-side rules refuse with an upgrade notice. |
| **Detect** | Did the default branch move in a way nobody intended? | Available, and cheap. Nobody does it. |
| **Recover** | Can we get a known-good history back? | Available, and cheap. |

A mirror buys **detect** and **recover**. It buys no prevention at all: a force-push still lands,
you just find out and can undo it. Say that plainly in the chapter, or a reader will switch on a
backup and believe they are protected.

### The one move that returns both controls

**Making the repository public restores server-side rules *and* unmetered hosted runs on standard
hardware, together, for nothing.** For a guide, a scaffold, or a tool, that is the whole answer and
it should be the first option offered. It is only wrong when the code genuinely cannot be public —
which is a business decision, not a technical one, and worth making deliberately rather than by
default. This repository itself faces exactly that choice, which is a fair thing to say out loud.

### The mirror, and how to make it worth more than a backup

A plain backup is a copy. The version worth documenting is a **verified mirror**: the mirror is
written *only* by a path that has already run the gate. Then the mirror is, by construction, a
history that passed — which is much closer to what a protected branch gives you than a raw copy is.
A poor team's protected branch, running on the honour system, but with a receipt.

Mechanics, all standard git, nothing to buy:

- A bare mirror clone, updated by pushing all refs. Run it from the same place the gate runs, after
  the gate passes, so an unverified push never reaches it.
- A scheduled comparison of the working remote's default branch against the mirror's. Any divergence
  that is not a fast-forward means somebody did something the missing rule would have blocked. That
  comparison **is** the detection control, and it is a few lines.

Where to put the copy, weakest to strongest:

1. **A second repository under the same account.** Separate namespace, no protection against losing
   the account.
2. **A free organisation on the same platform.** Cleaner separation, still one account behind it.
3. **A different host, or an offline bare mirror on separate storage.** The only options that
   survive losing the account.

⚠️ **Not a second personal account.** The platform's own terms allow one free personal account per
person, so "put the backup on another free login" is advice to break them. Use an organisation, a
different host, or an offline copy.

### A hosted gate with no minutes

Free minutes are metered on private repositories and reset monthly, so a busy repository burns
through them and every later run dies before it starts. **The signature is a job that reports
failure with zero steps, no runner name and no logs, within seconds, on every job at once** —
worth memorising, because it looks nothing like a test failure and people debug it as one for an
hour. The run's *annotation* names the cause in plain words (payments or the spending limit), so
read that before the log. The feature is still enabled; only runner allocation is refused, which
is why the settings page looks fine. It clears itself on the first of the month — so the same red
mark that meant nothing last week can mean something real this week.

In rough order of what to reach for:

1. **Make the repository public**, per above. Unmetered on standard runners.
2. **Run a self-hosted runner on a machine you already own.** Unmetered, because it is your
   hardware, and it is the direct answer to an exhausted allowance. One hard rule: never attach one
   to a public repository, because an untrusted contribution would execute on your machine.
3. **Treat the local gate as the real gate, and make that honest.** It is a convention, not an
   enforcement, so the pull-request template has to carry which gate the seat actually ran. This is
   the same declare-your-capability move the guide already applies to weaker harnesses, pointed at
   infrastructure instead of an agent.
4. **Delete the workflow if it cannot run.** A permanent red mark on every pull request is worse
   than no mark, because it trains everybody to ignore red — including the real one, later.
5. **Spend the allowance better** before concluding it is too small: skip runs on paths that cannot
   break anything, cancel superseded runs, cache dependencies, and cut duplicate legs.

### Why this belongs in *this* guide and not a general CI article

**Your allowance divides by the number of seats.** Four seats push roughly four times as often, so a
budget that comfortably fits one developer runs dry partway through the month, and it presents as a
platform fault rather than as a consequence of adding seats. Two direct effects:

- **Budget the gate per seat, not per repository**, when deciding how many seats a codebase can
  carry. Seats are capped by lanes first and by gate capacity second, and the second cap is real.
- **Cancel superseded runs.** Seats revise branches during review constantly, and without
  cancellation the allowance is spent on runs whose results nobody will ever read.

### Action items

- [ ] Decide the public-or-private question deliberately, and record the reason either way.
- [ ] Stand up a verified mirror, written only after the gate passes; pick a destination from the
      list above and say which failure it does and does not survive.
- [ ] Add the scheduled divergence check, and define what a non-fast-forward on the default branch
      should trigger.
- [ ] Try a self-hosted runner on an existing machine before accepting that there is no hosted gate.
- [ ] Either make the hosted workflow run or remove it, so no pull request carries a mark that means
      nothing.
- [ ] Add cancellation of superseded runs and path filters, then measure the burn per seat.

## Steps

- [x] Write sections 1–3 locally, in this folder (`01-working-agreement.md`, `02-conflict-management.md`, `03-orchestration.md`)
- [x] Write section 4 (per-agent setup) — `04-agent-setup.md`
- [x] Write section 5 (GitHub mechanics) — `05-github-mechanics.md`
- [x] Write section 6 (free-tier operations) — `06-free-tier-ops.md`
- [x] Add `README.md` — 5-minute quickstart replication guide
- [x] Add `bootstrap.sh` — one script creating the board + fields + labels + milestones, and
      naming the two workflows that cannot be scripted. Highest-value artefact: doing this by
      hand is what produces off-board tickets. Config in `bootstrap.conf.example`; documented
      as section 5.9.
- [x] Add `templates/` — issue forms, PR template, pre-push/pre-commit hooks, CI config, gitattributes, .lane example
- [ ] Add trial evidence once the seats have run several days
- [x] Re-read every file for project/vendor/date leakage before any push
- [x] Public repository decided for unmetered CI & branch rulesets
- [ ] Initialize git repo and push to public GitHub repository

## Open decisions

- Final name: `parallel-agents` (chosen) — alternatives were `agent-lanes`, `pit-crew`
- Whether the capability-map spec lives here or in the author's separate phase-skills repo.
  Current thinking: the phase-skills repo owns it (that is where capabilities are invoked);
  this repo references it.
