# 02 — Conflict Management

> **Goal**: Eliminate runtime collisions, git merge races, database lockups, and port clashes across multiple parallel agent checkouts.

---

## ⚡ Quick Start: 4-Seat Isolation Matrix

To run 4 seats simultaneously without conflict, assign deterministic ports and isolated workspaces:

| Seat | Role | Port Range | Local Directory | Environment Config |
| :--- | :--- | :--- | :--- | :--- |
| **`SR1`** | Senior / Lead | `3001` (FE) / `8001` (BE) | `worktrees/sr1` | `.env.sr1` |
| **`SR2`** | Senior | `3002` (FE) / `8002` (BE) | `worktrees/sr2` | `.env.sr2` |
| **`JR1`** | Junior | `3003` (FE) / `8003` (BE) | `worktrees/jr1` | `.env.jr1` |
| **`JR2`** | Junior | `3004` (FE) / `8004` (BE) | `worktrees/jr2` | `.env.jr2` |

---

## 1. What is a Git Worktree? (How It Works Under the Hood)

If you have only used standard Git, you are accustomed to **one repository folder holding exactly one checked-out branch at a time**. Switching branches swaps the files in place.

A **Git Worktree** allows a single repository (`.git`) to project **multiple simultaneous working folders on your disk at the same time, each checked out to a completely different branch**.

```
                           SINGLE LOCAL REPOSITORY (.git)
                                   ┌─────────────┐
                                   │ .git folder │
                                   │ (All commit │
                                   │  database)  │
                                   └──┬───────┬──┘
                                      │       │
                Linked Worktree 1     │       │     Linked Worktree 2
             ┌────────────────────────┘       └────────────────────────┐
             ▼                                                         ▼
     ┌───────────────┐                                         ┌───────────────┐
     │ worktrees/sr1 │                                         │ worktrees/jr1 │
     │ Branch: sr1   │                                         │ Branch: jr1   │
     │ Port: 8001    │                                         │ Port: 8003    │
     │ Full files on │                                         │ Full files on │
     │ disk for SR1  │                                         │ disk for JR1  │
     └───────────────┘                                         └───────────────┘
```

---

### Why Worktrees Are Superior to `git clone` for Parallel Agents

| Feature | Standard `git clone` (4 Copies) | `git worktree` (1 Repo, 4 Worktrees) |
| :--- | :--- | :--- |
| **Creation Time** | Slow (Minutes to download/copy entire history) | **Instant (< 1 second)** |
| **Disk Space** | Multiplies size by 4x (`.git` copied 4 times) | **Lean (1 shared `.git` commit database)** |
| **Branch Sharing** | Must `push` to GitHub and `pull` across clones | **Instant (Rebase local branches with zero network lag)** |
| **File Isolation** | Completely separate physical folders | **Completely separate physical folders** |

---

### Step-by-Step: Managing Worktrees in Practice

#### 1. Create Worktrees for Your 4 Seats
Run this from your repository root. It creates 4 independent folders inside `./worktrees/`, each checked out to its own seat branch:

```bash
# 1. Ensure worktrees parent folder exists
mkdir -p worktrees

# 2. Add worktree for each seat with its own branch
git worktree add worktrees/sr1 -b seat/sr1
git worktree add worktrees/sr2 -b seat/sr2
git worktree add worktrees/jr1 -b seat/jr1
git worktree add worktrees/jr2 -b seat/jr2

# 3. Create the .lane marker in each folder so agents know their seat
echo 'SEAT="SR1"' > worktrees/sr1/.lane
echo 'SEAT="SR2"' > worktrees/sr2/.lane
echo 'SEAT="JR1"' > worktrees/jr1/.lane
echo 'SEAT="JR2"' > worktrees/jr2/.lane
```

#### 2. Inspect Active Worktrees
To see all connected worktrees, their physical paths, and active branches:

```bash
$ git worktree list
/Users/dev/my-project             5a39e87 [main]
/Users/dev/my-project/worktrees/sr1  5a39e87 [seat/sr1]
/Users/dev/my-project/worktrees/sr2  5a39e87 [seat/sr2]
/Users/dev/my-project/worktrees/jr1  5a39e87 [seat/jr1]
/Users/dev/my-project/worktrees/jr2  5a39e87 [seat/jr2]
```

#### 3. How Files Exist on Disk
Inside each worktree folder (`worktrees/jr1`), you have a complete working tree of all project files. 

Instead of a heavy `.git/` directory, there is a tiny single-line `.git` file that tells Git:
```
gitdir: /Users/dev/my-project/.git/worktrees/jr1
```
Agents can run `npm install`, compile assets, start dev servers, and run test suites in `worktrees/jr1` without affecting `worktrees/sr1` in any way!

#### 4. Removing / Cleaning a Worktree
When a seat or feature branch is retired:

```bash
# Remove the worktree folder and unlink it from git
git worktree remove worktrees/jr1

# Clean up any stale worktree metadata
git worktree prune
```

> [!CAUTION]
> **Git Stash Hazard in Worktrees**: The git stash is global to the entire repository. If `JR1` runs `git stash` and `SR1` runs `git stash pop`, `SR1` will accidentally apply `JR1`'s uncommitted changes.
> **Rule**: Never use `git stash` in multi-seat worktrees. Commit WIP to a branch or copy modified files to a temp directory instead.

---

## 2. Port Allocation & Environment Configuration

### The Failure Mode: Port Leaks
If port numbers are hardcoded in source code or `Makefile`s:
* Seat `JR1` starts a backend server on `8000`.
* Seat `SR1` opens its browser at `localhost:3000` (which connects to `8000`).
* `SR1` is now unknowingly sending requests to `JR1`'s uncommitted code!

### The Solution: Parameterized Ports

In your application code, **never hardcode default ports**. Read them strictly from environment variables.

#### Example: Copyable `.env.example`
```env
# Frontend Port
PORT=3000
VITE_PORT=3000

# Backend API URL
API_PORT=8000
VITE_API_URL=http://localhost:8000
```

#### Example: Copyable Seat Config (`worktrees/jr1/.env`)
```env
PORT=3003
VITE_PORT=3003
API_PORT=8003
VITE_API_URL=http://localhost:8003
```

---

## 3. Database Migrations & Collision-Free Identifiers

### Failure Mode 1: The Self-Chosen Counter Collision
Two agents start working at the same time. Both look at the migrations folder:
* Highest existing file is `0042_add_users.sql`.
* Seat `SR1` names its new file `0043_add_orders.sql`.
* Seat `JR1` names its new file `0043_add_coupons.sql`.
* Both merge: one file is silently overwritten or causes a duplicate key error in the migration runner.

### The Rule: Use the Forge Ticket ID
Never let an agent calculate a sequence number. Always key migration files and generated documents by the **GitHub Ticket Number**:

```bash
# ❌ BAD: Sequential Guess
supabase/migrations/0043_add_billing.sql

# ✅ GOOD: Issue-Bound Timestamp/ID
supabase/migrations/<UTC-timestamp>_issue_<N>_add_billing.sql
```

---

## 4. Resolving Conflicts in Shared Index Files

When multiple seats register new modules, plugins, or documents, they all append a line to a central `index.ts`, `registry.py`, or `README.md`.

### The 3-Layer Solution

1. **Layer 1: Auto-generate the index**:
   Write a small pre-build script that scans the directory and generates the index dynamically rather than hand-editing it.
2. **Layer 2: Union Merge Strategy**:
   Add a `.gitattributes` rule so git merges appends from both branches automatically instead of conflicting:
   ```gitattributes
   # Add to .gitattributes in repo root
   docs/index.md merge=union
   src/registry/generated_list.txt merge=union
   ```
3. **Layer 3: CI Drift Verification**:
   Add a CI check that re-generates the index and fails if a PR made uncommitted manual edits to generated files.

---

## 5. The "Tree Someone is Standing In" Rule

When a human developer or tester is manually verifying a feature in a running checkout:
1. **Never write files or switch branches in that checkout.**
2. Dev servers with hot-module reload (HMR) will immediately restart the app, wiping the human's in-progress state or form inputs.
3. If an agent needs to make fixes, it must make them on its own seat's worktree/branch, run tests, and only notify the human when ready for a fresh pull.

---

## 6. Disaster Recovery Runbook (When an Agent Goes Off the Rails)

Even with strong rules, agents will occasionally hallucinate dependencies, touch forbidden paths, or leave hung background processes. Use these fast rollback recipes:

### Scenario A: Agent Corrupted Its Worktree
If an agent created messy untracked files, broken build caches, or bad dependency installations:

```bash
# In the corrupted worktree (e.g. worktrees/jr1)
git reset --hard HEAD
git clean -fdx
git checkout main && git pull origin main
echo 'SEAT="JR1"' > .lane
```

### Scenario B: Agent Accidentally Applied Unmerged DB Migrations
If an agent ran an uncommitted schema change against the shared development database:

```bash
# 1. Roll back the specific migration using your tool's rollback command
# Example for Supabase / Prisma:
supabase db reset
# or
npx prisma migrate reset --force

# 2. Re-verify the live schema matches origin/main
git checkout origin/main -- database/
```

### Scenario C: Agent Modified Files Outside Its Lane
If an agent generated a PR with 15 files, but 5 belong to forbidden lanes:

```bash
# Checkout the PR branch
git checkout feat/my-branch

# Restore forbidden files back to main's state
git checkout origin/main -- frontend/src/shared/central_config.ts
git commit -m "fix: revert out-of-lane changes"
git push origin feat/my-branch
```

### Scenario D: Zombie Process / Port Clash
If an agent session died but left port 8003 or 3003 blocked:

```bash
# Linux / macOS:
lsof -ti :8003 | xargs kill -9

# Windows (PowerShell):
Get-Process -Id (Get-NetTCPConnection -LocalPort 8003).OwningProcess | Stop-Process -Force
```

