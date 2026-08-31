# Spec — Capability Gates

> **Status**: **Implemented** in v0.3.0 (phases 1–4). This document is now the design
> record; behaviour is pinned by `tests/test_capability_gates.py`.
> **Closes**: the gap between `03-orchestration.md` (capability cards, designed) and
> `src/parallel_agents/` (lanes only, implemented).

---

## 1. Why this exists

`PLAN.md` names two theses this repository was created to publish:

1. Seats are capped by non-overlapping code lanes, not by how many subscriptions you own.
2. You cannot make a weaker harness produce equal work — **so you make it declare itself.**

Thesis 1 is mechanized: `spawn` provisions isolated worktrees, branches and ports, and
`validate` enforces lane paths and fails closed on an undeclared lane.

Thesis 2 is not mechanized anywhere. It exists in three places, none of which is enforced:

| Where | What it says | Enforced? |
|---|---|---|
| `03-orchestration.md` | Full capability card schema, 3-state enum, hard-stop rule | No — prose |
| `.github/pull_request_template.md` | "Capability Gate Executed" + mandatory Gate Declaration | No — a human types it |
| `cli.py:165` | `seat = args.seat or ("SR1" if "senior" in name.lower() else "JR1")` | No — a string |

The seat is currently decorative. It is written into `.env` and `.lane`, printed by
`status`, and consulted by nothing. An agent whose card says `security_review:
unavailable` can edit auth code and open a PR that declares whatever the author types.

**This spec makes the card load-bearing.**

---

## 2. What can and cannot be mechanized

This distinction governs the whole design, so it comes first.

**Mechanically enforceable** — the tool can prove these:

* Which files a seat touched (already implemented — `LaneEngine`).
* Whether those files require a capability the seat lacks. *This is the core of the spec.*
* Whether a declared gate command was actually executed, with what exit code.

**Not mechanically enforceable** — the tool can only record and attribute these:

* Whether an agent that claims `deep_code_review: native` genuinely reviewed deeply.
* Whether a `native` capability is honestly rated.

The tool must not pretend otherwise. A capability rating is a **claim by the seat's owner**,
and the tool's job is to (a) hold the claim in one place, (b) refuse work that the claim
says the seat cannot do, and (c) make the declaration a generated artefact rather than
hand-typed prose. Rating honesty stays a human review question, exactly as
`03-orchestration.md` §4 already proposes (drop a seat from `native` to `author-required`
when its benchmark falls below 70%).

---

## 3. Data model

Reuse the card from `03-orchestration.md` verbatim — it is already well specified. Cards
live in `.parallel-agents/capabilities/<seat>.json` and are **committed**, like the lane
policy, because they are a team contract.

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

The one addition this spec requires is in `config.yaml`: a mapping from **path patterns to
the capability they require**. This is what turns a rating into an enforceable rule, and it
is the piece `03-orchestration.md` leaves implicit.

```yaml
# .parallel-agents/config.yaml
capability_gates:
  security_review:
    paths: ["**/auth/**", "**/payments/**", "**/billing/**", "**/tenant*/**"]
  database_migrations:
    paths: ["database/migrations/**", "migrations/**"]
  deep_code_review:
    paths: ["src/core/**"]
```

Read this as: *touching a path under `security_review.paths` requires the seat's
`security_review` capability to be better than `unavailable`.* It is the mechanical
expression of the rule already written in `01-working-agreement.md` — stop when the change
touches money, auth, tenant isolation, or a migration.

---

## 4. Enforcement points

Four, in the order a change moves through the system.

### 4.1 `spawn` — refuse an impossible assignment up front

`--seat` becomes a real lookup, matching how `--lane` now behaves:

* Unknown seat → reject, listing declared seats. **Fails closed**, no permissive default.
* The `"senior" in name.lower()` heuristic is deleted.
* Seat's `max_allowed_lane_scope` does not include `--lane` → reject.

Nothing is provisioned on rejection, same as the lane check.

### 4.2 `validate` — the hard stop

After lane validation passes, cross-reference the changed files against `capability_gates`:

| Seat's rating for the required capability | Result |
|---|---|
| `native` | Pass. |
| `author-required` | Pass **only if** a verified script for that capability ran and exited 0. Otherwise fail with the script that was required. |
| `unavailable` | **Hard stop.** Fail, naming the file, the capability, and the seat to escalate to. |

`forbidden_paths` on the card is a per-seat deny list evaluated with the existing
`LaneEngine` — a seat-level overlay on top of the lane-level policy, taking precedence.

This is the whole point of the feature: an agent whose harness cannot do security review
**cannot get a green validate** on a file the config marks as security-sensitive. Not a
warning. A non-zero exit.

### 4.3 `declare` — generate the gate declaration

New command: `parallel-agents declare <agent> [--markdown]`

Emits the PR template's mandatory Gate Declaration from recorded state rather than from an
author's memory: seat, harness, lane, capability ratings that applied, each quality command
with its exit code, and the capability gates triggered by the changed paths.

The PR template's `Capability Gate Executed` checkboxes get filled from this output.
Today that section is an honour-system form; this makes it a generated artefact.

### 4.4 `doctor` — card health

Adds checks for: an agent whose seat has no card; a card referencing a lane that no longer
exists; a `capability_gates` entry naming a capability no card declares (a gate that can
never be evaluated); and cards whose `max_allowed_lane_scope` collectively leaves a lane
with no eligible seat.

---

## 5. Phasing

Each phase ships and is useful alone.

| Phase | Scope | Risk |
|---|---|---|
| **1** | Card loading, `CapabilityCard` model, strict `--seat` lookup, `doctor` checks. No enforcement yet. | Low. Additive; the heuristic is replaced by an explicit lookup. |
| **2** | `capability_gates` config, `validate` enforcement, `forbidden_paths` overlay. | **Breaking.** Existing agents have no cards, so validate must skip gating when no cards are declared at all — see §7. |
| **3** | `declare`, PR template integration. | Low. New command. |
| **4** | `author-required` script registry and execution proof. | Medium. Needs a convention for where verified scripts live and how their execution is recorded. |

---

## 6. Testing requirements

Mirroring the fail-closed suite added in v0.2.0, since this is the same class of guarantee:

* An `unavailable` capability on a gated path fails `validate` with a non-zero exit — the
  central test, and it should assert the exact exit code the CI gate depends on.
* An unknown seat is rejected at spawn, provisioning nothing.
* A card whose `max_allowed_lane_scope` excludes the requested lane is rejected.
* `forbidden_paths` takes precedence over a lane's `allow`.
* A gated path with **no** matching capability gate is not accidentally blocked.
* A capability gate naming a capability absent from a card fails closed, not open —
  the v0.2.0 lesson: an unrecognised key must never mean "permitted".

---

## 7. Decisions taken

These were open when the spec was drafted. Each was resolved as follows; reopen any of
them by changing the code and the tests that pin it.

1. **Gating with no cards present** — resolved without a fail-open default. Gating applies
   only where `capability_gates` are configured; if none are, there is nothing to enforce.
   Once gates *are* configured, a seat without a card fails closed. `init` writes both, so
   a new repository is gated from the first spawn and the two can never drift apart.
2. **Where cards live** — `.parallel-agents/capabilities/<seat>.json`, one file per seat,
   so loosening a single seat is a visible one-file diff in review.
3. **Whether this belongs here** — implemented here, because the README already implied
   the CLI enforced it. Nothing in the implementation is repo-specific; if the phase-skills
   repo should own the model, `capabilities.py` moves wholesale and this repo imports it.
4. **`author-required` proof** — carried by the existing quality-command mechanism rather
   than a new registry. A command may declare `satisfies: <capability>`; the gate passes
   only if every command satisfying it ran and exited 0.

## 8. Original open questions (historical)

1. **Gating with no cards present.** Phase 2 breaks every existing repo unless validate
   skips gating when no cards exist at all. That is a fail-*open* default, which cuts
   against the v0.2.0 direction. Options: (a) skip when the `capabilities/` directory is
   absent, warn loudly; (b) require `capability_gates: {}` to be explicit; (c) make
   `init` write default cards for SR1/SR2/JR1/JR2. I lean (c) — it keeps everything
   fail-closed and makes the feature visible on day one.

2. **Where cards live.** This spec says `.parallel-agents/capabilities/<seat>.json`.
   `03-orchestration.md` suggests repository root as `capabilities.json` or
   `.lane.capabilities`. One file per seat is easier to review in a PR diff; a single
   file is easier to read whole. Your call.

3. **Whether this belongs here at all.** `PLAN.md` §"Open decisions" records:
   *"Whether the capability-map spec lives here or in the author's separate phase-skills
   repo. Current thinking: the phase-skills repo owns it."* That decision was never
   resolved. If it still stands, this spec should be a reference to that repo instead —
   but then thesis 2 stays permanently unmechanized *here*, and this repo's README should
   stop implying otherwise.

4. **`author-required` proof.** Phase 4 needs a convention for verified scripts. Simplest
   workable version: `quality.commands` entries tagged with the capability they satisfy,
   so an existing mechanism carries the new meaning rather than adding a registry.

---

## 8. What this does not do

* It does not verify that a `native` rating is honest.
* It does not stop a human from editing a card to unblock themselves. Cards are committed
  and diffable specifically so that loosening one is visible in review — the same posture
  as the lane policy.
* It does not replace human review. It makes the *scope* of required human review explicit
  and mechanically enforced.
