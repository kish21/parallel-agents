# Lanekeeper ⚡

[![Version](https://img.shields.io/badge/version-v0.7.0-blue.svg)](https://github.com/kish21/parallel-agents/blob/main/CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/kish21/parallel-agents/blob/main/LICENSE)

**Run multiple AI coding agents safely in the same repository.**

Lanekeeper gives each coding agent its own Git worktree, branch, ports, environment, and code boundaries, so agents can work at the same time without accidentally interfering with each other.

```
                    Your Repository
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
          Agent 1      Agent 2      Agent 3
          Backend      Frontend     Tests
             │            │            │
          Worktree     Worktree     Worktree
          Branch       Branch       Branch
          Port 8001    Port 8002    Port 8003
             │            │            │
             └────────────┼────────────┘
                          ▼
                      Validate
                          │
                          ▼
                         PRs
```

---

## Why Lanekeeper?

AI coding agents are powerful, but running several agents in the same repository creates real operational problems:

* **File Overwrites**: One agent can modify files another agent is actively working on.
* **Port Clashes**: Two agents can accidentally claim the same development port.
* **Cross-Talk**: Frontends can connect to another agent's uncommitted backend code.
* **Migration Conflicts**: Shared database migrations can clash or create duplicate counters.
* **Out-of-Scope Changes**: An agent can modify central configs, auth, or infrastructure outside its assigned task.
* **Resource Leaks**: Failed agents can leave behind orphaned processes, blocked ports, or stale git state.

Lanekeeper adds a mechanical coordination and safety layer around your coding agents to prevent these problems.

---

## The Basic Idea

There are four fundamental concepts:

### 1. Agent
An agent is an isolated worker session assigned to a specific task.
```
agent-001 → "Implement user authentication"
```

### 2. Worktree
Each agent gets its own physical Git working directory.
```
Agent 1 → .lanekeeper/worktrees/agent-001
Agent 2 → .lanekeeper/worktrees/agent-002
Agent 3 → .lanekeeper/worktrees/agent-003
```
Agents never edit the same physical files simultaneously.

### 3. Lane
A lane defines which part of the codebase an agent is permitted to touch. A lane is a
feature, top to bottom — not a tech layer.
```yaml
lane: checkout

allow:
  - src/api/checkout/**
  - src/services/payments/**
  - src/frontend/checkout/**
  - tests/checkout/**

deny:
  - src/api/checkout/legacy/**
```
If the backend agent modifies `src/api/users.py`, that is allowed. If it touches `src/frontend/App.tsx`, validation reports a violation.

### 4. Resources
Each agent receives its own dedicated runtime resources:
```
Agent 1 → backend port 8001, frontend port 3001
Agent 2 → backend port 8002, frontend port 3002
Agent 3 → backend port 8003, frontend port 3003
```
This prevents agents from talking to the wrong development server.

---

## 🚀 Quick Start

### 1. Install

```bash
pip install lanekeeper
```

This installs the `lanekeeper` command. Check which build you have with:

```bash
lanekeeper --version
```

From a clone:

```bash
pip install -e .
```

### 2. Start here

`lanekeeper start` is the guided way in. Before it sets anything up it asks the question
everything else depends on: **is the work written down, and does it cover what this
product is meant to do?** Every later step — how the work divides, who owns what, what
the merge gate enforces — is derived from your issues, so dividing a backlog that is
missing half the product produces a confident-looking split of nothing.

```
$ lanekeeper start

🛑 There is no written-down work in this project yet, so there is nothing
   to share out between agents.

   Run:  /vision  then  /scope  then  /plan

   I have changed nothing in this project.
```

That is [product-playbook](https://github.com/kish21/product-playbook), the companion
tool that works out what you are building and turns it into tickets. Lanekeeper divides
work; it does not invent it.

When there *is* work written down, `start` compares it against the product description —
`PRODUCT.md` first, a README second — and reports which features have nothing written
against them. When there is nothing to compare against, it says exactly that, rather than
dressing a guess up as a verdict:

```
📋 I found 12 pieces of work written down.

   I count 12 pieces of work and I cannot tell whether that is
   all of them, because this project has nothing written down that says
   what it is meant to do. I am not going to guess.
```

Answer it with `--take-as-is` if what is there is the whole job. Fix your issues and run
`start` again and it carries on from where it stopped rather than starting over. Read the
same check on its own with `lanekeeper intake`.

Where your work is read from is configuration, not an assumption. GitHub Issues is the
default; the section lives in `config.yaml` under `intake`, along with which documents
describe your product and every threshold the check judges by.

When there is nothing written down and you are at a terminal, `start` does not stop at
the advice: it opens Claude Code in the project with `/vision` as the opening prompt,
waits for you to finish `/scope` and `/plan` there, and looks at the tickets again when
you exit. `--no-handoff` keeps it to printing the steps.

After the pre-flight, `start` proposes how the work divides and writes the proposal as a
draft for you to edit; `lanekeeper divide --confirm` re-checks what you wrote and makes
it the policy every agent is held to. `init` below is the direct route if you already
know how you want the work divided.

**The board.** `lanekeeper board` creates the GitHub project board with Lane, Owner and
Seat fields, `lane:` labels and milestones, all generated from `config.yaml` so the board
carries the same lane names the gate enforces. It needs `gh` with the `project` scope.
`board --show` reads every card back. With `board.read: true` in the configuration, a
card's Lane outranks the ticket form when the work is divided, and
`lanekeeper spawn --ticket 12` takes the agent's lane and seat from the card.

**The advisor.** Set `divide.advisor: claude-code` and, for a ticket that names no files
and that nothing in the code matches, lanekeeper asks Claude Code headless (`claude -p`,
on your own login, no API key) which files it probably touches. The answer is filtered to
paths that exist and lands in the draft switched off for you to confirm. The gate never
consults a model.

### 3. Initialize the Repository

`init` reads your repository and generates lanes that match its actual structure, then
reports how much of the tree they cover:

```
$ lanekeeper init
🧭 Detected 3 lanes from the repository layout: backend, frontend, platform
   Coverage: 100% of 412 tracked files fall inside a lane.
```

If coverage is low it says so, rather than letting you discover it when validation reports
legitimate work as out-of-lane. Use `--generic` to keep the starter lanes instead.

From your project root:
```bash
lanekeeper init
```
This creates the `.lanekeeper/` configuration and state directories.

Lanekeeper keeps its own files in one directory. To put them somewhere else,
set `LANEKEEPER_HOME` to a directory name relative to the repository root
before running any command:

```bash
export LANEKEEPER_HOME=.agents
```

Everything lanekeeper writes moves with it — config, state, logs, capability
cards, the default worktree location, and the rules `init` adds to
`.gitignore`. Absolute paths and paths containing `..` are rejected, so the
directory always stays inside the repository.

### 4. Create an Agent
```bash
lanekeeper spawn \
  --name backend-1 \
  --lane backend \
  --task "Implement user authentication"
```
Lanekeeper provisions the isolated worktree, branch, `.env`, and dedicated ports automatically (and optionally starts an agent execution process when `--command` is supplied).

### 5. Create Another Agent
```bash
lanekeeper spawn \
  --name frontend-1 \
  --lane frontend \
  --task "Build the login interface"
```
Now both agents can work simultaneously without collision.

### 6. Check Agents
```bash
$ lanekeeper status

📋 LANEKEEPER — MY-PROJECT

Agent ID     Name           Seat   Lane         Status     Ports            Task
----------------------------------------------------------------------------------------------------
agent-001    backend-1      SR1    backend      RUNNING    8001/3001        Implement user authentication
agent-002    frontend-1     JR1    frontend     RUNNING    8002/3002        Build the login interface
```

### 7. Validate an Agent's Work
```bash
$ lanekeeper validate agent-001

🛡️ VALIDATION REPORT: backend-1 (agent-001)
Lane: backend

  [Lane Compliance]
    ✓ All 4 changed files are within allowed lane paths.

==================================================
✅ VALIDATION PASSED: PR is safe to submit and merge.
```

### 8. Inspect Changed Files
```bash
lanekeeper diff agent-001
```

### 9. Open the Agent's Desk
```bash
lanekeeper open agent-001          # or: lanekeeper spawn ... --open
```
Opens the worktree in your editor — `code` by default, set under `editor:` in
`config.yaml`. The worktree's `.lane` file names the lane, the task, and the exact
`ALLOW` and `DENY` patterns, so an agent told "read `.lane`" knows its boundary.

### 10. Gate Every Pull Request
```bash
lanekeeper check --write-workflow  # writes .github/workflows/lanekeeper-gate.yml
```
`validate` is what you run by hand. `check` is the same lane engine run by CI on every
pull request, with **no agent state needed**: it reads the lane from a `lane: <name>`
label on the pull request and fails if any changed file is outside it. No label, no
pass. Run it yourself on a branch with:

```bash
lanekeeper check --lane checkout --base origin/main
```

### 11. Stop an Agent
```bash
lanekeeper stop agent-001
```

### 12. Clean Up Safely
```bash
lanekeeper cleanup agent-001
```

---

## How It Works

```
WITHOUT LANEKEEPER:                           WITH LANEKEEPER:

Agent A ─────┐                                      Git Repository
             │                                            │
Agent B ─────┼── Same working directory     ┌─────────────┼─────────────┐
             │                              │             │             │
Agent C ─────┘                              ▼             ▼             ▼
                                         Agent A       Agent B       Agent C
             ↓                              │             │             │
      Conflicts & Leaks                Worktree A    Worktree B    Worktree C
                                       Branch A      Branch B      Branch C
                                       Port 8001     Port 8002     Port 8003
                                            │             │             │
                                            ▼             ▼             ▼
                                         Backend       Frontend       Tests
```

The core difference is **physical isolation**. Agents are not merely prompted to avoid collisions; the tooling physically isolates their files, branches, and ports, and mechanically validates their boundaries.

---

## Lanes

A lane is a **feature slice, not a tech layer.**

This is the single decision that makes or breaks a lane file. The tempting split is
`backend` / `frontend` / `infra`, because it matches the folder tree. It is the wrong
one: an ordinary ticket — *"an expired coupon still shows a struck-through price"* —
touches a service, a schema, an API route, a React component and four tests. Under a layer
split that is one ticket against four lanes, so either four agents coordinate to ship it
or one agent escalates four times. Under a feature split it is one agent, one lane, one PR.

```yaml
lanes:
  checkout:                                 # a feature, top to bottom
    allow:
      - backend/app/domains/checkout/**
      - backend/app/api/checkout.py
      - backend/app/schemas/order.py
      - frontend/src/components/checkout/**
      - frontend/src/pages/CheckoutPage.tsx
      - backend/tests/test_checkout.py
```

```
checkout agent        search agent          catalog agent
      ↓                     ↓                      ↓
 service · api         service · api         service · api
 schema · page         schema · page         schema · page
 provider · tests      provider · tests      provider · tests
```

The goal is not to isolate every single file — it is that **one ticket lands in one lane.**

---

## The lane file

`lanes.yaml` is the contract: a checked-in, hand-writable file that lanekeeper loads as the
authority on who owns what. `lanekeeper init` can *propose* one by reading your folder tree,
but it proposes for confirmation — the file, not the detection, is the source of truth.
Hand-editing it is the expected act, and `check` and `spawn` honour the edit with no other
action.

A complete worked example — a mid-size e-commerce SaaS carved into 17 lanes and 8 shared
zones, with every judgement call annotated — is in
[`examples/feature-lanes.yaml`](examples/feature-lanes.yaml). The project is invented; the
awkward parts of the split are not.

### The whole schema

```yaml
version: 1

unowned: new-modules      # a path in no lane and no shared zone:
                          #   error | allow | <lane-name>

defaults:
  harness: claude-code    # inherited by every lane that does not override it

lanes:
  checkout:
    description: Cart to confirmed order — addresses, shipping, the order write.
    owner: senior         # a ROLE this lane needs, not a seat number
    harness: claude-code  # optional; overrides defaults
    allow:
      - backend/app/domains/checkout/**
      - frontend/src/components/checkout/**
    deny:                 # carve-outs inside your own allow
      - backend/app/domains/checkout/legacy/**

  new-modules:
    description: The greenfield lane.
    claims: unowned       # at most one lane; holds every unclaimed path

shared:
  request-spine:
    description: Where every feature plugs in.
    steward: platform       # the lane that may edit without escalating,
                            # and the lane everyone else escalates TO
    mode: escalate          # escalate | append_only
    paths:
      - backend/app/main.py
      - backend/app/config/platform.yaml

  migrations:
    description: Adding a file is free; editing an applied one is not.
    mode: append_only       # any lane may ADD a file here; changing an
    paths:                  # existing one is an escalation
      - db/migrations/**
```

### The four rules that decide who owns a path

1. **A shared zone always wins.** However specific a lane's `allow`, a path inside a shared
   zone belongs to the zone. That is what makes `shared` mean anything.
2. **Between lanes, specificity wins** — the pattern with the most wildcard-free path
   segments, ties broken by pattern length. **Declaration order is irrelevant**, because the
   file is hand-edited and a split that silently depends on line order is not reviewable. An
   exact tie is a load error naming both lanes; it means you have not decided yet.
3. **`deny` beats `allow` within a lane**, and only carves out of your own claim.
4. **Anything left over goes where `unowned` says.** `error` if every file must have a home,
   `allow` if you are enforcing loosely, or a lane name if — as is usually true — the
   greenfield work has an owner too.

### `owner` is a role, not a seat

One lane, one owner at a time. But a real project has far more lanes than running agents —
a 17-lane split routinely runs on four seats — so **the file names the role a lane needs,
and `spawn` binds it to a seat.** A lane split is a design decision with a long half-life;
who is sitting in front of it this week is not, and the two do not belong in the same
field.

### `shared` needs a steward

The original design said a shared zone is owned by nobody and touching it needs escalation.
Half of that survives contact with a real repo. `backend/app/main.py` is genuinely shared —
every feature registers itself there — but if it is owned by nobody, then the platform lane,
whose whole job is that file, escalates to no one in order to do its own work.

So a zone may name a `steward`: the one lane that edits it directly, and the lane every
other lane escalates *to*. `steward` is optional — omit it for a zone that really is
everybody's, like the root `README.md`.

### `append_only`, for directories that grow

Some shared directories are touched by nearly every lane and still never collide, because
each lane only ever *adds* a timestamped file: database migrations, feature docs,
changelog fragments. Marking them `escalate` would put an escalation on routine work, and
leaving them out of `shared` would let one lane rewrite an applied migration. `append_only`
says the difference out loud: **adding a file is free, editing an existing one is an
escalation.**

### Shared zones are lists of paths, not folders

Prefer naming files. `frontend/src/store/**` looks like the obvious shared zone until you
notice `authStore.ts` sits in it and belongs squarely to the auth lane — and now auth
escalates to touch its own file. A zone that swallows a folder taxes its neighbours.

---

### Lane enforcement fails closed

Lane policy is only meaningful if it cannot be switched off by accident, so every lane
lookup is strict:

* `spawn --lane <name>` **rejects** a lane that is not declared in `config.yaml`, listing
  the valid lanes. Nothing is provisioned — no branch, no worktree, no port reservation.
* `validate` and `diff` **refuse** an agent whose lane is no longer declared (for example,
  the lane was renamed or removed after the agent was spawned). They report a failure
  rather than checking the agent against an empty policy.

There is deliberately no permissive fallback. An unrecognised lane is a configuration
error, never a lane that happens to allow every path. The loader keeps that promise too:

* A lane with **no `allow` patterns** is refused at load. `allow: []` used to be read as
  "allow everything"; it is now an error that names the lane.
* A pattern written as a directory — `secrets/` — means everything under it, in lanes
  and capability gates alike. It used to match nothing in a lane.
* **A rename is two changes.** Moving a file out of another lane, or out of a denied
  directory, reports the source path as a change to that path. It used to report only
  the destination.
* **A diff that cannot be computed is a failed check**, never an empty one. If the base
  branch does not exist, `validate` and `check` say "nothing was checked" and fail.
* **The policy is not subject to the policy.** `.lanekeeper/config.yaml` and the seat
  cards under `.lanekeeper/capabilities/` are denied to every lane, however wide its
  `allow`. A change to them is made by a person, in its own pull request, checked under
  the reserved lane name `policy` — which may touch those files and nothing else.
* A state ledger that cannot be read stops every command with a message. It used to be
  read as empty, and the next write replaced it.

> **Commit `.lanekeeper/config.yaml`.** It is the policy every agent is validated
> against — the team's shared contract. `lanekeeper init` adds ignore rules that keep
> runtime state and worktrees out of git while leaving the config tracked. Without those
> rules an agent running `git add -A` would sweep every other agent's worktree into its own
> commit.


## Capability Gates

A lane answers **where** a seat may work. A capability card answers **what kind of work it
is competent to do there**.

Each seat has a card declaring its capabilities in three states:

| State | Meaning | Effect |
|---|---|---|
| `native` | The harness does this reliably. | Proceeds. |
| `author-required` | It can, but only by running a procedure written for it. | Proceeds **only** if a quality command declaring `satisfies: <capability>` passed. |
| `unavailable` | It cannot do this safely. | **Hard stop.** Non-zero exit; must escalate. |

`config.yaml` maps paths to the capability they require:

```yaml
capability_gates:
  security_review:
    paths: ["**/auth/**", "**/payments/**", "**/tenant/**", "secrets/**"]
  database_migrations:
    paths: ["database/migrations/**", "migrations/**"]
```

So a junior seat rated `security_review: unavailable` cannot get a green validation on an
auth file — **even when that file is inside its lane**:

```
  [Lane Compliance]
    ✓ All 1 changed files are within allowed lane paths.

  [Capability Gates] seat JR1 — evaluated: database_migrations, security_review
    ✗ src/backend/auth/login.py
        requires 'security_review' — seat is 'unavailable'
        seat 'JR1' cannot perform 'security_review'. This change must be escalated
        to a seat rated native for it.

❌ VALIDATION FAILED: Must resolve errors before merging.
```

This is the mechanical form of the rule in `01-working-agreement.md`: stop when the change
touches money, auth, tenant isolation, or a migration.

### It fails closed, in four ways

An unrecognised seat, a seat with no card, a capability the card does not rate, and a
green-but-untagged quality command are **all denials**. Absence is never permission.

### Generating the gate declaration

`lanekeeper declare <agent>` produces the PR template's mandatory Gate Declaration
from recorded state — the seat, its ratings, the gates triggered, and each quality command
with its real exit code — rather than asking an author to type it from memory.

> **What this does not do.** It does not verify that a `native` rating is *honest*. A
> rating is a claim by the seat's owner; the tool holds the claim in one place, refuses
> work the claim says the seat cannot do, and makes the declaration an artefact.
> Rating honesty stays a human review question.


## Ports

Parallel development servers need independent ports. Instead of hardcoding `8000`:

```
Agent 1 → Port 8001 / 3001
Agent 2 → Port 8002 / 3002
Agent 3 → Port 8003 / 3003
```

Allocations are deterministic, checked against the host OS socket state, injected into `.env`, and released upon cleanup.

### Service URLs

A port number on its own does not connect anything. Browser build tools expose only their
own prefixed variables to client code — Vite reads `VITE_*`, Next.js reads
`NEXT_PUBLIC_*` — so a frontend handed `API_PORT=8002` cannot see it, and falls back to
whatever server is compiled into its source. That is usually another agent's backend.

`lanekeeper init` therefore reads the dependencies your repository declares and writes
the matching URL variables into `.lanekeeper/config.yaml`:

```yaml
environment:
  host: 127.0.0.1
  url_templates:
    API_URL: http://${HOST}:${BACKEND_PORT}
    VITE_API_URL: http://${HOST}:${BACKEND_PORT}
    FRONTEND_URL: http://${HOST}:${FRONTEND_PORT}
```

Each agent's `.env` then resolves them against its own ports:

```bash
# .lanekeeper/worktrees/agent-002/.env
BACKEND_PORT='8002'
VITE_API_URL='http://127.0.0.1:8002'   # agent-002's own backend, never agent-001's
```

Add, remove, or rename templates to suit your stack; a template naming a port category
your project does not define is dropped rather than written half-expanded.

Lanekeeper does **not** install dependencies. A fresh worktree has no `node_modules` or
virtualenv, so run your usual install command in it before starting a dev server.

---

## Agent Lifecycle

Agents follow an explicit state machine:

```
CREATED ──► STARTING ──► RUNNING ──┬──► COMPLETED ──► REVIEW
                            │      │
                            │      └──► FAILED ──► REPAIR ──► RUNNING
                            ▼
                         STOPPED
```

Useful commands:
```bash
lanekeeper status
lanekeeper logs backend-1
lanekeeper stop backend-1
lanekeeper restart backend-1
lanekeeper repair backend-1
lanekeeper cleanup backend-1
```

---

## Mechanical Validation

Never rely on an AI agent's word that its work is complete. Lanekeeper independently validates:

```bash
$ lanekeeper validate backend-1

Validation: backend-1

Git
  ✓ Correct branch
  ✓ Correct worktree

Policy
  ✓ All changed files allowed in lane 'backend'

Quality
  ✓ Tests passed
  ✓ Lint passed
  ✓ Typecheck passed

Result: PASS
```

If an agent touches a forbidden file:
```
Validation: backend-1

Policy
  ✗ Forbidden file modified: src/frontend/App.tsx (Reason: denied)

Result: FAIL (Exit code 2)
```

---

## Recovery & Diagnostics

If an agent process crashes or an orphaned port is left behind:

```bash
$ lanekeeper doctor

🩺 LANEKEEPER DOCTOR

  ✓ Git repository: Valid Git repository detected.
  ✓ Configuration: Valid config (Project: demo, Max agents: 4).
  ✓ Worktrees: All 1 agent worktrees are intact.
  ✗ Port allocations: 2 port allocation issue(s) detected.
      ↳ Port 3001 still reserved by stopped agent 'agent-001'.
      ↳ Port 8001 still reserved by stopped agent 'agent-001'.
  ✓ Agent processes: All active agent process states are consistent.

⚠️ 1 problem(s) detected. Run 'lanekeeper repair' to fix.
```

`doctor` reports three classes of problem:

| Class | Meaning |
|---|---|
| **Orphaned** | A port is still reserved by an agent that has stopped, failed, completed, or no longer exists. If a process is *still listening* on it, it is reported as a leaked server. |
| **Conflict** | The port ledger and an agent's own recorded ports disagree — the dangerous case, because the ledger could hand the same port to a second agent. |
| **Stale process** | An agent is marked `RUNNING` but its PID is dead. |

Run repair to automatically clean up orphaned resources:
```bash
lanekeeper repair
```

---

## Database Isolation

Projects that interact with databases can configure an isolation strategy:

```yaml
database:
  strategy: per-agent
  name_template: "app_${AGENT_ID}"
```

Resulting databases:
```
agent-001 → app_agent_001
agent-002 → app_agent_002
agent-003 → app_agent_003
```

---

## Agent Providers & Adapters

Lanekeeper is provider-independent. It uses a pluggable `AgentAdapter` abstraction:

```
              Lanekeeper
                    │
              Agent Adapter
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
   CLI harness   IDE session   Custom adapter
```

The orchestration layer handles isolation, ports, and validation; the adapter handles
execution. No vendor is named anywhere in the tooling or the configuration schema: which
harness fills a seat is recorded in that seat's capability card (`vendor_harness`), so
swapping vendors edits one field and changes nothing else.

---

## 🛠️ CLI Reference

| Command | Purpose |
| :--- | :--- |
| **`lanekeeper start`** | Guided setup. Checks that the work is written down and covers the product before anything else runs. |
| **`lanekeeper intake`** | The same check on its own: is the work written down, and does it cover the features? |
| **`lanekeeper init`** | Initializes repository and creates configuration. The direct route if you already know your lanes. |
| **`lanekeeper doctor`** | Diagnoses repository, worktree, and port health. |
| **`lanekeeper spawn`** | Provisions an isolated worktree, branch, `.env`, and allocated ports. `--ticket` reads lane and seat from the board; `--open` opens the editor. |
| **`lanekeeper status`** | Shows active agents, lanes, and allocated ports (`--json` supported). |
| **`lanekeeper validate`** | Mechanically validates lane compliance and runs test suites. |
| **`lanekeeper check`** | The same lane check as a pull-request gate: a lane name or the PR's labels, a base branch, no agent state. `--write-workflow` installs it in GitHub Actions. |
| **`lanekeeper open`** | Opens an agent's worktree in the configured editor. |
| **`lanekeeper board`** | Creates the GitHub project board (Lane, Owner, Seat, labels, milestones) from the configuration; `--show` reads the cards back. |
| **`lanekeeper divide`** | Proposes how the work divides into a draft; `--confirm` re-checks your edits and writes the lanes into the policy. |
| **`lanekeeper diff`** | Displays changed files classified as `[LANE OK]` vs. `[OUT-OF-LANE]`. |
| **`lanekeeper inspect`** | Shows detailed agent metadata and environment variables. |
| **`lanekeeper logs`** | Tails structured execution logs for an agent session. |
| **`lanekeeper stop`** | Stops an active agent process. |
| **`lanekeeper restart`** | Restarts an agent in its worktree. |
| **`lanekeeper repair`** | Repairs stale states and releases orphaned ports. |
| **`lanekeeper declare`** | Generates the PR gate declaration from recorded state. |
| **`lanekeeper cleanup`** | Safely removes worktrees and releases port allocations. |

---

## 💡 Design Philosophy

1. **Isolation Over Instructions**: Do not merely instruct agents to avoid collisions; provide physically isolated environments.
2. **Mechanical Validation Over Trust**: Never assume an agent followed the rules; mechanically verify diffs against lane policies.
3. **Simple Over Clever**: Coordinate coding agents with clarity; do not build an autonomous swarm or bloated web UI.
4. **Developer in Control**: Agents propose changes; humans review and merge them.
5. **Safe Cleanup**: Never sacrifice uncommitted developer work for aggressive cleanup.

---

## 🚫 What Lanekeeper Is Not

* ❌ Not an autonomous AI software company.
* ❌ Not an AI project manager.
* ❌ Not a replacement for Git or CI/CD.
* ❌ Not tied to any single AI vendor or model.

It is a **lightweight coordination and safety layer** for parallel AI coding agents.

---

## 🧪 Automated Testing & Reliability Benchmarks

Lanekeeper includes a **tracked 36-test unit, integration, concurrency stress, and failure recovery suite** and an automated reproducibility benchmark runner.

### 1. Run the Full Test Suite
```bash
python -m unittest discover tests
```
```
....................................
----------------------------------------------------------------------
Ran 139 tests in 16.3s

OK
```

#### What Is Tested & Proven:
* **StateLock Integration (`test_state_lock.py`)**: Validates StateLock mutual exclusion under heavy contention (20 simultaneous threads) with zero state lost or overwritten.
* **Atomic Concurrency & Stress (`test_concurrency.py`, `test_e2e_concurrent.py`)**: Spawns up to 10 agents in parallel threads simultaneously across separate CPU workers to mechanically prove that re-entrant file locking (`StateLock`) assigns unique sequential IDs, dedicated Git worktrees, unique branches, and non-colliding ports atomically with zero lost state.
* **Failure Modes & Transactional Rollbacks (`test_failure_modes.py`)**: Validates clean port rollback on port exhaustion, clean rollback when worktree creation fails (simulated disk/git failure), dead process diagnosis and recovery in `repair`, and protection of uncommitted developer code during cleanup.
* **3-Agent Multi-Lane Workflow (`test_e2e_3agents.py`)**: Concurrently spawns Agent A (Backend), Agent B (Frontend), and Agent C (Service), verifies distinct physical worktrees, dedicated branches, and unique ports (`8001/3001`, `8002/3002`, `8003/3003`), validates in-lane edits (pass), proves deliberate cross-lane violations fail with exit code `2`, and cleanly reclaims all resources.
* **Port Audit & Conflict Detection (`test_ports.py`, `test_port_audit.py`, `test_port_conflicts.py`)**: Validates real OS socket probing (a bound socket is detected and skipped by the allocator), ledger/agent-state drift detection, leaked-server reporting on orphaned ports, and that a failed re-allocation never releases the agent's existing reservations.
* **Fail-Closed Lane Enforcement (`test_lane_fail_closed.py`)**: Proves that an undeclared lane — a typo at spawn, or a lane deleted from the config afterwards — is rejected outright rather than validating as safe, and that a rejected spawn leaves behind no branch, worktree, or port reservation.
* **Environment Injection (`test_env_injection.py`)**: Round-trips hostile task strings (quotes, newlines, `$VAR`, backticks, `$(...)`) through a real `/bin/sh` to prove generated `.env` and `.lane` files cannot be escaped or executed.
* **Capability Gates (`test_capability_gates.py`)**: Proves an `unavailable` capability hard-stops an in-lane file, `native` passes the same file, `author-required` passes only when its verified script exits 0, `forbidden_paths` overrides the lane allow, and four separate fail-closed paths (unknown seat, missing card, unrated capability, untagged command).
* **Glob Matching (`test_glob_matching.py`)**: Pins segment-aware `**` semantics, including that `**/auth/**` must not match `src/authentic/`, and that a recursive deny pattern actually denies.
* **Repository Hygiene (`test_init_gitignore.py`)**: Proves `git add -A` cannot stage agent worktrees or runtime state, while the shared lane policy stays tracked.
* **Diagnostics & Recovery (`test_doctor.py`, `test_cleanup.py`)**: Validates automatic detection of missing worktrees, orphaned port reclamation, and uncommitted developer code protection.

---

### 2. Run Reproducibility Benchmarks
```bash
python benchmarks/benchmark_parallel.py --cycles 5
```
```
======================================================================
📈 LANEKEEPER: BENCHMARK RESULTS & SYSTEM RELIABILITY METRICS
======================================================================
  • Total Cycles Executed:        5 / 5
  • Total Agents Spawned:         15
  • Total Execution Time:         7.02s
----------------------------------------------------------------------
  • Worktree Collision Rate:      0.0% (0 collisions)
  • Port Race Condition Rate:     0.0% (0 collisions)
  • Lane Violation Accuracy:      100.0% (5/5 caught)
  • Worktree Leaks Post-Cleanup:  0
======================================================================
✅ PASSED: 5 cycles / 15 agents with 0 observed worktree or port collisions, 5/5 injected lane violations detected, and no leaked resources.
======================================================================
```

Every number above is measured at run time. The benchmark exits non-zero on any collision,
leak, or undetected violation, so CI fails rather than printing a clean summary over a bad
run.

---

## 📚 Deep-Dive Documentation & Guides

| Document | Description |
| :--- | :--- |
| **[🎬 End-to-End Walkthrough](https://github.com/kish21/parallel-agents/blob/main/EXAMPLES.md)** | Step-by-step lifecycle of Ticket #102 from assignment to merge. |
| **[01. Working Agreement](https://github.com/kish21/parallel-agents/blob/main/01-working-agreement.md)** | Definition-of-Done, path boundary contracts, and merge discipline. |
| **[02. Conflict Management](https://github.com/kish21/parallel-agents/blob/main/02-conflict-management.md)** | Worktree deep-dive, port tables, and Disaster Recovery Runbook. |
| **[03. Orchestration](https://github.com/kish21/parallel-agents/blob/main/03-orchestration.md)** | Capability cards, scaling 2→4→6 seats, and ROI metrics. |
| **[04. Agent Setup](https://github.com/kish21/parallel-agents/blob/main/04-agent-setup.md)** | Prompts for Senior/Junior agents and token cost hygiene. |
| **[05. GitHub Mechanics](https://github.com/kish21/parallel-agents/blob/main/05-github-mechanics.md)** | Board custom fields, disjoint milestones, and single-account routing. |
| **[06. Free-Tier Operations](https://github.com/kish21/parallel-agents/blob/main/06-free-tier-ops.md)** | CI minute optimization, public vs private repo trade-offs, and verified mirrors. |

---

## 🤝 Community & Contributing

Contributions are welcome! See our community guidelines:
* **[Contributing Guide](https://github.com/kish21/parallel-agents/blob/main/CONTRIBUTING.md)**
* **[Security Policy](https://github.com/kish21/parallel-agents/blob/main/SECURITY.md)**
* **[Code of Conduct](https://github.com/kish21/parallel-agents/blob/main/CODE_OF_CONDUCT.md)**

---

## License
[MIT](https://github.com/kish21/parallel-agents/blob/main/LICENSE)
