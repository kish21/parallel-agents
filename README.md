# Parallel Agents ⚡

[![Version](https://img.shields.io/badge/version-v0.1.0-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Run 2 to 6 AI coding agents simultaneously on one codebase without merge collisions, port clashes, or rotting prompts.**

A vendor-neutral, project-neutral framework, guide, and drop-in scaffolding for parallel multi-agent software development.

**Current Release**: [`v0.1.0` (Alpha / Foundation)](CHANGELOG.md)

---

## 🚀 5-Minute Quickstart (Replicate in 4 Steps)

### Step 1: Bootstrap Your GitHub Project Board & Fields
Create your delivery board, custom single-select fields (`Lane`, `Seat`, `Owner`), standard labels, and disjoint milestones automatically in under 30 seconds:

```bash
# 1. Copy config and add your repository name
cp bootstrap.conf.example bootstrap.conf

# 2. Run the bootstrap script
./bootstrap.sh
```

### Step 2: Initialize 4 Isolated Worktrees & Seats
Set up local worktrees with dedicated ports and seat identifiers:

```bash
# Create worktrees directory and 4 seats
mkdir -p worktrees
git worktree add worktrees/sr1 -b seat/sr1
git worktree add worktrees/sr2 -b seat/sr2
git worktree add worktrees/jr1 -b seat/jr1
git worktree add worktrees/jr2 -b seat/jr2

# Create seat marker files
echo 'SEAT="SR1"' > worktrees/sr1/.lane
echo 'SEAT="SR2"' > worktrees/sr2/.lane
echo 'SEAT="JR1"' > worktrees/jr1/.lane
echo 'SEAT="JR2"' > worktrees/jr2/.lane
```

### Step 3: Copy Drop-In GitHub & Git Templates
```bash
# Copy PR and Issue templates
mkdir -p .github/ISSUE_TEMPLATE
cp templates/pull_request_template.md .github/
cp templates/issue-template-task.yml .github/ISSUE_TEMPLATE/
cp templates/issue-template-bug.yml .github/ISSUE_TEMPLATE/

# Copy union merge rules
cp templates/gitattributes .gitattributes
```

### Step 4: Launch Your Agent Sessions
Paste the drop-in prompt templates from [`04-agent-setup.md`](04-agent-setup.md) into each agent harness (pointing `SR1`/`SR2` to senior roles, `JR1`/`JR2` to junior roles).

---

## 📚 The Complete Guide

| Chapter | Topic | What You Learn / Copy |
| :--- | :--- | :--- |
| **[01. Working Agreement](01-working-agreement.md)** | **Quality Bar & Contracts** | Definition-of-Done checklist, security boundaries, and PR review rules. |
| **[02. Conflict Management](02-conflict-management.md)** | **Isolation & Migrations** | Port allocation matrix, worktree vs clone guide, and migration collision prevention. |
| **[03. Orchestration](03-orchestration.md)** | **Capability Cards & Scaling** | 3-state capability model (`native`, `author-required`, `unavailable`) and review matrix. |
| **[04. Per-Agent Setup](04-agent-setup.md)** | **Prompts & Session Hygiene** | Copy-paste prompt templates for Senior and Junior seats; token cost management. |
| **[05. GitHub Mechanics](05-github-mechanics.md)** | **Board & Issue Routing** | Custom fields, disjoint milestones, sub-issues, and single-account routing. |
| **[06. Free-Tier Operations](06-free-tier-ops.md)** | **CI & Verified Mirror** | Public vs. private trade-offs, divergence checkers, and CI minute optimization. |

---

## 💡 Core Principles (Validated in Practice)

1. **Seats are Capped by Lanes, Not Subscriptions**:
   - If your codebase has 4 separable code paths, adding a 5th agent produces merge collisions, not more throughput. Scale by modularizing code paths.
2. **Seats are Slots, Vendors are Lines in a Card**:
   - Seats are fixed (`SR1`, `JR1`). Swapping AI models/vendors is a one-line edit in `.lane`—no board churn, no branch renames.
3. **Make Weaker Harnesses Declare Themselves**:
   - A weaker agent must state in the PR template which verification tests it actually executed, and stop completely when touching migrations or auth.
4. **Use Forge Ticket IDs, Never Self-Chosen Counters**:
   - Name migrations and generated assets after the GitHub ticket ID to prevent simultaneous counter collisions across seats.

---

## 📦 Project Structure

```
parallel-agents/
├── README.md                  # Quickstart and overview
├── 01-working-agreement.md     # Definition of done & contracts
├── 02-conflict-management.md   # Port matrix & worktree isolation
├── 03-orchestration.md         # Capability cards & review chains
├── 04-agent-setup.md          # Prompts & .lane configurations
├── 05-github-mechanics.md     # Board fields & issue management
├── 06-free-tier-ops.md        # CI optimization & verified mirror
├── bootstrap.sh               # One-touch board setup script
├── bootstrap.conf.example     # Configuration for bootstrap script
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
MIT
