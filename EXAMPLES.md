# End-to-End Walkthrough: Lifecycle of Ticket #102 🎬

> **Goal**: Trace a realistic ticket from assignment to merge across the 4-seat parallel architecture. See how boundaries, `.lane` files, port isolation, and gate declarations work together in practice.

---

## 📋 Ticket Overview: Issue #102

```markdown
Title: [Service] Add billing webhook handler for subscription renewals
Number: 102
Lane: service
Seat: JR1
Owner: junior
Status: Ready
```

---

## 🧭 The 5-Phase Lifecycle

```
Phase 1: Assignment     Phase 2: Setup         Phase 3: Dev & Test    Phase 4: PR Gate      Phase 5: Senior Merge
┌──────────────────┐   ┌───────────────────┐   ┌──────────────────┐   ┌─────────────────┐   ┌──────────────────┐
│ GitHub Board:    │   │ worktrees/jr1     │   │ Write service &  │   │ Open PR #105    │   │ Seat SR1 reviews │
│ Stamped to JR1   ├──►│ Reads .lane       ├──►│ tests; run tests ├──►│ Declares test   ├──►│ & merges to main │
│ in Service lane  │   │ Branch: feat/102  │   │ on port 8003     │   │ gate output     │   │ within 15 mins   │
└──────────────────┘   └───────────────────┘   └──────────────────┘   └─────────────────┘   └──────────────────┘
```

---

### Phase 1: Ticket Assignment & Boundary Check

1. The Tech Lead or human filer creates **Issue #102** using the task issue form:
   * **Lane**: `service`
   * **Allowed Paths**: `backend/app/services/billing/`, `backend/tests/services/billing/`
   * **Forbidden Paths**: `frontend/`, `database/migrations/`
   * **Seat**: Stamped to `JR1` on the Delivery Board.

---

### Phase 2: Agent Initialization in `worktrees/jr1`

The Junior Agent session in `worktrees/jr1` initializes and reads its local environment:

1. **Checks `.lane`**:
   ```bash
   $ cat .lane
   SEAT="JR1"
   ROLE="junior"
   ALLOWED_LANES="interface,service"
   PORT_BACKEND="8003"
   ```
2. **Creates Feature Branch**:
   ```bash
   git checkout -b feat/102-billing-webhook origin/main
   ```

---

### Phase 3: Implementation & Local Test Execution

1. The agent writes the webhook verification logic in `backend/app/services/billing/webhook.py`.
2. The agent writes unit and integration tests in `backend/tests/services/billing/test_webhook.py`.
3. The agent runs the local test suite on its assigned port:
   ```bash
   $ pytest backend/tests/services/billing/ -q
   ...... [100%]
   6 passed in 0.42s
   ```

---

### Phase 4: Opening the Pull Request with Gate Declaration

The agent pushes the branch and creates a pull request using the project template:

```markdown
## Summary of Changes
Closes #102. Adds HMAC signature verification for billing renewal webhooks.

### Seat & Lane Information
- **Seat**: [x] JR1
- **Lane**: [x] service
- **Capability Gate Executed**: [x] Native Local Test Suite

---

## Gate Declaration (Mandatory)
```bash
$ pytest backend/tests/services/billing/ -v
test_valid_signature PASSED
test_expired_timestamp PASSED
test_missing_secret PASSED
3 passed in 0.18s
```
- **Tests Run**: 3 Passed, 0 Failed
- **Status**: [x] Clean / All Passed

---

## Definition of Done Verification
- [x] Touched only files within `backend/app/services/billing/`
- [x] No unmerged migrations applied to shared live database
- [x] No hardcoded ports or secret keys
- [x] Rebased on latest `origin/main`
```

---

### Phase 5: Senior Review (`SR1`) & Merge

1. **`SR1` Reviewer checks the PR diff**:
   * Confirms changes are strictly within the `service` lane.
   * Confirms the gate declaration output matches the test suite.
   * Approves the PR.
2. **Merge & Board Update**:
   * PR merges via squash-and-merge into `main`.
   * GitHub closing keyword automatically moves Issue #102 to **Done**.
   * `JR1` is immediately free to pick up the next ticket in its lane.
