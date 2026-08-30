# Parallel Agents ⚡

[![Version](https://img.shields.io/badge/version-v0.1.0-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Run 2 to 6 AI coding agents simultaneously on one codebase without merge collisions, port clashes, or rotting prompts.**

A practical blueprint, operational guide, and drop-in toolchain for parallel multi-agent software engineering.

---

## 📖 The Story: Why This Exists

### The Dream
You set up 4 AI coding agent subscriptions (or open 4 agent tabs). You assign each a ticket, imagining a 4x boost in engineering velocity. You picture an autonomous software factory building your product in parallel.

### The 24-Hour Reality (The Collision Trap)
Within hours, the system descends into chaos:

```
                  ┌──────────────┐      ┌──────────────┐
                  │   Agent 1    │      │   Agent 2    │
                  │ (Frontend UI)│      │  (Backend)   │
                  └──────┬───────┘      └──────┬───────┘
                         │                     │
                Starts on Port 3000   Hardcodes API to 8000
                         │                     │
                         ▼                     ▼
                  ┌────────────────────────────────────┐
                  │ 💥 CROSS-TALK: Agent 1's UI tests  │
                  │ against Agent 2's uncommitted API! │
                  └────────────────────────────────────┘
```

1. **The Dev Server Collision**: Agent A starts on port 8000; Agent B auto-increments to 8001. Agent A's browser frontend quietly connects to Agent B's uncommitted backend. You spend 2 hours debugging phantom bugs that only exist because two agents are talking to different code.
2. **The Database Migration Disaster**: Two agents look at the `migrations/` folder at the same time. Both see `0042_user.sql`, so both name their new file `0043_feature.sql`. When both PRs merge, migrations fail with duplicate keys.
3. **The Git Merge Gridlock**: Four agents push branches touching shared central files (`index.ts`, `routes.py`, `Makefile`). Instead of writing code, you spend your entire afternoon resolving 3-way merge conflicts.
4. **The "Rotting Hand-Copied Prompt"**: You paste testing rules into prompt windows. By day three, one agent is running deprecated test commands that measure the wrong metrics, while another agent burns $20 in tokens re-reading massive command logs.

### The Core Realization
> **Seats are capped by non-overlapping code lanes, not by how many AI subscriptions you own.**
> 
> If your codebase has 4 separable code paths, adding a 5th agent produces merge collisions, not a 5th stream of work. Scaling parallel agents requires **physical lane boundaries, deterministic port allocations, and honest capability declarations**.

This repository is the battle-tested system that turns that chaos into a quiet, predictable assembly line.

---

## 🧩 The 4 Core Ideas Explained Simply

```
┌───────────────────────────┬───────────────────────────┐
│ 1. SEAT = SLOT            │ 2. LANE = CODE PATH       │
│ Seats are permanent       │ Group by directory paths  │
│ roles (SR1, JR1). Model   │ (interface/, service/),   │
│ vendors live in a .lane   │ NEVER by broad feature    │
│ config file.              │ topics.                   │
├───────────────────────────┼───────────────────────────┤
│ 3. DECLARE YOUR GATE      │ 4. FORGE-BOUND IDS        │
│ Weaker models must state  │ Name migrations and files │
│ what tests they ran in    │ after GitHub ticket IDs   │
│ the PR before merging.    │ to kill race conditions.  │
└───────────────────────────┴───────────────────────────┘
```

---

## 🚀 Step-by-Step: From Zero to Parallel in 5 Minutes

Follow these 4 steps to set up your repository for parallel agents:

### Step 1: Bootstrap Your GitHub Delivery Board
Instead of configuring project boards by hand, use the automated setup script to create custom single-select fields (`Lane`, `Seat`, `Owner`), status columns, standard labels, and disjoint milestones in under 30 seconds:

```bash
# 1. Copy the example config and add your repo name
cp bootstrap.conf.example bootstrap.conf

# 2. Run the bootstrap script
./bootstrap.sh
```

---

### Step 2: Spin Up Isolated Worktrees & Seats
Never let agents share one working directory or fight over git branches. Create isolated git worktrees with dedicated ports:

```bash
# 1. Create worktrees directory and 4 seats
mkdir -p worktrees
git worktree add worktrees/sr1 -b seat/sr1
git worktree add worktrees/sr2 -b seat/sr2
git worktree add worktrees/jr1 -b seat/jr1
git worktree add worktrees/jr2 -b seat/jr2

# 2. Drop the .lane seat identifier into each checkout
echo 'SEAT="SR1"' > worktrees/sr1/.lane
echo 'SEAT="SR2"' > worktrees/sr2/.lane
echo 'SEAT="JR1"' > worktrees/jr1/.lane
echo 'SEAT="JR2"' > worktrees/jr2/.lane
```

---

### Step 3: Drop In Quality Gates & Merge Rules
Copy the ready-to-use PR template (with mandatory test execution declarations), issue forms, and union-merge git attributes:

```bash
# 1. Copy GitHub Issue and PR templates
mkdir -p .github/ISSUE_TEMPLATE
cp templates/pull_request_template.md .github/
cp templates/issue-template-task.yml .github/ISSUE_TEMPLATE/
cp templates/issue-template-bug.yml .github/ISSUE_TEMPLATE/

# 2. Enable union merging for shared index files
cp templates/gitattributes .gitattributes
```

---

### Step 4: Launch Your Agent Sessions
Open an agent session in each worktree and paste the lightweight, non-rotting role prompt:

* **In `worktrees/sr1` & `sr2` (Senior Seats)**: Paste the prompt from [`04-agent-setup.md §2`](04-agent-setup.md#2-drop-in-prompt-senior--lead-agent-sr1--sr2).
* **In `worktrees/jr1` & `jr2` (Junior Seats)**: Paste the prompt from [`04-agent-setup.md §3`](04-agent-setup.md#3-drop-in-prompt-junior-agent-jr1--jr2).

Your agents will now pick tickets assigned to their seat, work strictly inside their assigned code lane, and run verification tests on isolated ports.

---

## 📚 The Complete Deep-Dive Handbook

| Chapter | Topic | What It Teaches |
| :--- | :--- | :--- |
| **[01. Working Agreement](01-working-agreement.md)** | **Quality Bar & Contracts** | Definition-of-Done checklist, path boundary contracts, security rules, and merge discipline ("never merge without the owner"). |
| **[02. Conflict Management](02-conflict-management.md)** | **Isolation & Migrations** | 4-seat port table, worktrees vs. separate clones, ticket-based migration IDs, and resolving shared index conflicts. |
| **[03. Orchestration](03-orchestration.md)** | **Capability Cards & Scaling** | The 3-state capability model (`native` / `author-required` / `unavailable`), scaling 2→4→6 seats, and review chains. |
| **[04. Per-Agent Setup](04-agent-setup.md)** | **Prompts & Session Hygiene** | Copy-paste prompt templates for Senior and Junior seats; controlling context token runaway. |
| **[05. GitHub Mechanics](05-github-mechanics.md)** | **Board & Issue Routing** | Board single-select fields, disjoint milestones, sub-issues, and single-account routing. |
| **[06. Free-Tier Operations](06-free-tier-ops.md)** | **CI & Verified Mirror** | Public vs. private trade-offs, divergence check scripts, and optimizing CI allowances per seat. |

---

## 📦 Repository Structure

```
parallel-agents/
├── README.md                  # The Story, Concepts & 5-Minute Quickstart
├── 01-working-agreement.md     # Quality Bar & Definition-of-Done
├── 02-conflict-management.md   # Port Allocation & Collision Prevention
├── 03-orchestration.md         # Capability Cards & Scaling Patterns
├── 04-agent-setup.md          # Agent Prompts & Token Cost Control
├── 05-github-mechanics.md     # GitHub Board & Issue Routing
├── 06-free-tier-ops.md        # CI Minute Optimization & Verified Mirror
├── bootstrap.sh               # One-touch board setup script
├── bootstrap.conf.example     # Configuration for bootstrap script
├── CHANGELOG.md               # Semantic Versioning Release Notes
└── templates/                 # Ready-to-copy issue forms, PR templates & hooks
    ├── pull_request_template.md
    ├── issue-template-task.yml
    ├── issue-template-bug.yml
    ├── ci.yml
    ├── dot-lane.example
    ├── gitattributes
    └── git-hooks/
```

---

## License
[MIT](LICENSE)
