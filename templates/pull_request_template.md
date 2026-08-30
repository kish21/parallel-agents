## Summary of Changes

Closes #[ISSUE_NUMBER]

### Seat & Lane Information
- **Seat**: [ ] SR1  [ ] SR2  [ ] JR1  [ ] JR2
- **Lane**: [ ] interface  [ ] service  [ ] data  [ ] platform
- **Capability Gate Executed**: [ ] Native Local Test Suite  [ ] Verified Script  [ ] Escalated to Senior

---

## Gate Declaration (Mandatory for All Seats)

Please list the exact commands and outputs from your local verification pass:

```bash
# Paste verification commands (e.g. npm test, pytest, linter)
```

- **Tests Run**: [X] Passed, [Y] Failed
- **Status**: [ ] Clean / All Passed

---

## Definition of Done Verification

- [ ] Touched only files within assigned lane
- [ ] No unmerged migrations applied to live shared database
- [ ] No hardcoded ports or secret keys
- [ ] UI controls and inputs wired to real state (no dead placeholders)
- [ ] Rebased on latest `origin/main`
