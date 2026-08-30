# 01 — Working Agreement

> **Goal**: Establish a clear, enforceable standard of work across all human and AI seats. Every agent session knows the bar, the boundary contracts, and the security rules before touching code.

---

## ⚡ Quick Start (Copy-Paste Checklist)

Drop this checklist into your PR template or issue description. Every seat must satisfy these points before a pull request can merge.

```markdown
### Definition of Done Checklist
- [ ] **Lane Respected**: Touched only files inside assigned lane (`interface/`, `service/`, `data/`, or `platform/`).
- [ ] **Tests Passing**: Added/updated unit tests; ran local verification suite.
- [ ] **No Dead Controls**: UI controls are wired to live state; no disconnected UI or dummy placeholders.
- [ ] **Schema & Migrations Safe**: No unmerged schema changes applied to the shared live database.
- [ ] **Zero Hardcoded Secrets / Ports**: Environment variables and ports use configured variables.
- [ ] **Self-Contained Follow-ups**: Any out-of-scope debt filed as a distinct issue with parent links.
```

---

## 1. The Core Philosophy

When multiple AI agents work on the same codebase simultaneously, standard human assumptions break down:
1. **Agents do not have ambient awareness.** An agent working in seat `JR1` does not know what seat `SR1` merged five minutes ago unless it fetches and reads the diff.
2. **Weaker harnesses will quietly lower the bar** unless forced to declare what verification steps they actually executed.
3. **Speed without boundaries produces merge gridlock.** Four agents pushing uncoordinated changes produce four times the merge conflicts, not four times the features.

The working agreement turns loose conventions into **explicit contracts**.

---

## 2. Per-Feature Contract: Inputs, Outputs, and Boundaries

Every ticket assigned to a seat must have a clear contractual boundary before coding starts.

### The 3 Rules of Boundary Isolation

| Rule | Principle | What it Prevents |
| :--- | :--- | :--- |
| **1. One Lane, One Owner** | A ticket only modifies files within its declared path lane. | Merge conflicts across concurrent branches. |
| **2. Interface First** | If Lane A needs data from Lane B, define the type/schema contract first. | Uncoordinated API breakage and blocking. |
| **3. Never Guess Downstream Intent** | If an API response shape is ambiguous, the seat stops and clarifies. | Cascading bug fixes across multiple seats. |

### Contract Template for Issue Descriptions

When filing or refining a ticket, include this copyable block:

```markdown
### Boundary Contract
- **Lane**: `service/`
- **Allowed Paths**:
  - `backend/app/services/billing/`
  - `backend/tests/services/billing/`
- **Forbidden Paths**:
  - `frontend/` (Interface lane)
  - `database/migrations/` (Data lane)
- **External Dependencies**: Consumes `UserRecord` type from `backend/app/types/user.py`
```

---

## 3. Security & Stability Definition of Done

AI agents are prone to taking the shortest path to make a test pass. The following sensitive areas have **zero-tolerance rules**:

### 1. Authentication & Authorization
* **Rule**: Never bypass auth checks or mock session tokens in production paths.
* **Failure Mode Prevented**: Agent writes a quick bypass for an integration test that accidentally persists into production.

### 2. Tenant & User Isolation
* **Rule**: Every database query, cache key, and storage lookup must be scoped by `tenant_id` / `user_id`.
* **Failure Mode Prevented**: Cross-tenant data leakage when filtering records in shared tables.

### 3. Database Migrations
* **Rule**: Never run an unmerged migration against a shared development database.
* **Rule**: Migration identifiers must be derived from the unique ticket number or precise timestamp, never sequential guess counters.
* **Failure Mode Prevented**: Local dev databases get placed in a state ahead of `main`, breaking every other seat's dev environment.

### 4. Billing & Financial State
* **Rule**: Any logic touching pricing, tokens, credits, or payments requires review from a Senior seat (`SR1` or `SR2`).

---

## 4. The Merge Discipline: Never Merge Without the Owner

In a multi-agent system, the default branch (`main`) is sacred. 

```
   ┌───────────┐      Local Test & Gate Pass       ┌───────────────┐
   │ Seat: JR1 ├──────────────────────────────────►│ Open PR (#42) │
   └───────────┘                                   └───────┬───────┘
                                                           │
                                            Senior Review  │ Capability: Native
                                            or Lead Gate   ▼
                                                   ┌───────────────┐
                                                   │  Approved &   │
                                                   │ Merged to main│
                                                   └───────────────┘
```

1. **Self-Merges are Forbidden for Junior Seats**:
   - `JR1` and `JR2` seats cannot merge their own pull requests.
   - A Senior seat (`SR1` / `SR2`) or the human repository owner must approve the PR.
2. **PRs Must Declare Executed Gates**:
   - Every PR must state explicitly: *"Ran test suite locally with 42 passed tests, 0 failures."*
3. **Branch Freshness Rule**:
   - If `main` has moved ahead while a PR was under review, the author seat must rebase on `origin/main` and re-run local tests before merging.

---

## 5. What to Do When a Seat is Blocked

When an agent seat cannot proceed (e.g., dependency missing in another lane, missing credentials, or architectural ambiguity):

1. **Do not guess or create dummy fallback implementations.**
2. **Push the work-in-progress branch** with the commit message `wip: [ticket-id] description`.
3. **Leave a structured comment on the ticket**:
   ```markdown
   ### ⚠️ Blocker Reported by Seat JR1
   - **Reason**: Requires database column `stripe_customer_id` from Ticket #104.
   - **Current State**: Service logic drafted in branch `feat/105-billing-sync`.
   - **Action Needed**: Waiting on Data lane (#104) to merge to `main`.
   ```
4. **Switch to the next unblocked ticket in the assigned lane.**
