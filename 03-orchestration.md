# 03 — Orchestration & Capability Cards

> **Goal**: Define seat roles, review chains, capability boundaries, and scaling models without tying the team to any single AI vendor.

---

## ⚡ Quick Start: Capability Card Template

Copy this card into your team wiki or repository root as `capabilities.json` or `.lane.capabilities`:

```json
{
  "seat": "JR1",
  "vendor_harness": "Agent-X-v2",
  "capabilities": {
    "file_level_code_generation": "native",
    "unit_test_generation": "native",
    "local_test_execution": "native",
    "deep_code_review": "author-required",
    "security_review": "unavailable",
    "database_migrations": "author-required"
  },
  "max_allowed_lane_scope": ["interface", "service"],
  "forbidden_paths": ["database/migrations/", "infra/"]
}
```

---

## 1. The Three Capability States

Never assume all AI agent harnesses are equal. Treat capabilities as an explicit 3-state enum:

| State | Definition | Operational Rule |
| :--- | :--- | :--- |
| **`native`** | The harness reliably executes this task out of the box with zero hallucination. | Can execute autonomously within its lane. |
| **`author-required`** | The harness *can* do it, but requires explicit step-by-step guidance/scripts written by a senior seat. | Must run the verified script; cannot invent its own process. |
| **`unavailable`** | The harness cannot safely perform this task (e.g. lacks tool execution or context depth). | **Hard Stop**: Must escalate to a Senior seat (`SR1` / `SR2`). |

---

## 2. Seat Architecture: Slots vs. Vendors

```
GitHub Project Board              Local Checkout (.lane)              Active AI Harness
┌──────────────────┐             ┌────────────────────┐             ┌──────────────────┐
│ Ticket #808      │             │ Path: worktree/sr1 │             │ Vendor Model A   │
│ Seat: SR1        ├────────────►│ SEAT=SR1           ├────────────►│ (Fills SR1 Slot) │
│ Lane: service    │             └────────────────────┘             └──────────────────┘
└──────────────────┘
```

* **Seats are permanent operational slots**: `SR1`, `SR2` (Seniors/Leads), `JR1`, `JR2` (Juniors).
* **Vendors are ephemeral lines in a config**: If Vendor A releases a broken update or rate limits out, change `VENDOR=Model-B` in `.lane`. 
* **Zero Board Churn**: No issues are reticketed, no branch conventions are broken.

---

## 3. Scaling Patterns: 2 → 4 → 6 Seats

Do not add seats simply because you bought subscriptions. **Seats are strictly capped by separable code lanes.**

### 2-Seat Pattern (The Pair)
* **Configuration**: 1 Senior (`SR1`), 1 Junior (`JR1`).
* **Lanes**: 
  - `SR1`: `platform/`, `data/`, complex `service/`.
  - `JR1`: `interface/`, simple CRUD `service/`.
* **Review**: `SR1` reviews all `JR1` pull requests.

### 4-Seat Pattern (The Balanced Factory)
* **Configuration**: 2 Seniors (`SR1`, `SR2`), 2 Juniors (`JR1`, `JR2`).
* **Lanes**:
  - `SR1`: `platform/` + Shared Architecture.
  - `SR2`: `data/` + Core Backend Services.
  - `JR1`: `interface/` (UI/Pages).
  - `JR2`: `service/` (API endpoints, integrations).
* **Review Matrix**:
  - `SR1` ◄── reviews ──► `JR1`
  - `SR2` ◄── reviews ──► `JR2`
  - `SR1` ◄── cross-reviews ──► `SR2` (for architectural changes)

### 6-Seat Pattern (High Modularity Required)
* Only viable if the repository is split into distinct microservices, packages, or monorepo workspaces. If lanes overlap, a 6th seat produces merge locks, not throughput.

---

## 4. Review Chains & Escalation Protocol

Every pull request follows this deterministic decision tree:

```
                  ┌────────────────────────┐
                  │ PR Created by Seat JR1 │
                  └───────────┬────────────┘
                              │
                  Touches Auth, Migrations,
                     or Billing Lane?
                       /           \
                    YES             NO
                    /                 \
        ┌──────────▼─────────┐    ┌────▼────────────────┐
        │ Hard Gate:         │    │ Fast Gate:          │
        │ Escalate to SR1/SR2│    │ Run automated test  │
        │ for Full Review    │    │ suite + Peer Review │
        └────────────────────┘    └─────────────────────┘
```

---

## 5. The Golden Rule of Vendor Swapping

> [!IMPORTANT]
> **Swap vendors ONLY at ticket boundaries.**
> Never swap an AI model in the middle of a half-finished ticket. A half-completed branch holds architectural context inside the active conversation window. Swapping mid-stream forces the new agent to guess previous design choices, creating phantom bugs. Finish or reset the ticket first.

---

## 6. Measuring ROI & Parallel Velocity (The 4 KPIs)

To ensure that running 4–6 parallel seats is producing real engineering throughput rather than PR review fatigue, track these 4 core metrics:

```
┌───────────────────────────────┬───────────────────────────────┐
│ 1. Throughput Scaling Factor  │ 2. Merge Conflict Frequency   │
│ Target: > 3.2x across 4 seats │ Target: < 2% of merged PRs    │
├───────────────────────────────┼───────────────────────────────┤
│ 3. Gate First-Pass Ratio      │ 4. PR Review Cycle Time       │
│ Target: > 85% clean passes    │ Target: < 30 min per review   │
└───────────────────────────────┴───────────────────────────────┘
```

### 1. Throughput Scaling Factor
* **Formula**: $\frac{\text{Weekly Merged Tasks (4 Seats)}}{\text{Baseline 1-Developer Velocity}}$
* **Benchmark**: 
  * 4 Seats: Target **3.2x – 3.6x**. (A sub-2.5x ratio indicates lane overlap or review bottlenecks).

### 2. Merge Conflict Frequency
* **Formula**: $\frac{\text{PRs Hitting Merge Conflicts}}{\text{Total Merged PRs}} \times 100\%$
* **Benchmark**: Must remain **under 2%**. If this exceeds 5%, file paths are not cleanly partitioned in `.lane`.

### 3. Gate First-Pass Ratio
* **Formula**: $\frac{\text{PRs with Passing Gate on First Submit}}{\text{Total PRs Opened}} \times 100\%$
* **Benchmark**: Target **> 85%**. A drop below 70% indicates that a seat's capability card needs to be downgraded from `native` to `author-required`.

### 4. PR Review Cycle Time
* **Formula**: $\text{Time from PR Open} \rightarrow \text{Senior Merge}$
* **Benchmark**: Target **under 30 minutes**. Because PRs are path-isolated and carry gate declarations, senior review is a verification pass, not a line-by-line rewrite.

