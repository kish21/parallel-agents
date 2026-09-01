# 06 — Running on the Free Tier & CI Operations

> **Goal**: Maximize velocity on free GitHub plans without hitting metered CI lockouts, missing branch protections, or corrupted histories.

---

## ⚡ Quick Start: Public vs. Private Matrix

| Platform Feature | Public Repository (Free) | Private Repository (Free) |
| :--- | :--- | :--- |
| **Hosted CI Minutes** | **Unmetered (Free)** | Metered (Limited monthly pool) |
| **Branch Protection Rules** | **Fully Available (Free)** | Refused (Requires Team/Enterprise) |
| **Recommended Strategy** | Standard PR Gates + Rulesets | Local Hooks + Verified Mirror |

---

## 1. The Triad of Controls: Prevent, Detect, Recover

When running on the free tier for private repositories where server-side branch protection is withheld, distinguish between these three controls:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CONTROLS ARCHITECTURE                           │
├─────────────────┬──────────────────────────┬───────────────────────────┤
│ 1. PREVENT      │ 2. DETECT                │ 3. RECOVER                │
│ (Local Gate)    │ (Divergence Checker)     │ (Verified Mirror)         │
│                 │                          │                           │
│ Pre-push hooks  │ Scheduled comparison to  │ Clean bare mirror clone   │
│ validate tests  │ detect unverified or     │ updated ONLY after all    │
│ before sending. │ non-fast-forward pushes. │ gates succeed.            │
└─────────────────┴──────────────────────────┴───────────────────────────┘
```

---

## 2. The Verified Mirror (Your Free-Tier Insurance)

A plain backup copies whatever is pushed—including broken or malicious commits. 
A **Verified Mirror** updates **only after tests pass**, creating a guaranteed known-good branch history.

### Copyable Verified Sync Script (`scripts/sync-mirror.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Configuration
MAIN_REMOTE="origin"
MIRROR_REMOTE="mirror"
DEFAULT_BRANCH="main"

echo "🔍 Running test suite before updating verified mirror..."
npm test --silent || { echo "❌ Tests failed. Mirror update aborted."; exit 1; }

echo "🚀 Pushing to main remote..."
git push "$MAIN_REMOTE" "$DEFAULT_BRANCH"

echo "🛡️ Updating verified mirror..."
git push "$MIRROR_REMOTE" "$DEFAULT_BRANCH"

echo "✅ Verified mirror synced successfully."
```

---

## 3. Scheduled Divergence Checker

If a collaborator or agent bypasses the local gate and force-pushes a bad change to `main`, this script detects the divergence immediately:

```bash
#!/usr/bin/env bash
# scripts/check-divergence.sh
set -euo pipefail

git fetch origin main --quiet
git fetch mirror main --quiet

LOCAL_HEAD=$(git rev-parse origin/main)
MIRROR_HEAD=$(git rev-parse mirror/main)

if [ "$LOCAL_HEAD" = "$MIRROR_HEAD" ]; then
  echo "✅ Branches in sync."
  exit 0
fi

# Check if origin is a fast-forward of mirror
if git merge-base --is-ancestor "$MIRROR_HEAD" "$LOCAL_HEAD"; then
  echo "ℹ️ Origin is ahead of mirror (normal unverified progress)."
else
  echo "🚨 CRITICAL: Origin diverged non-fast-forward from verified mirror!"
  echo "   Possible force-push or missing gate detected."
  exit 2
fi
```

---

## 4. CI Optimization: Budgeting Minutes Per Seat

On private repositories, your monthly GitHub Actions allowance divides by the number of seats:
* 4 seats running tests on every draft commit will burn through monthly free allowances in days.
* When allowance is exhausted, jobs fail instantly with **0 steps and no logs**.

### 3 Rules for Free-Tier CI Workflows

1. **Cancel Superseded Runs**: If an agent pushes 3 commits in 2 minutes, kill the older runs immediately:
   ```yaml
   concurrency:
     group: ${{ github.workflow }}-${{ github.ref }}
     cancel-in-progress: true
   ```
2. **Path Filtering**: Skip heavy test suites for documentation or asset changes:
   ```yaml
   on:
     push:
       paths-ignore:
         - '**.md'
         - 'docs/**'
         - '.lane'
   ```
3. **Move Fast Tests to Local Hooks**: Run linter and unit tests in the pre-push hook so failing code never touches hosted CI.
