# Getting started with lanekeeper

**Read this if you have never used lanekeeper and want to know whether it is worth
your time, and exactly what to type if it is.**

Everything on this page is real output from lanekeeper 0.7.9 run against
[mini-issue-tracker](https://github.com/kish21/mini-issue-tracker), a small React
project with three open tickets. Nothing here is illustrative or approximate. Long
paths are shortened to `…/repo` for readability, and that is the only edit.

**Contents**

1. [Is this for you?](#1-is-this-for-you-decide-in-thirty-seconds) — including when the answer is no
2. [The five words this page uses](#2-the-five-words-this-page-uses)
3. [What you need before you start](#3-what-you-need-before-you-start)
4. [Install](#4-install)
5. [Your first agent, start to finish](#5-your-first-agent-start-to-finish)
6. [The daily loop: which command do I run?](#6-the-daily-loop-which-command-do-i-run)
7. [When the gate says no](#7-when-the-gate-says-no)
8. [Tickets that name no files](#8-tickets-that-name-no-files)
9. [No GitHub issues, or no `gh`?](#9-no-github-issues-or-no-gh)
10. [Two agents at once](#10-two-agents-at-once--and-the-warning-you-must-not-ignore)
11. [Making GitHub enforce it](#11-making-github-enforce-it)
12. [Finishing with an agent](#12-finishing-with-an-agent)
13. [Removing lanekeeper completely](#13-removing-lanekeeper-completely)
14. [Troubleshooting](#14-troubleshooting--every-message-you-are-likely-to-hit)
15. [Honest limits](#15-honest-limits)
16. [Where to go next](#16-where-to-go-next)

**In a hurry?** Sections 4 and 5 are the whole of it: install, then one command per
ticket. Everything else answers a question you will have later.

---

## 1. Is this for you? Decide in thirty seconds

**Use lanekeeper if all three of these are true:**

1. You run **two or more AI coding agents** (Claude Code, Cursor, Codex, anything) on
   **one repository**, at the same time or over the same few days.
2. You have **written-down work** — GitHub issues, a backlog, tickets. One sentence per
   ticket is enough; a ticket that lists the files it touches is ideal.
3. Two agents changing the same file, and finding out at merge time, would cost you
   real time.

**Do not use lanekeeper if:**

- You run **one agent at a time**. There is nothing to keep apart. Git already does
  everything you need.
- Your agents already work on **separate repositories**. Same reason.
- You want a tool that **assigns, prioritises or writes** the work. Lanekeeper divides
  work that already exists. Writing it down is
  [product-playbook](https://github.com/kish21/product-playbook)'s job, or yours.
- You want **autonomy** — agents that decide what to do next. Lanekeeper is the
  opposite: it is a fence, and fences do not make decisions.

**What it will not do, stated plainly, so you do not wait for it:**

- It does not write code, run your agents, or review their output.
- It does not stop an agent from *reading* any file. The boundary is on what a change
  may contain, not on what an agent may look at.
- It does not merge, deploy, or talk to your CI beyond one generated GitHub Action.
- It cannot tell two agents apart inside one lane. **One lane, one agent** — the tool
  refuses a second one for exactly this reason.

---

## 2. The five words this page uses

You need these five. Nothing else on this page is jargon.

| Word | What it means |
| :--- | :--- |
| **Lane** | A set of file paths one agent is allowed to change. Usually one ticket's file list. |
| **Policy** | The file listing every lane: `.lanekeeper/config.yaml`. It is checked into git, and it is the only thing the gate reads. |
| **Worktree** | A second, separate checkout of your repository, one per agent, so two agents never share a working directory. Git makes these; lanekeeper manages them. |
| **Gate** | The check that fails a change containing a file outside its lane. It is a set intersection over file patterns — no model, no judgement. |
| **Seat** | A capability level (`SR1`, `JR1`, …) deciding whether that agent may touch gated paths such as database migrations. Seats are numbers, not personalities. You can ignore seats until you need them. |

---

## 3. What you need before you start

Check each of these. If one fails, fix it before going on.

| Requirement | How to check | If it fails |
| :--- | :--- | :--- |
| **Python 3.9 or newer** | `python --version` | Install Python from python.org. |
| **Git 2.5 or newer** | `git --version` | Any git from the last decade is fine. Worktrees need 2.5. |
| **A git repository with at least one commit** | `git log --oneline -1` | Lanekeeper works on a repository, not a folder. |
| **You are at the repository root** | `git rev-parse --show-toplevel` prints your current directory | `cd` there, or use `lanekeeper --repo <path>` from anywhere. |
| **Your tickets are reachable** *(only for `--ticket`)* | `gh auth status` | Install the [GitHub CLI](https://cli.github.com) and run `gh auth login`. Or skip tickets entirely and declare lanes yourself — see §9. |

You do **not** need: a GitHub project board, a `PRODUCT.md`, an existing CI setup, or
any change to how you run your agents.

---

## 4. Install

```bash
pip install --upgrade lanekeeper
lanekeeper --version
```

```
lanekeeper 0.7.9
```

<details>
<summary><strong>Windows: <code>lanekeeper</code> is "not recognized as the name of a cmdlet"</strong></summary>

Microsoft Store Python installs the command into a folder that is not on your `PATH`,
so `pip install` succeeds and the command does not exist. This is not a broken install.
Everything works through the module instead:

```powershell
python -m lanekeeper.cli --version
```

To type `lanekeeper` the way this page does, define it for the session:

```powershell
function lanekeeper { python -m lanekeeper.cli @args }
```

Or add the Scripts folder to your user `PATH` permanently — `pip show -f lanekeeper`
reports which one it is; it looks like:

```
%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\Scripts
```
</details>

---

## 5. Your first agent, start to finish

Six steps. Type them in order. Expected output is shown after each.

### Step 1 — Check what lanekeeper thinks of your repository

```bash
lanekeeper status
```

On a repository that has never seen lanekeeper you get this, and **it is not an
error you need to fix** — it is the tool telling you which command comes first:

```
❌ Error loading lanekeeper state: No lanekeeper configuration found at
…/repo/.lanekeeper/config.yaml. Hand a ticket to an agent and one is written for you:
'lanekeeper spawn --ticket <number>'.
```

### Step 2 — Hand one ticket to one agent

Pick any open issue number. **This is the whole setup** — there is no separate `init`
step, and running one first would only get in the way. (No ticket tracker? Skip to §9,
which starts differently and rejoins here.)

```bash
lanekeeper spawn --ticket 2
```

```
📁 Wrote .lanekeeper/config.yaml and the seat cards: this is the first agent on this project.
🎫 Ticket #2: [FEAT-02]: Automated Semantic Clustering Engine with Gemini & Mock Fallback (M2)
   Lane 'feat-02', bounded by the ticket's own file list:
     src/domain/contracts.ts
     src/providers/llm/llmProvider.ts
     src/prompts/clusteringPrompt.ts
     src/services/clusterService.ts
     src/components/features/ClusterCard.tsx
     tests/unit/clustering.test.ts
   Written into the policy so the pull-request gate checks the same boundary.

🔨 Creating Git worktree for agent-001 on branch 'parallel/agent-001/2-feat-02-automated-semantic-clustering'...

🚀 Agent 'worker-1' (agent-001) successfully spawned!
  • Worktree: …/repo/.lanekeeper/worktrees/agent-001
  • Branch:   parallel/agent-001/2-feat-02-automated-semantic-clustering
  • Lane:     feat-02
  • Ports:    backend: 8001, frontend: 3001
  • Seat:     JR1
```

**What just happened, line by line:**

- **The file list came from the ticket itself.** Lanekeeper read the issue body and
  took the paths it names. It did not guess and it did not ask a model. If your ticket
  names no files, see §8 — you will be told, not given a boundary that does not exist.
- **A worktree was created.** A separate checkout at
  `.lanekeeper/worktrees/agent-001`, on its own branch. Your own working directory is
  untouched. **It appearing in your editor's sidebar is expected, not a fault.**
- **Ports 8001 and 3001 were reserved** for this agent, and written into a `.env` in
  its worktree, so two agents running dev servers do not fight over port 3000.
- **`.lanekeeper/config.yaml` was written** — that is the policy, and it now contains
  lane `feat-02` with those six paths. It is short: only the lanes and whatever differs
  from the defaults, so the file is dominated by what you care about and picks up
  improved defaults when you upgrade. The lane also records where it came from:

  ```yaml
  - name: feat-02
    allow:
    - src/domain/contracts.ts
    …
    ticket: '2'
    paths_from: ticket        # ticket | flag (--allow) | proposed (--propose, accepted)
  ```

  When a ticket is finished, add `retired: true` under its lane. That is bookkeeping,
  not enforcement: the collision report and CODEOWNERS skip a retired lane, `spawn`
  refuses it without `--force`, and the gate checks it exactly as before. `cleanup`
  suggests it at the natural moment; the edit is always yours.

### Step 3 — Commit the policy

```bash
git add .lanekeeper .gitignore && git commit -m "Add the lane policy"
```

Do this **now**, before anything else, **in this checkout** (not inside the agent's
worktree), on whatever branch you are on. `spawn` says exactly that:

```
  • Commit the policy before you commit anything else — in this checkout, not inside
    the agent's worktree, and ideally on a branch of its own, opened as a pull request
    labelled 'lane: policy'. …
```

On a branch other than the default it names that branch instead. It never tells you to
commit to a branch the policy itself lists as protected. Land the commit as a pull
request labelled `lane: policy`, like any other change. Two reasons, both learned the
hard way:

1. CI can only enforce a policy that is in the repository.
2. Left uncommitted, your next `git add -A` sweeps it into whatever branch you happen
   to be on — including an agent's, where the gate correctly denies it and the error
   is baffling.

### Step 4 — Do the work in the agent's worktree

Lanekeeper prepared the desk. It does not write code, and it does not install
anything. `spawn` ends with the numbered steps, read from your project:

```
▶ Now do the work. Lanekeeper has prepared the desk; it does not write code.

  1. Once per worktree, install the dependencies — a worktree is a fresh
     checkout, so it has none (package-lock.json says how):

            cd .lanekeeper/worktrees/agent-001 && npm ci

  2. Open .lanekeeper/worktrees/agent-001 in your editor ('lanekeeper open agent-001' does it),
     then start your coding agent there: claude, cursor, whatever you use.
```

**A worktree has no `node_modules`.** It is a checkout of tracked files, so tests and
dev servers fail there until you run the install once. Lanekeeper names the command
from your lockfile (`package-lock.json` → `npm ci`, `pnpm-lock.yaml`, `yarn.lock`,
`uv.lock`, `poetry.lock`); a project with a manifest but no lockfile is told the install
is its own call; a project with neither gets no line. It is never run for you.

```bash
lanekeeper open agent-001        # opens the worktree in your editor (VS Code by default)
```

`open` repeats the install line, and one more: *if `lanekeeper` is not found in that
window, `python -m lanekeeper.cli` is the same program.* The window your editor opens
carries the editor's `PATH`, not your terminal's, and on a Microsoft Store Python the
shim is not on it. Every "run this next" line lanekeeper prints uses the form you
started it with; set `LANEKEEPER_INVOCATION=lanekeeper` if you use the PowerShell
wrapper function from §4 and want the short form printed back.

Then give the agent its task **and its boundary**. `spawn` printed a prompt that
carries both — copy it verbatim:

```
Implement [FEAT-02]: Automated Semantic Clustering Engine with Gemini & Mock Fallback
(M2) (#2). You may only create or modify these files: src/domain/contracts.ts,
src/providers/llm/llmProvider.ts, src/prompts/clusteringPrompt.ts,
src/services/clusterService.ts, src/components/features/ClusterCard.tsx,
tests/unit/clustering.test.ts. If the task needs a file that is not in that list, stop
and say so instead of editing it — a change outside the list is rejected before it can
merge.
```

The same list is in `.lanekeeper/worktrees/agent-001/.lane`, so an agent that reads its
own working directory finds it without being told.

### Step 5 — Check the boundary before opening a pull request

From inside the agent's worktree:

```bash
lanekeeper check --lane feat-02 --base main --working-tree
```

```
🛡️  LANE CHECK — lane 'feat-02', main...HEAD
  in …/repo/.lanekeeper/worktrees/agent-001 — agent-001's worktree, lane 'feat-02'

  ✓ All 2 changed files stay inside the lane.

✅ CHECK PASSED
```

`--working-tree` includes changes that are not committed yet. Leave it off to check
only what is committed, which is what CI does.

**The second line says where it ran.** With two identical-looking editor windows open,
running the check in the wrong one is easy, and the verdict is then correct about the
wrong question. In the main checkout it says so and names the worktrees that exist; in
a worktree asked about a different lane than its own it warns above the verdict:

```
  ⚠️  This worktree's .lane says 'feat-02', but the check was asked about 'feat-03'.
      If this is agent-001's work, you probably meant --lane feat-02.
```

Inside a worktree, `check` reads the policy from the main checkout whenever the two
differ, and says so — that is the copy being maintained and the one CI reads once it is
committed.

**On the very first agent you will also see this line, and it is expected:**

```
ℹ️  This checkout has no policy of its own; reading the one in …/repo.
   Commit the policy on 'main' so the gate in CI reads it too.
```

The worktree was branched from a commit made *before* you committed the policy in step
3, so the policy is not in it yet. Nothing is wrong. To clear it, from inside the
worktree:

```bash
git merge main
```

Agents spawned after step 3 never see this line.

### Step 6 — Open the pull request, and label it

From inside the agent's worktree, commit and push its branch:

```bash
git add -A && git commit -m "FEAT-02: clustering engine"
git push -u origin HEAD
```

Then open the pull request and give it **exactly one label naming the lane**:

```
lane: feat-02
```

With the GitHub CLI, creating the label once per lane and then the PR:

```bash
gh label create "lane: feat-02" --color 0e8a16 --description "Lanekeeper lane"
gh pr create --fill --label "lane: feat-02"
```

In the web UI, type the label name in the Labels box and GitHub offers to create it.

The label is the declaration a reviewer can see and change without a checkout, and it
wins. **A branch lanekeeper made already carries its lane in its name**, so the gate
(with `--lane-from-branch`, which `install-gate` turns on) reads the lane from the
branch when no label is present. A label that disagrees with the branch fails,
naming both: that is the mislabelled pull request, the one case the tool can catch.
With no label and a hand-made branch, **it fails closed** — it will not guess, and that
is deliberate: a change with no declared boundary has no boundary.

On the pull-request page the verdict is on the run's summary, not only in the log, and
each blocked file is annotated on the Files tab:

```
### Lane check — `feat-02`

✅ **Passed.** All 2 changed files stay inside lane `feat-02`.
```

---

## 6. The daily loop: which command do I run?

| You want to… | Run |
| :--- | :--- |
| Give a ticket to a new agent | `lanekeeper spawn --ticket 7` |
| See every agent, lane and port | `lanekeeper status` |
| Open an agent's worktree in your editor | `lanekeeper open agent-002` |
| See what one agent changed, in lane / out of lane | `lanekeeper diff agent-002` |
| Check one agent fully before its PR | `lanekeeper validate agent-002` |
| Check any branch or PR against a lane | `lanekeeper check --lane feat-02 --base main` |
| Put the gate on every PR, once per repo | `lanekeeper install-gate` |
| Route reviews by lane in GitHub | `lanekeeper codeowners --owner @you` |
| Finish with an agent | `lanekeeper cleanup agent-002` |
| Check nothing is stale or broken | `lanekeeper doctor` |
| Remove lanekeeper from the repository | `lanekeeper uninit` |

Add `--repo <path>` (or `-C <path>`, as in git) to any of them to run against a
repository that is not your current directory.

Two of these are worth seeing before you need them:

```bash
lanekeeper diff agent-001
```

```
📝 DIFF SUMMARY FOR worker-1 (agent-001)
Branch: parallel/agent-001/2-feat-02-automated-semantic-clustering
Total Modified Files: 2

  ✓ [LANE OK]    src/domain/contracts.ts
  ✓ [LANE OK]    src/services/clusterService.ts
```

```bash
lanekeeper validate agent-001
```

```
🛡️ VALIDATION REPORT: worker-1 (agent-001)
Lane: feat-02

  [Lane Compliance]
    ✓ All 2 changed files are within allowed lane paths.

  [Capability Gates] seat JR1 — evaluated: database_migrations, security_review
    ✓ No gated path was touched by a capability this seat lacks.

==================================================
✅ VALIDATION PASSED: PR is safe to submit and merge.
```

---

## 7. When the gate says no

There are exactly five refusals. Each one names the file and says which kind it is,
because the right response is different every time.

**1. Outside the lane** — the ordinary one:

```
🛡️  LANE CHECK — lane 'feat-02', main...HEAD

  ✗ src/App.tsx: outside lane 'feat-02'.

❌ CHECK FAILED: this change leaves its lane.
```

```
  ✗ tests/unit/contracts.test.ts: outside lane 'feat-02'.
      If this file belongs in this lane: lanekeeper allow --lane feat-02 tests/unit/contracts.test.ts
```

The agent edited a file its ticket never mentioned. Decide which is true:

- *The agent overreached* → revert that file. This is the case the tool exists for.
- *The ticket was incomplete* → the one decision is *yes, that file belongs to this
  lane*, and the message offers the command that records it:

  ```bash
  lanekeeper allow --lane feat-02 tests/unit/contracts.test.ts
  ```

  ```
  ✅ tests/unit/contracts.test.ts is now allowed in lane 'feat-02'.
     .lanekeeper/config.yaml changed; commit it (it is the policy, so on its own, labelled 'lane: policy') for the gate in CI to read it.
  ```

  Inside an agent's worktree the `--lane` defaults to that worktree's own, and the
  policy in your main checkout is what changes. It refuses a path another lane already
  claims (naming it), the policy files, and shared zones — those exist so a person
  decides deliberately. It never widens a lane on its own.

**A tracked build artifact** — `tsconfig.tsbuildinfo`, coverage output, a lockfile an
unrelated install rewrote — trips every lane on every check until somebody untracks it.
The honest fix is to untrack it. Until then, name it once in the policy, and the gate
leaves it out in every lane and says so:

```yaml
generated:
  - '*.tsbuildinfo'
```

The list lives in `config.yaml`, which no lane may edit, so an agent cannot exempt a
file from inside its own pull request. The default is empty: nothing is ignored unless
you say so.

**2. Denied by the lane itself** — the lane lists a `deny` pattern that matches:

```
  ✗ src/domain/contracts.ts: denied to lane 'src-components' (matched 'src/domain/**').
```

Someone wrote that carve-out on purpose. Treat it as a smaller version of case 1: the
change belongs somewhere else, or the policy needs a deliberate edit.

**3. Shared code** — the file belongs to a lane declared `shared: true`, owned by
nobody on purpose:

> *shared code, in the 'shared-ui' zone that belongs to no lane on purpose. A change
> here affects every lane, so it is raised and decided, not made inside this one.*

Raise it with whoever owns the policy. Do not widen the lane to make it go away.

**4. The policy itself** — the change touches `.lanekeeper/config.yaml` or a seat card:

> *this file defines the lanes. A change to it is made by a person under the 'policy'
> lane, on its own.*

Make that change on your main checkout, in its own PR labelled `lane: policy`.

**5. Nothing was checked** — the gate could not read the change at all, usually a base
branch missing from a shallow CI checkout. **This fails too.** A gate that cannot see
is not a gate that passes, and an empty change list must never read as "all clear".

---

## 8. Tickets that name no files

Some tickets are one sentence. Lanekeeper refuses to invent a boundary for them:

```
❌ Ticket #9 ('Make the header sticky') names no files, so there is no boundary to
give an agent. Say which files it may touch with --allow 'src/checkout/**'
(repeatable), or let Claude Code propose them with --propose.
```

Two ways forward:

```bash
lanekeeper spawn --ticket 9 --allow 'src/components/layout/**'
```

```
🎫 Ticket #9: Make the header sticky
   Lane 'issue-9', bounded by --allow:
     src/components/layout/**
   Written into the policy so the pull-request gate checks the same boundary.
```

Or `--propose`, which asks Claude Code (on your own login, headless) what the ticket
probably touches, **prints the answer, and uses it only if you say yes**:

```
🤖 Claude Code proposes this boundary for #9 (Make the header sticky):
     src/components/layout/Header.tsx
   Use it? The agent will be held to exactly these files. [y/N]:
```

Answer `y` and it becomes the lane. Answer anything else — or run without a terminal
attached, as in a script — and it is **not used**: you are shown the `--allow` line to
hand over yourself. A proposed path never reaches the gate without your confirmation,
and `--yes` is how you give that confirmation up front.

---

## 9. No GitHub issues, or no `gh`?

`--ticket` reads your tracker. If you do not have one, or your work is written down
somewhere else, declare the lanes yourself once and spawn into them by name.

```bash
lanekeeper init --name "My App"
```

```
✨ Initialized lanekeeper for 'My App'
📁 Configuration written to …/repo/.lanekeeper/config.yaml
🧭 Detected 6 lanes from the repository layout: backend, docs, frontend, platform, src-components, src-hooks
   These are technology layers, a starting point only. 'lanekeeper start'
   divides by feature from your tickets and writes the same file.
   Coverage: 100% of 42 tracked files fall inside a lane.
```

**Read the line it prints about what it wrote.** `init` reads feature slices out of
your directory tree when it can find at least two — a feature top to bottom, which is
what you want. When it cannot, as on the project above, it falls back to technology
layers and says so, and **a layer split is the thing this tool argues against**: one
ordinary ticket touches a service, a schema, a route, a page and a test, so under
`backend`/`frontend` lanes it is one ticket against four lanes and four escalations.

So treat what `init` wrote as a draft. Open `.lanekeeper/config.yaml` and rewrite the
`lanes:` section as features:

```yaml
lanes:
  - name: checkout
    allow:
      - src/services/checkout/**
      - src/components/checkout/**
      - tests/checkout/**
  - name: search
    allow:
      - src/services/search/**
      - src/components/search/**
```

Then spawn by lane name instead of by ticket:

```bash
lanekeeper spawn --lane checkout --task "Cart total ignores expired coupons"
```

```
🚀 Agent 'worker-1' (agent-001) successfully spawned!
  • Worktree: …/repo/.lanekeeper/worktrees/agent-001
  • Branch:   parallel/agent-001/cart-total-ignores-expired-coupons
  • Lane:     checkout
  • Ports:    backend: 8001, frontend: 3001
  • Seat:     JR1
```

Everything after this point — check, the gate, cleanup — is identical. The lane file is
the contract; where it came from does not matter.

---

## 10. Two agents at once — and the warning you must not ignore

Spawn a second ticket exactly as you did the first:

```bash
lanekeeper spawn --ticket 3
```

```
⚠️  Another lane could touch the same files. Both lanes allow them, so both
    agents' changes pass their own checks — and meet at merge. That is the
    collision this tool exists to prevent, and the gate will not catch it:
      'feat-02' claims src/domain/contracts.ts, this ticket claims src/domain/contracts.ts

    The designed answer is a shared zone: 'shared: true' on a lane nobody is
    spawned into, checked before either lane's own list, so a change there is
    escalated rather than passed twice. In .lanekeeper/config.yaml:
      - name: shared
        shared: true
        allow:
        - src/domain/contracts.ts

    Nothing has been written yet.
   Proceed anyway [p], write the shared zone and proceed [s], or stop [n]? [p/s/N]:
```

**Read that.** It is printed *before* the lane goes into the policy and before a
worktree exists. Both tickets legitimately need `src/domain/contracts.ts`, and the gate
will pass both agents editing it, because it *is* inside both boundaries — the warning
says so, because everything printed after it is green. Lanekeeper asks; it does not
decide for you:

- **`s`** writes the shared zone shown and proceeds. From then on a change to that file
  from *either* lane is escalated, not passed. Choose this when the file genuinely
  belongs to everyone and will keep coming up.
- **`p`** proceeds with the overlap as it is — sequence the two agents yourself, or give
  the file to one lane and take it out of the other in `config.yaml`.
- **`n`** stops. Nothing was written; edit the tickets and run again.

Without a terminal — a script, CI — it proceeds with the warning printed, and says
`--accept-overlap` is how to say the overlap is deliberate.

**One lane, one agent.** If you try to put a second agent in a lane that already has a
live one, lanekeeper refuses and names the occupant:

```
❌ Lane 'feat-02' already belongs to agent-001 (worker-1). Two agents in one lane can
edit the same files, and the gate passes both — which is the collision this tool
exists to prevent.
```

That refusal is the tool being useful, not being in your way: inside one lane the gate
cannot tell two agents apart, because both are inside the boundary. Finish or clean up
the first agent, or give this work its own lane.

```bash
lanekeeper status
```

```
📋 LANEKEEPER — REPO

Agent ID     Name           Seat   Lane         Status     Ports            Task
----------------------------------------------------------------------------------
agent-001    worker-1       JR1    feat-02      RUNNING    8001/3001        #2 [FEAT-02]…
agent-002    worker-2       JR1    feat-03      RUNNING    8002/3002        #3 [FEAT-03]…
```

---

## 11. Making GitHub enforce it

Two commands, once per repository.

**The gate on every pull request:**

```bash
lanekeeper install-gate
```

```
📝 Wrote .github/workflows/lanekeeper-gate.yml
   It runs on every pull request and needs exactly one 'lane: <name>' label on the change.
```

Commit that file. From then on every PR runs the same check you ran by hand, and a PR
without exactly one `lane:` label fails closed.

**Reviews routed by lane** (optional, and it is not a substitute for the gate):

```bash
lanekeeper codeowners --owner @you
```

```
✅ Wrote .github/CODEOWNERS
   feat-02: 6 pattern(s) → @kish21
   feat-03: 6 pattern(s) → @kish21
   policy: 3 pattern(s) → @kish21
```

Commit it, then turn on **Require review from Code Owners** in your branch protection
settings. GitHub will then require the right person's approval per path.

The difference, because it matters: **CODEOWNERS asks who must approve a file, after
the work is done, and only a human can act on it. The gate asks whether the branch
should have touched the file at all, before the work starts, and the agent itself can
read the answer.** Have both; neither replaces the other.

---

## 12. Finishing with an agent

```bash
lanekeeper cleanup agent-002
```

```
🧹 Successfully cleaned up agent 'worker-2' (agent-002).
   Released ports: 8002, 3002
   Kept branch parallel/agent-002/3-feat-03-…: not merged into main. Its commits are pushed to origin/parallel/agent-002/3-feat-03-….
   If #3 is finished, you can mark lane 'feat-03' retired — 'retired: true' under it in .lanekeeper/config.yaml. A suggestion, and the edit is yours: the collision report and CODEOWNERS then skip it; the gate does not change.
```

The worktree goes, the ports go back in the pool, and the branch is deleted **only
when every commit on it is already on the base branch** — asked of git directly, never
inferred from `git branch -d`, which says yes to a pushed branch whatever `main` holds.
A merged branch reads `Deleted branch … (merged into main)`. An unmerged one is kept,
and the message says where its commits are, because the two cases carry different
risk:

```
   Kept branch parallel/agent-003/2-feat-02-…: not merged into main, and not pushed
   anywhere. Delete it yourself with 'git branch -D' when you are sure.
```

Lanekeeper never deletes unmerged work. The lane stays in `config.yaml` — it is your
policy, not agent state — and the next agent can be spawned into it.

---

## 13. Removing lanekeeper completely

You can undo all of this at any time. It shows you the plan and asks before touching
anything.

```bash
lanekeeper uninit
```

```
This will remove:
  - .lanekeeper/ (configuration, seat cards, state, logs)
  - .github/workflows/lanekeeper-gate.yml
  - lanekeeper's managed block in .gitignore
  - lanekeeper's managed block in .github/CODEOWNERS (anything you wrote by hand around it stays)

Some of those files are committed, so removing them leaves a deletion
in 'git status' for you to commit:
      .lanekeeper/capabilities/JR1.json
      .lanekeeper/config.yaml
      …

Remove all of that? [y/N]: y

   Removed .lanekeeper/.
   Removed .github/workflows/lanekeeper-gate.yml.
   Removed lanekeeper's block from .github/CODEOWNERS.
   Removed lanekeeper's block from .gitignore.

✅ Lanekeeper is out of this repository.
   Committed files were removed, so commit the deletion when you are ready.
```

An agent branch not merged into the base branch is **kept even with `--force`**,
pushed or not, and the plan says so per branch. `--force` answers "are you sure"; it
does not decide that your commits do not matter.

---

## 14. Troubleshooting — every message you are likely to hit

| What you see | What it means | What to do |
| :--- | :--- | :--- |
| `lanekeeper: command not found` / `not recognized as the name of a cmdlet` | Installed, but not on `PATH`. Common on Microsoft Store Python. | `python -m lanekeeper.cli …`, or add the Scripts folder to `PATH` — see §4. |
| `No lanekeeper configuration found` | Nothing set up here yet. Not a fault — it is telling you the first command. | With a ticket tracker: `lanekeeper spawn --ticket <number>`, which writes the configuration for you. Without one: §9, which starts from `lanekeeper init` and tells you what to check in what it wrote. |
| `Must run inside a valid Git repository root` | You are in a subdirectory, or not in a repository. | `cd` to the root, or use `lanekeeper --repo <path>`. |
| `Ticket #N names no files` | The ticket has no file list, so there is no boundary. | `--allow '<glob>'` (repeatable), or `--propose`. See §8. |
| `Lane 'x' already belongs to agent-001` | One lane, one agent — the collision the tool exists to prevent. | `lanekeeper cleanup agent-001` first, or spawn into a different lane. `--force` overrides it deliberately. |
| `Lane 'x' is shared code: it belongs to no agent on purpose` | You tried to put an agent in a `shared: true` lane. | Spawn into the feature lane whose work needs it. Changes to shared code are made by a person. |
| `This checkout has no policy of its own` | The worktree predates your policy commit. Harmless. | `git merge main` inside the worktree, or ignore it — it is gone for later agents. |
| `Could not read the change, so nothing was checked` | The gate could not diff against the base branch — usually a shallow checkout, or a `--base` that does not exist here. | The workflow `install-gate` writes already sets `fetch-depth: 0`; if you wrote your own, set it too, and check the base branch name. A gate that cannot see must not pass. |
| `Seat 'JR1' is not permitted in lane 'x'` | A seat card was written before that lane existed. | Lanekeeper reconciles a lane no card has heard of and says so. If another card names it, that is a real restriction: change the card or use a different seat. |
| `The editor command 'code' is not on PATH` | `lanekeeper open` could not find your editor. Nothing is broken; the worktree exists. | Set `editor.command` in `.lanekeeper/config.yaml` to your editor's command (`cursor`, `subl`, `idea`), or open the printed path yourself. |
| The worktree folder appears in my editor's sidebar | Expected. It is the agents' checkouts, ignored by git. | Leave it, or set `worktree_dir: ../lk-worktrees` in `config.yaml` to keep it outside the project. |
| `lanekeeper doctor` reports a problem | Something is stale — a leftover port, an orphaned worktree. | `lanekeeper repair` when doctor says it is repairable; doctor tells you when it is not and why. |
| `Branch '…' already exists on origin at …` | `spawn` looked at the remote first: an earlier session pushed that branch, often as an open pull request's head. Nothing was created. | `--remote-branch continue` to carry on from it, `rename` to start fresh under the name it proposes, `ignore` to use the name knowingly. Your call; it picks none. |
| `Could not ask origin whether '…' already exists there` | The remote could not be reached. A note, not an error. | Nothing; the spawn went ahead. Check the branch name against the remote yourself before pushing. |
| `This worktree's .lane says 'x', but the check was asked about 'y'` | You ran `check --lane y` inside agent x's worktree. The verdict is right about the question asked. | Re-run with the lane the worktree names, or from the checkout you meant. |
| `The label says lane 'x' but the branch name says 'y'` | A mislabelled pull request — the one case the gate can catch. | Fix the label (it wins) or the branch; the check does not run against either until they agree. |
| `tsconfig.tsbuildinfo: outside lane …` (or any build artifact) | A tracked file a build rewrites trips every lane. | Untrack it, or list it under `generated:` in `config.yaml`. See §7. |
| `Lane 'x' is marked retired` | Somebody put `retired: true` on that lane. | Remove the line to reopen the lane, or `--force` to spawn into it as it is. |
| `'spwan' is not a lanekeeper command. The most similar command is 'spawn'.` | A typo. | Type the one it names. |

Sanity check at any time:

```bash
lanekeeper doctor
```

```
🩺 LANEKEEPER DOCTOR

  ✓ Git repository: Valid Git repository detected.
  ✓ Configuration: Valid config (Project: repo, Max agents: 4).
  ✓ Worktrees: All 0 active agent worktrees are intact.
  ✓ Port allocations: 0 ports allocated cleanly.
  ✓ Capability cards: 4 capability card(s), 2 gate(s) consistent.

✅ Environment is clean and ready for parallel execution.
```

---

## 15. Honest limits

Things this tool does not do, and things not yet proven, so you are not surprised:

- **Two agents in one lane cannot be told apart.** Both are inside the boundary, so
  both pass. `spawn` refuses the second one; if you use `--force`, you are on your own.
- **A lane is only as good as the ticket.** A ticket that names the wrong files gives
  an agent the wrong boundary, correctly enforced.
- **Reading is unrestricted.** Only changes are checked.
- **The remote check is `git ls-remote`**, nothing more: it sees a branch that exists
  on `origin`, and names its pull request only when `gh` can answer. It never sees a
  branch somebody has not pushed.
- **`lanekeeper board`** (the GitHub project board integration) has never been run
  against a live project board.
- **`lanekeeper codeowners`** has never been observed routing a real pull request with
  *Require review from Code Owners* turned on.

Both unverified items are tracked in the repository, and neither affects the gate.

---

## 16. Where to go next

- The **[README](../README.md)** — the full reference: lane file schema, capability
  gates, ports, `.env` generation, agent lifecycle, recovery.
- **[docs/codeowners.md](codeowners.md)** — why the generated CODEOWNERS is ordered the
  way it is, and what it cannot express.
- **[docs/start-step1-intake.md](start-step1-intake.md)** and
  **[docs/start-step2-divide.md](start-step2-divide.md)** — the guided path
  (`lanekeeper start`), for dividing a whole backlog at once rather than one ticket at
  a time.
- **[product-playbook](https://github.com/kish21/product-playbook)** — for writing the
  tickets in the first place.

Found something this page did not answer? That is a documentation bug —
[open an issue](https://github.com/kish21/parallel-agents/issues/new).
