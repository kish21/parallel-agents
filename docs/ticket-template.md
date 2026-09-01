# The ticket template: the input contract for dividing work

Issue: #23 (a lane is a feature slice, not a technology layer) · Unblocks #38 ·
Prerequisite for the umbrella #36

## 1. The decision this builds to

**A lane is a feature slice, not a tech layer.** `checkout` — its service, its schema,
its API route, its React page and its tests — not `backend`. The README argues this at
length under §Lanes, `examples/feature-lanes.yaml` is a 17-lane worked example of it,
and #23 is the open issue tracking everywhere the tool still teaches otherwise.

The ticket template is one of those places, and it is the most consequential one,
because it is not documentation the user may or may not read. It is a **form they have
to fill in**, and whatever it asks for is what lands in the backlog that every later
step divides.

Settled last session, and the reason this comes before #38:

> The prerequisite for `lanekeeper start` is **not** a `PRODUCT.md`. It is that tickets
> are filed through a template that asks for the files they touch. A properly filed
> ticket already names its own boundary — it carries its own answer, and nothing needs
> comparing against a spec to find it.

Step 2 (#38) is handed those tickets and proposes how they group. Its input is only ever
as good as this form. Fixing the form is small; building #38 on a form that teaches
layers would mean building the thing that has to argue with its own input.

## 2. What is actually wrong

Six files, not two. `.github/ISSUE_TEMPLATE/{task,bug}.yml` are this repository's own;
`templates/issue-template-{task,bug}.yml` are the copies **shipped to users**, which is
the pair that teaches the world. Two more documents teach the same enum in prose and
were found by review, not by looking for templates: `CONTRIBUTING.md`, read *before* a
filer reaches the form, and `05-github-mechanics.md`, which instructs users to build the
Lane dropdown this change deletes.

**a. `Lane` is a dropdown of technology layers.** Both templates offer
`interface / service / data / platform / docs-framework / shared`. Every one of those is
a layer. This is the exact model #23 rejects and the README spends a section arguing
against, presented to the user as the only available answer.

**b. The dropdown cannot be fixed by editing its options.** Feature-slice lane names are
project-specific — `checkout`, `search`, `billing`, `voiceover`. No fixed enum in a
shipped template can know them. A dropdown is structurally committed to the layer model,
because layers are the only lane names that generalise across projects. The field has to
become free text.

**c. `Lane` is required and `Allowed File Paths` is the field that should be.** A
required `Lane` asks the filer to guess the grouping *before* step 2 has proposed one,
and a guessed lane name is worse input than a blank one — #38 must then argue with it.
The paths are what the filer actually knows, and they are the boundary the merge gate
enforces.

**d. `bug.yml` asks for a Lane but never for file paths.** Under the settled design a
lane may be a **single ticket**, bounded by that ticket's own Allowed File Paths, and a
bug report is exactly the kind of ticket most likely to be picked that way. Filed
through this form it arrives with nothing to enforce: no boundary means no gate, so
handing it to an agent ships a safety guarantee that quietly does not exist.

**e. The two copies have already drifted.** The repository's own templates added
`docs/framework` to the Lane list; the shipped copies kept path placeholders the
repository's have since dropped, and word their headings differently. Nothing in code or
CI copies one to the other, so they drift silently and neither is authoritative.

**f. The format of `Allowed File Paths` is unstated.** It is a free textarea with no
statement of what a line means. #38 has to parse it. Unstated format means #38 guesses.

**g. The prose documents carry the enum too.** `CONTRIBUTING.md` tells contributors to
"include the target **Lane** (`interface`, `service`, `data`, `platform`)" — the deleted
list, in the document read before the form. `05-github-mechanics.md` goes further and
tells the reader to *add* Lane and Owner dropdowns. Fixing only the YAML would leave the
instructions telling people to put it back.

## 3. Scope of this session

**In scope**

- `Lane` becomes a free-text input teaching feature-not-layer, and becomes **optional**,
  with an explicit "leave it blank and lanekeeper will propose one" escape.
- `Allowed File Paths` becomes the **required** field, in `task.yml` **and** `bug.yml`.
- The format of `Allowed File Paths` is stated on the form: one path or glob per line.
- All four copies reconciled, and a test that keeps them reconciled.
- `CONTRIBUTING.md` and `05-github-mechanics.md` stop teaching the layer enum, and the
  latter stops telling readers to build the dropdown.

**Explicitly out of scope**

- Any `src/` change. `cli._has_issue_template` only tests for existence and is
  unaffected; nothing parses these fields yet. **#38 is the first reader**, and it is a
  separate session.
- Changing `Owner: junior / senior`. Verified against the lane file schema: `owner` there
  is documented as "a ROLE this lane needs, not a seat number" (README:343, and
  `examples/feature-lanes.yaml` uses `owner: senior`). It is consistent, and it is not
  the layer bug.
- `layout.py`'s `ROLE_BY_DIR_NAME`, the other half of #23. That is auto-detection, it is
  #38's to displace as the default, and it is a code change with real blast radius.
- Renaming or restructuring anyone's repository. Lanes are globs and carve a feature
  slice out of a messy tree without moving a file.

## 4. Module-interaction map

Nothing here is code, so the boundaries are between documents and their readers. Stating
them is the point: this file is a contract with a step that is not written yet.

```
  .github/ISSUE_TEMPLATE/task.yml     templates/issue-template-task.yml
  .github/ISSUE_TEMPLATE/bug.yml      templates/issue-template-bug.yml
  (this repository's own)             (shipped; copied by hand into user projects)
             |                                      |
             +---------------- same fields ---------+
                              |
                    guarded by tests/test_issue_template.py
                              |
                              v
                   a filed GitHub issue body
                              |
      cli._has_issue_template |  (existence only - does not parse)
                              |
                              v
              trackers.GitHubIssuesTracker.list_issues()
                              |  Issue.body, verbatim
                              v
                    intake.quality  (#37, shipped)
                      reads for a file hint -> FlagKind.NO_FILE_HINT
                              |
                              v
                   IntakeResult ----> step 2 (#38, not built)
                      parses "Allowed File Paths" as the ticket's boundary
```

**The contract #38 may rely on, and the whole reason this file exists:**

| Field | Label on the form | Required | Meaning |
|---|---|---|---|
| `lane` | Lane (which feature this belongs to) | no | A feature name, free text. Blank means "propose one". Never a layer. |
| `allowed_paths` | Allowed File Paths | **yes** | **One path or glob per line.** The ticket's boundary. |
| `owner` | Seniority Level Required | yes | A role the work needs, matching the lane file's `owner`. |

A blank `lane` is an ordinary, expected input — not a defect for #38 to flag.

## 5. Test plan

The templates are data, so the tests are guards on that data, in the pattern of
`tests/test_intake_language.py` — which guards user-facing strings the same way.

`tests/test_issue_template.py`, `unittest` classes under pytest, no network, no `gh`:

**Unit — the shape of each file**

- Every one of the four files is valid YAML and a valid GitHub issue form (`name`,
  `description`, `body`; every element has a `type`).
- `allowed_paths` exists in **all four** and is `required: true` in all four. This is the
  regression that matters: it is the field whose absence removes the merge gate.
- The `lane` field is `type: input`, not `type: dropdown`, and carries no `options`.
- `lane` is not `required`.

**Unit — the layer model does not come back**

- No `lane` field in any of the four offers, defaults to, or gives as its placeholder any
  of `interface`, `service`, `data`, `platform`, `backend`, `frontend`, `infra`. Asserted
  against a named list so re-introducing the dropdown fails loudly, which is the whole
  point of the guard.
- Each `lane` field's description states the feature-slice rule.

**Integration — the copies agree**

- The shipped and repository copies of each template declare the **same field ids, with
  the same `required` flags**. Prose may differ (the shipped ones are generic examples);
  the contract may not. This is the drift that already happened once.

**Integration — the live path still works**

- `cli._has_issue_template` still returns `True` for this repository after the edits.
- The full existing suite still passes: nothing reads these fields yet, so any failure
  here is a genuine surprise and worth surfacing.

**Run the real command**

- `lanekeeper intake` executed against this actual repository, whose backlog is filed
  through the very template being changed. Green tests on a fake tracker are not evidence
  — last session 104 of them missed both cases the ticket was written for, because the
  double returned a state the real tracker never produces.
- A ticket filed through the edited form, rendered by GitHub, to confirm the form is
  accepted and the fields land in the issue body in the shape §4 promises #38.

## 6. Exit criteria

Testable, and not done until each is verified:

1. No `Lane` field in any of the four templates offers a technology layer as a choice,
   whether as an option, a pre-filled `value`, or a placeholder.
2. `Lane` is free text and optional in all four; the form says a blank one is fine.
3. `Allowed File Paths` is present and required in all four, including `bug.yml`.
4. The form states that the field is one path or glob per line.
5. The shipped and repository copies declare identical field ids and required flags.
   Neither shows an `Allowed File Paths` example confined to a single top-level directory
   -- an example is the strongest teaching in a form and must not contradict its prose.
6. `tests/test_issue_template.py` passes and **fails** when the dropdown is restored —
   verified by restoring it, not by assuming.
7. The existing suite passes unchanged.
8. `lanekeeper intake` runs green against this repository.
9. All four forms are valid GitHub issue-form syntax.
10. No document in the repository still teaches the layer enum or the dropdown.
11. No form promises a behaviour that is not implemented.

## 7. What this deliberately does not solve

The form can ask for feature-slice paths; it cannot make anyone write them well. Someone
will still type `backend/` into Allowed File Paths and `backend` into Lane. That is
#38's problem and it is the right place for it: #38 sees the whole backlog at once, so it
can notice that every ticket claims the same root and say so. A form sees one ticket and
cannot.

`layout.py` still detects `backend / frontend / data / platform` and proposes it as the
default. That is the other half of #23 and the larger half. This change means the
**tickets** stop teaching layers; #38 is where the **detection** stops.

**A threshold worth revisiting in #38, found while reviewing this.** `intake.quality`
flags a ticket as `BROAD_TICKET` when it touches more than `broad_ticket_areas`
top-level directories, which defaults to **3**. A correctly written feature slice spans
`backend` + `frontend` + `tests` — exactly 3. So the default sits precisely on the
boundary of the model the form now teaches: today's placeholders do not trip it
(measured), but one more line does. The threshold was set when a ticket was expected to
stay inside one layer. It is config, not a constant, so nothing is broken; #38 should
decide what it ought to be now that a lane spans the stack by design.

**A promise removed rather than kept.** An earlier draft of `bug.yml` told the filer that
if they could not name the paths, saying so "will be asked about before anyone is handed
the work". Nothing does that, and worse, `quality._file_hints` scans the whole issue body,
so a stack trace in the Evidence field supplies a path and the ticket raises no flag at
all. A form must not promise a safety behaviour that does not exist — that is the same
defect class this change was opened to fix — so the sentence was cut. Asking for missing
paths is #38's, per its rewritten definition of done.
