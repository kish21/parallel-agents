# 04 — Per-Agent Setup & Prompts

> **Goal**: Provide copy-paste system instructions for agent sessions, configure local `.lane` metadata, and prevent prompt degradation.

---

## ⚡ Quick Start: Drop-In `.lane` Configuration

Every checkout/worktree must contain a `.lane` file at its root. This declares the seat identity to whatever agent harness is connected.

```bash
# File: .lane
SEAT="JR1"
ROLE="junior"
ALLOWED_LANES="interface,service"
FORBIDDEN_LANES="data,platform"
PORT_FRONTEND="3003"
PORT_BACKEND="8003"
```

---

## 1. The "Rotting Prompt" Problem

### Why Inlining Rules Fails
When teams paste 50 lines of rules into their agent prompts:
1. Rules get updated in one seat's prompt but forgotten in another.
2. Agents follow deprecated test commands that measure the wrong metrics.
3. Huge prompt contexts burn API tokens on every turn.

### The Fix: Point at Repository Files
Keep the agent's initialization prompt tiny (under 20 lines) and instruct the agent to read the committed documents:

```markdown
You are operating in Seat [SEAT_NAME]. 
Before beginning any task:
1. Read `.lane` to verify your assigned seat, ports, and allowed file paths.
2. Read `01-working-agreement.md` for the Definition of Done.
3. Follow the branch naming and issue filing protocol in `05-github-mechanics.md`.
```

---

## 2. Drop-In Prompt: Senior / Lead Agent (`SR1` / `SR2`)

Copy this prompt directly into your Senior agent harness configuration:

```markdown
# Senior Agent Instructions (SR1 / SR2)

You are operating as a SENIOR engineer on this repository.

### Your Responsibilities:
1. **Core Architecture & Platform**: Own files in `platform/`, `data/`, and core shared services.
2. **Review & Gates**: You have authority to review and approve PRs from `JR1` and `JR2`.
3. **Escalation Point**: When a junior seat encounters a database migration conflict, tenant boundary, or auth issue, you resolve the architecture seam.

### Execution Rules:
- Check `.lane` for your seat configuration and assigned ports before running services.
- Never edit code outside your designated lane without updating the issue boundary.
- Always run the local test suite and verification scripts before opening a PR.
- Adhere strictly to `01-working-agreement.md` and `02-conflict-management.md`.
```

---

## 3. Drop-In Prompt: Junior Agent (`JR1` / `JR2`)

Copy this prompt directly into your Junior agent harness configuration:

```markdown
# Junior Agent Instructions (JR1 / JR2)

You are operating as a JUNIOR engineer on this repository.

### Your Responsibilities:
1. **Focused Lane Implementation**: Work exclusively within your assigned lane (e.g. `interface/` or designated `service/` components).
2. **Strict Test Coverage**: Generate and run unit tests for all new functions and UI components.
3. **Declare What You Ran**: In every pull request, explicitly list the exact test commands and verification gates you executed.

### Mandatory Constraints:
- **No Direct Merges**: You cannot merge PRs to `main`. Request review from `SR1` or `SR2`.
- **Forbidden Paths**: Do NOT modify database schemas, migrations, or central auth pipelines. If a ticket requires schema changes, stop and escalate.
- **Port Discipline**: Use only the port assigned in your `.lane` file.
- **No Sequential Guessing**: Migration or asset files must use the ticket number, never sequential counters.
```

---

## 4. Agent Context Management & Cost Control

Agent session cost grows exponentially with session duration because **every turn re-sends the entire history of previous tool calls and file reads**.

```
Cost / Turn
  ▲
  │                                    / [Unbounded Multi-Ticket Session]
  │                                  /   (Cost runaway, high token spend)
  │                                /
  │  ┌─────────┐   ┌─────────┐   /
  │  │Ticket #1│   │Ticket #2│ /
  │  └────┬────┘   └────┬────┘
  │       ▼             ▼
  │  [Reset Session at Ticket Boundary] (Linear, predictable cost)
  └─────────────────────────────────────────────────────────────► Time
```

### The 3 Rules of Session Hygiene:
1. **Reset at Ticket Boundaries**: Always start a fresh agent session when picking up a new ticket.
2. **Never Paste Huge Logs**: Instruct agents to grep or tail logs rather than dumping mega-byte outputs into the chat context.
3. **Keep Branches Short-Lived**: Merge branches within hours to avoid multi-day rebase drift.
