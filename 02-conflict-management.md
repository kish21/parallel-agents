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

## 1. Worktrees vs. Separate Clones

You can isolate agents using either **Git Worktrees** or **Separate Clones**. Both have clear trade-offs:

```
GIT WORKTREES (Shared Git Directory)        SEPARATE CLONES (Complete Isolation)
      ┌─────────────┐                            ┌───────────┐  ┌───────────┐
      │ .git (Root) │                            │ Clone SR1 │  │ Clone JR1 │
      └──┬───────┬──┘                            │   .git    │  │   .git    │
         │       │                               └───────────┘  └───────────┘
   ┌─────▼─┐   ┌─▼─────┐                          • Pro: Zero shared state (stashes,
   │  SR1  │   │  JR1  │                            locks, refs).
   └───────┘   └───────┘                          • Con: Uses more disk space; 
   • Pro: Fast, shared commit cache.                requires independent fetches.
   • Con: Stash and branch locks are shared.
```

### Option A: Git Worktree Setup (Recommended for Local Dev)

Run this copyable bash script from the repository root to create 4 isolated worktrees:

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Ensure worktrees directory exists
mkdir -p worktrees

# 2. Add worktree for each seat on its own branch
git worktree add worktrees/sr1 -b seat/sr1
git worktree add worktrees/sr2 -b seat/sr2
git worktree add worktrees/jr1 -b seat/jr1
git worktree add worktrees/jr2 -b seat/jr2

# 3. Create .lane marker file in each worktree
echo "SEAT=SR1" > worktrees/sr1/.lane
echo "SEAT=SR2" > worktrees/sr2/.lane
echo "SEAT=JR1" > worktrees/jr1/.lane
echo "SEAT=JR2" > worktrees/jr2/.lane

echo "✅ 4 seats initialized in ./worktrees/"
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
supabase/migrations/20260830120000_issue_808_add_billing.sql
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
