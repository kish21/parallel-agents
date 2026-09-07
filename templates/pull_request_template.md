## Summary of Changes

Closes #[ISSUE_NUMBER]

**Lane:** `<name>` — the same name as this pull request's `lane: <name>` label. The gate
reads exactly one such label and fails closed without it. A lane is a feature slice
(`checkout`, `search`), never a technology layer. Use `policy` for a change to the lane
policy itself (`.lanekeeper/config.yaml`, the seat cards, the gate workflow).

---

## Gate Declaration

Paste the output of the boundary check, run against the branch this merges into:

```bash
$ lanekeeper check --lane <name> --base origin/main --working-tree
# paste the output here — including the ✅ CHECK PASSED / ❌ CHECK FAILED line
```

An agent spawned by lanekeeper can generate this section instead with
`lanekeeper declare <agent>`, which derives the seat, lane and capability gates from
recorded state rather than from memory.

---

## Definition of Done

- [ ] Touched only files inside the lane (the check above passed)
- [ ] No hardcoded ports or secret keys — ports and keys come from the agent's `.env`
- [ ] No unmerged migrations applied to a live shared database
- [ ] Rebased on the latest base branch
