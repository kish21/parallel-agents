# Lanekeeper ⚡

[![Version](https://img.shields.io/badge/version-v0.7.5-blue.svg)](https://github.com/kish21/parallel-agents/blob/main/CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/kish21/parallel-agents/blob/main/LICENSE)

**Run several AI coding agents on one repository without them colliding.**

Lanekeeper reads your tickets, divides the work into **lanes** — a feature, top to
bottom, never a technology layer — gives each agent its own worktree, branch and ports
inside one lane, and puts a **gate on every pull request** that fails any change which
leaves its lane. The gate is a set intersection over file patterns. No model is
consulted where the safety promise is made.

It is built to pair with [product-playbook](https://github.com/kish21/product-playbook),
which writes the tickets. Product-playbook writes the work down; lanekeeper divides it up.

---

## Five minutes, start to gate

Everything below is real output from running lanekeeper on
[a small React project](https://github.com/kish21/mini-issue-tracker) with three open
issues written by product-playbook.

### 1. Install

```bash
pip install lanekeeper
```

### 2. Let it read your tickets

```
$ lanekeeper start

✅ The work is written down: 3 pieces of work.

   I compared them against the plan in PRODUCT.md, and every thing that document says
   this product does has something written against it.

📋 Here is how I would share out 3 pieces of work — 2 groups, one for each agent.

   prompt  (#3, #1)
       2 pieces of work name the same part of the project (prompt) in the
       files they touch.
       Files it would cover: src/components/features/IssueCard.tsx, ... (and 9 more)

   feat-02  (#2)
       Nothing else in the list points at the same part of the project.
       Files it would cover: src/components/features/ClusterCard.tsx, ... (and 3 more)

     • Two of these would be working on the same files. That is the one thing
       here you cannot see by reading the list, so it is worth settling before
       anybody starts:
     • prompt and feat-02 both cover src/domain/contracts.ts.

   I have written all of the above to .lanekeeper/start/lanes.draft.yaml.
```

It reads GitHub Issues through `gh`. Each ticket's file list (the *Allowed File Paths*
field of the issue form, or product-playbook's *Target Modules* section) is the
boundary. Nothing is guessed: a ticket with no files is listed as unplaced, not invented.
If there are no tickets at all and you are at a terminal, `start` opens Claude Code on
product-playbook's `/vision` and picks up when you are done.

### 3. Confirm the split

Edit the draft if you disagree — join two entries, rename one, add a missing file. The
draft already contains the fix for the collision above, switched off:

```yaml
# shared:
#   common:
#     paths:
#       - src/domain/contracts.ts
```

Uncomment it, then:

```
$ lanekeeper divide --confirm

✅ Written down: 2 groups of work, each with its own set of files.

   The record is lanes.yaml. It is yours to edit from here.
   The same groups are now the 'lanes' in .lanekeeper/config.yaml, which is what
   'spawn', 'validate' and 'check' hold every agent to.
```

Commit `.lanekeeper/` and `lanes.yaml`. That is the policy.

### 4. Give an agent a desk

```
$ lanekeeper spawn --lane feat-02 --task "#2 clustering engine" --open

🚀 Agent 'worker-1' (agent-001) successfully spawned!
  • Worktree: .lanekeeper/worktrees/agent-001
  • Branch:   parallel/agent-001/2-clustering-engine
  • Lane:     feat-02
  • Ports:    backend: 8001, frontend: 3001
🪟 Opened agent-001 in the editor
```

`--open` launches your editor (`code` by default) on the worktree. The worktree's
`.lane` file tells the agent its lane, its task and the exact paths it may touch:

```
LANE='feat-02'
TASK='#2 clustering engine'
ALLOW='src/components/features/ClusterCard.tsx src/domain/contracts.ts src/prompts/clusteringPrompt.ts ...'
```

Point the agent at it: *"Read `.lane` before you start. Stay inside `ALLOW`."*

### 5. Put the gate on every pull request

```bash
lanekeeper check --write-workflow    # writes .github/workflows/lanekeeper-gate.yml
```

Commit it. From then on every PR needs exactly one `lane: <name>` label, and the gate
fails any file outside that lane. Here is the agent above straying into `src/App.tsx`:

```
$ lanekeeper check --lane feat-02 --base origin/main

🛡️  LANE CHECK — lane 'feat-02', origin/main...HEAD

  ✗ src/App.tsx: outside lane 'feat-02'.

❌ CHECK FAILED: this change leaves its lane.
```

Revert the stray file and the same command prints `✅ CHECK PASSED`. A rename out of
another lane, a deleted file that was not yours, an edit to the policy itself: all
caught. A PR that changes the policy files carries the reserved label `lane: policy`.

### Already have a backlog? One command per ticket

You do not need `start`, `divide` or a board. Hand a ticket to an agent and the ticket
is the boundary:

```
$ lanekeeper spawn --ticket 12 --open

🎫 Ticket #12: [FEAT-02] Cluster similar issues
   Lane 'feat-02', bounded by the ticket's own file list:
     src/components/features/ClusterCard.tsx
     src/domain/clustering/**
   Written into the policy so the pull-request gate checks the same boundary.

🚀 Agent 'worker-1' (agent-001) successfully spawned!
  • Worktree: .lanekeeper/worktrees/agent-001
  • Branch:   parallel/agent-001/12-feat-02-cluster-similar-issues
  • Lane:     feat-02

  • When the agent opens its pull request, label it 'lane: feat-02'. The gate fails
    the change if any file is outside the lane.
```

Commit the policy it wrote (`git add .lanekeeper .gitignore`) before the agent commits
anything: until you do, the agent's first `git add -A` sweeps the policy into its own
branch, where the gate denies it — a policy change is its own lane. `spawn --ticket`
says so when the policy is still uncommitted.

The file list is the ticket's *Allowed File Paths* or *Target Modules* section. A
ticket that names no files is refused, never guessed at: say the files yourself with
`--allow 'src/checkout/**'`, or run `--propose` to have Claude Code suggest them from
the ticket and the tree, shown to you before they are used. If another lane could
touch the same files, it says so and lets you decide. On a project with no policy
yet, this first command writes one containing only this lane.

### What it does not do

- It does not invent work. No tickets, no lanes; it hands you to product-playbook.
- It does not stop an agent typing outside its lane. It stops the change merging.
- It does not judge with a model. The optional advisor (`divide.advisor: claude-code`)
  only suggests file paths for a ticket that names none, and its suggestion lands in the
  draft switched off for you to confirm.

### Where the board fits

`lanekeeper board` creates a GitHub project board with Lane, Owner and Seat fields and
the `lane:` labels, generated from your policy so the names agree. With `board.read:
true` a card's Lane outranks the ticket text, and `lanekeeper spawn --ticket 12` takes
the agent's lane and seat from the card. It needs `gh` with the `project` scope.

---

# Reference

Everything below is the full reference. The five minutes above is all a first run needs.

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

This is the mechanical form of the rule in `docs/legacy/01-working-agreement.md`: stop when the change
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
| **`lanekeeper init`** | The escape hatch: writes a policy with lanes detected from the directory layout (technology layers, not features). Use `start` unless you already know your lanes. |
| **`lanekeeper doctor`** | Diagnoses repository, worktree, and port health. |
| **`lanekeeper spawn`** | Provisions an isolated worktree, branch, `.env`, and allocated ports. `--ticket N` makes the ticket the boundary (its file list, `--allow`, or a confirmed `--propose`); with `board.read: true` the card's Lane and Seat win. `--open` opens the editor. |
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
| **[The lane file](docs/start-step2-divide.md)** | How `start` reads the tickets, proposes the split, and what `--confirm` writes. |
| **[The pre-flight](docs/start-step1-intake.md)** | What `start` checks before it divides anything. |
| **[The ticket form](docs/ticket-template.md)** | Why Allowed File Paths is the one required field. |
| **[Capability gates](specs/capability-gates.md)** | The seat cards and the three-state capability model. |
| **[Legacy process docs](docs/legacy/README.md)** | The pre-tool, layer-lane way of working. History, not instructions. |

---

## 🤝 Community & Contributing

Contributions are welcome! See our community guidelines:
* **[Contributing Guide](https://github.com/kish21/parallel-agents/blob/main/CONTRIBUTING.md)**
* **[Security Policy](https://github.com/kish21/parallel-agents/blob/main/SECURITY.md)**
* **[Code of Conduct](https://github.com/kish21/parallel-agents/blob/main/CODE_OF_CONDUCT.md)**

---

## License
[MIT](https://github.com/kish21/parallel-agents/blob/main/LICENSE)
