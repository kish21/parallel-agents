# Parallel Agents ⚡

[![Version](https://img.shields.io/badge/version-v0.1.0-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Run multiple AI coding agents safely in the same repository.**

Parallel Agents gives each coding agent its own Git worktree, branch, ports, environment, and code boundaries, so agents can work at the same time without accidentally interfering with each other.

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

## Why Parallel Agents?

AI coding agents are powerful, but running several agents in the same repository creates real operational problems:

* **File Overwrites**: One agent can modify files another agent is actively working on.
* **Port Clashes**: Two agents can accidentally claim the same development port.
* **Cross-Talk**: Frontends can connect to another agent's uncommitted backend code.
* **Migration Conflicts**: Shared database migrations can clash or create duplicate counters.
* **Out-of-Scope Changes**: An agent can modify central configs, auth, or infrastructure outside its assigned task.
* **Resource Leaks**: Failed agents can leave behind orphaned processes, blocked ports, or stale git state.

Parallel Agents adds a mechanical coordination and safety layer around your coding agents to prevent these problems.

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
Agent 1 → .parallel-agents/worktrees/agent-001
Agent 2 → .parallel-agents/worktrees/agent-002
Agent 3 → .parallel-agents/worktrees/agent-003
```
Agents never edit the same physical files simultaneously.

### 3. Lane
A lane defines which part of the codebase an agent is permitted to touch.
```yaml
lane: backend

allow:
  - src/api/**
  - src/services/**
  - tests/api/**

deny:
  - src/frontend/**
  - infrastructure/**
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
pip install -e .
```

### 2. Initialize the Repository
From your project root:
```bash
parallel-agents init
```
This creates the `.parallel-agents/` configuration and state directories.

### 3. Create an Agent
```bash
parallel-agents spawn \
  --name backend-1 \
  --lane backend \
  --task "Implement user authentication"
```
Parallel Agents provisions the isolated worktree, branch, `.env`, and dedicated ports automatically (and optionally starts an agent execution process when `--command` is supplied).

### 4. Create Another Agent
```bash
parallel-agents spawn \
  --name frontend-1 \
  --lane frontend \
  --task "Build the login interface"
```
Now both agents can work simultaneously without collision.

### 5. Check Agents
```bash
$ parallel-agents status

📋 PARALLEL AGENTS — MY-PROJECT

Agent ID     Name           Seat   Lane         Status     Ports            Task
----------------------------------------------------------------------------------------------------
agent-001    backend-1      SR1    backend      RUNNING    8001/3001        Implement user authentication
agent-002    frontend-1     JR1    frontend     RUNNING    8002/3002        Build the login interface
```

### 6. Validate an Agent's Work
```bash
$ parallel-agents validate agent-001

🛡️ VALIDATION REPORT: backend-1 (agent-001)
Lane: backend

  [Lane Compliance]
    ✓ All 4 changed files are within allowed lane paths.

==================================================
✅ VALIDATION PASSED: PR is safe to submit and merge.
```

### 7. Inspect Changed Files
```bash
parallel-agents diff agent-001
```

### 8. Stop an Agent
```bash
parallel-agents stop agent-001
```

### 9. Clean Up Safely
```bash
parallel-agents cleanup agent-001
```

---

## How It Works

```
WITHOUT PARALLEL AGENTS:                      WITH PARALLEL AGENTS:

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

Lanes are how you define architectural ownership boundaries:

```yaml
lanes:
  backend:
    allow:
      - src/api/**
      - src/services/**
      - tests/api/**
    deny:
      - src/frontend/**

  frontend:
    allow:
      - src/frontend/**
      - tests/frontend/**
    deny:
      - src/api/**

  infrastructure:
    allow:
      - infrastructure/**
      - deployment/**
```

```
backend agent        frontend agent        infrastructure agent
      ↓                     ↓                       ↓
backend files         frontend files        infrastructure files
```

The goal is not to isolate every single file—it is to make parallel execution predictable.

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
error, never a lane that happens to allow every path.

> **Commit `.parallel-agents/config.yaml`.** It is the policy every agent is validated
> against — the team's shared contract. `parallel-agents init` adds ignore rules that keep
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

`parallel-agents declare <agent>` produces the PR template's mandatory Gate Declaration
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
parallel-agents status
parallel-agents logs backend-1
parallel-agents stop backend-1
parallel-agents restart backend-1
parallel-agents repair backend-1
parallel-agents cleanup backend-1
```

---

## Mechanical Validation

Never rely on an AI agent's word that its work is complete. Parallel Agents independently validates:

```bash
$ parallel-agents validate backend-1

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
$ parallel-agents doctor

🩺 PARALLEL AGENTS DOCTOR

  ✓ Git repository: Valid Git repository detected.
  ✓ Configuration: Valid config (Project: demo, Max agents: 4).
  ✓ Worktrees: All 1 agent worktrees are intact.
  ✗ Port allocations: 2 port allocation issue(s) detected.
      ↳ Port 3001 still reserved by stopped agent 'agent-001'.
      ↳ Port 8001 still reserved by stopped agent 'agent-001'.
  ✓ Agent processes: All active agent process states are consistent.

⚠️ 1 problem(s) detected. Run 'parallel-agents repair' to fix.
```

`doctor` reports three classes of problem:

| Class | Meaning |
|---|---|
| **Orphaned** | A port is still reserved by an agent that has stopped, failed, completed, or no longer exists. If a process is *still listening* on it, it is reported as a leaked server. |
| **Conflict** | The port ledger and an agent's own recorded ports disagree — the dangerous case, because the ledger could hand the same port to a second agent. |
| **Stale process** | An agent is marked `RUNNING` but its PID is dead. |

Run repair to automatically clean up orphaned resources:
```bash
parallel-agents repair
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

Parallel Agents is provider-independent. It uses a pluggable `AgentAdapter` abstraction:

```
              Parallel Agents
                    │
              Agent Adapter
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
   Claude CLI    Cursor / IDE   Generic CLI
```

The orchestration layer handles isolation, ports, and validation; the adapter handles execution.

---

## 🛠️ CLI Reference

| Command | Purpose |
| :--- | :--- |
| **`parallel-agents init`** | Initializes repository and creates configuration. |
| **`parallel-agents doctor`** | Diagnoses repository, worktree, and port health. |
| **`parallel-agents spawn`** | Provisions an isolated worktree, branch, `.env`, and allocated ports. |
| **`parallel-agents status`** | Shows active agents, lanes, and allocated ports (`--json` supported). |
| **`parallel-agents validate`** | Mechanically validates lane compliance and runs test suites. |
| **`parallel-agents diff`** | Displays changed files classified as `[LANE OK]` vs. `[OUT-OF-LANE]`. |
| **`parallel-agents inspect`** | Shows detailed agent metadata and environment variables. |
| **`parallel-agents logs`** | Tails structured execution logs for an agent session. |
| **`parallel-agents stop`** | Stops an active agent process. |
| **`parallel-agents restart`** | Restarts an agent in its worktree. |
| **`parallel-agents repair`** | Repairs stale states and releases orphaned ports. |
| **`parallel-agents declare`** | Generates the PR gate declaration from recorded state. |
| **`parallel-agents cleanup`** | Safely removes worktrees and releases port allocations. |

---

## 💡 Design Philosophy

1. **Isolation Over Instructions**: Do not merely instruct agents to avoid collisions; provide physically isolated environments.
2. **Mechanical Validation Over Trust**: Never assume an agent followed the rules; mechanically verify diffs against lane policies.
3. **Simple Over Clever**: Coordinate coding agents with clarity; do not build an autonomous swarm or bloated web UI.
4. **Developer in Control**: Agents propose changes; humans review and merge them.
5. **Safe Cleanup**: Never sacrifice uncommitted developer work for aggressive cleanup.

---

## 🚫 What Parallel Agents Is Not

* ❌ Not an autonomous AI software company.
* ❌ Not an AI project manager.
* ❌ Not a replacement for Git or CI/CD.
* ❌ Not tied to any single AI vendor or model.

It is a **lightweight coordination and safety layer** for parallel AI coding agents.

---

## 🧪 Automated Testing & Reliability Benchmarks

Parallel Agents includes a **tracked 36-test unit, integration, concurrency stress, and failure recovery suite** and an automated reproducibility benchmark runner.

### 1. Run the Full Test Suite
```bash
python -m unittest discover tests
```
```
....................................
----------------------------------------------------------------------
Ran 108 tests in 13.2s

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
📈 PARALLEL AGENTS: BENCHMARK RESULTS & SYSTEM RELIABILITY METRICS
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
| **[🎬 End-to-End Walkthrough](EXAMPLES.md)** | Step-by-step lifecycle of Ticket #102 from assignment to merge. |
| **[01. Working Agreement](01-working-agreement.md)** | Definition-of-Done, path boundary contracts, and merge discipline. |
| **[02. Conflict Management](02-conflict-management.md)** | Worktree deep-dive, port tables, and Disaster Recovery Runbook. |
| **[03. Orchestration](03-orchestration.md)** | Capability cards, scaling 2→4→6 seats, and ROI metrics. |
| **[04. Agent Setup](04-agent-setup.md)** | Prompts for Senior/Junior agents and token cost hygiene. |
| **[05. GitHub Mechanics](05-github-mechanics.md)** | Board custom fields, disjoint milestones, and single-account routing. |
| **[06. Free-Tier Operations](06-free-tier-ops.md)** | CI minute optimization, public vs private repo trade-offs, and verified mirrors. |

---

## 🤝 Community & Contributing

Contributions are welcome! See our community guidelines:
* **[Contributing Guide](CONTRIBUTING.md)**
* **[Security Policy](SECURITY.md)**
* **[Code of Conduct](CODE_OF_CONDUCT.md)**

---

## License
[MIT](LICENSE)
