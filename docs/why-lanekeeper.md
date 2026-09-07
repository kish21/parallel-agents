# Why lanekeeper, and how it works, as a story

**Read this if you want to understand what problem lanekeeper solves before you read
what to type.** It is written as the story of one small team, because the problem only
makes sense as something that happens to people. The commands come at the end, once
you know why each one exists.

---

## 1. The problem: three agents, one Tuesday

Priya runs a small product with two other people and, lately, three coding agents.
Agents are cheap and fast, so on Tuesday morning she hands out three tickets at once:

- **#2** — add semantic clustering to the issue list
- **#3** — add status transitions and an export panel
- **#4** — make the header sticky

Each agent gets its own copy of the repository and its own branch. By lunchtime all
three report done. All three test suites pass. Priya opens three pull requests.

Then the merge starts.

The clustering agent needed a new field on the issue type, so it edited
`src/domain/contracts.ts`. The export agent needed a different field on the same type,
so it edited `src/domain/contracts.ts` too. Git merges the first one cleanly. The second
one conflicts. Priya resolves it by hand, and now the clustering feature is broken,
because the export agent also "tidied up" a helper the clustering code relied on. The
header agent, meanwhile, decided the layout file was messy and rewrote it, which moved
the export panel off the screen.

Nothing was wrong with any agent. Each did exactly what it was asked, inside its own
copy. **The copies were isolated. The intentions were not.** Three agents each believed
they owned the whole repository, because nothing told them otherwise, and nothing could
have stopped them if it had.

Priya spent Tuesday afternoon un-merging Tuesday morning.

## 2. What would have to be true for that not to happen

Look at what actually went wrong. It was not that agents ran in parallel. It was that:

1. **Nobody said, in writing, which files each ticket was allowed to touch.** The
   boundary lived in Priya's head.
2. **Nothing checked a change against that boundary before it merged.** The test suite
   checks whether code works, not whether it was the agent's to write.
3. **The one file two tickets genuinely both needed was not treated as special.** It was
   just another file, so both agents edited it and both were "right".

So the fix is not a smarter agent. It is three plain, mechanical things:

- a written boundary per piece of work,
- a check that fails a change which steps outside its boundary, run where merging
  happens,
- and a way to mark the shared file as belonging to nobody, so a change to it is a
  decision rather than an accident.

That is the whole of lanekeeper. Everything else is convenience around those three.

## 3. What lanekeeper is

**Lanekeeper keeps parallel coding agents in their lanes.** A lane is a list of file
paths one piece of work may touch. Lanekeeper writes the lanes down, gives each agent a
separate checkout on its own branch with its own ports, and puts a gate on every pull
request that fails a change touching a file outside its lane.

It does not write code. It does not decide what a product should do. It does not judge
whether a change is good. It answers one question, mechanically, every time: **did this
change stay inside the files it was allowed to touch?**

Five words carry the whole model:

| Word | Meaning | Where it lives |
| :--- | :--- | :--- |
| **Lane** | The files one piece of work may touch. A feature slice, not a technology layer: `checkout`, not `backend`. | `lanes:` in the policy |
| **Policy** | The file that lists every lane. It is the contract, so it is committed, and no lane may edit it. | `.lanekeeper/config.yaml` |
| **Agent** | One worker on one ticket: a worktree, a branch, a port range, and a lane. | `.lanekeeper/worktrees/agent-001` |
| **Gate** | The check that fails a change outside its lane. Runs locally on request and on every pull request in CI. | `lanekeeper check`, and the workflow `install-gate` writes |
| **Shared zone** | A lane nobody is spawned into. A change to a file in it is escalated to a person, from any lane. | a lane with `shared: true` |

## 4. Tuesday again, with lanekeeper

Same team, same three tickets. This time each ticket's body names its files, because
the issue form asks for them. Priya types one command per ticket.

```
lanekeeper spawn --ticket 2
```

Lanekeeper reads ticket #2, takes the six files it names, writes them into the policy
as lane `feat-02`, creates a worktree on branch `parallel/agent-001/2-feat-02-…`,
reserves ports 8001 and 3001 for it, and prints the prompt to give the agent: the task,
the file list, and the instruction to stop and say so if it needs a file that is not on
the list.

```
lanekeeper spawn --ticket 3
```

This time lanekeeper stops before writing anything:

```
⚠️  Another lane could touch the same files. Both lanes allow them, so both
    agents' changes pass their own checks — and meet at merge.
      'feat-02' claims src/domain/contracts.ts, this ticket claims src/domain/contracts.ts

    The designed answer is a shared zone: 'shared: true' on a lane nobody is
    spawned into, checked before either lane's own list …
   Proceed anyway [p], write the shared zone and proceed [s], or stop [n]?
```

This is Tuesday afternoon's conflict, found on Tuesday morning, before either agent has
typed a line. Priya answers `s`. The contracts file now belongs to a shared zone. Either
agent that touches it will be told to raise the change rather than make it, and Priya
will decide the shape of that type once, by hand, for both.

```
lanekeeper spawn --ticket 4
```

Ticket #4 is one sentence and names no files. Lanekeeper will not guess a boundary. On
a terminal with Claude Code available it asks the model which files the ticket probably
touches, shows the answer, and uses it only if Priya says yes. She does.

Three agents, three lanes, one shared file settled. Now the work happens, and here is
the difference from before: when the header agent decides to rewrite the layout file,
`lanekeeper check` says

```
  ✗ src/App.tsx: outside lane 'issue-4'.
      If this file belongs in this lane: lanekeeper allow --lane issue-4 src/App.tsx
```

The agent overreached, and the tool says so before the pull request exists. Priya
reverts that file. If instead the ticket had simply forgotten a file the work genuinely
needs, she runs the `allow` command it offers, and the boundary widens by one deliberate
decision, recorded in the policy.

The three pull requests open with `lanekeeper pr agent-001` and so on: each is checked,
pushed, and labelled with its lane. The gate in CI runs the same check on each. All three
are green, and green now means something: **each change touched only the files its
ticket was allowed to.** Priya merges them in the order she likes. There is nothing to
un-merge.

## 5. The gate and the policy, precisely

Because these two words carry the guarantee, here is exactly what they are.

**The policy** is `.lanekeeper/config.yaml`. Its important section is `lanes:`, a list of
lane names each with `allow:` patterns (and optionally `deny:` carve-outs). It is written
by `spawn --ticket` the first time, and then only ever changed by a person: by hand, or
by `lanekeeper allow`, which refuses to widen one lane into another's territory. It is
committed to the repository, on its own, in a pull request labelled `lane: policy`,
because CI can only enforce a policy that is in the repository. No ordinary lane may
touch it: an agent that edits the policy inside its own pull request is refused, so an
agent cannot widen its own boundary.

**The gate** is `lanekeeper check`. Given a lane name and a base branch, it lists every
file the change touches and asks, for each one: is this file inside the lane's `allow`
patterns and outside its `deny` patterns, and is it not in a shared zone, and is it not
a policy file? One file failing fails the change. It has no opinions and no exceptions;
the same file gives the same answer every time.

The gate runs in three places:

- **By hand**, from inside an agent's worktree, whenever you like.
- **Before every push** from an agent's branch, if you install the pre-push hook.
- **On every pull request**, as a GitHub Action `install-gate` writes. The lane comes
  from the pull request's `lane: <name>` label, or from the branch name lanekeeper made
  when there is no label. A missing lane fails closed: a change with no declared
  boundary has no boundary.

**The gate is never wrong about the question it is asked.** Every problem found in
testing was about what the tool said around the verdict, never the verdict. The check is
a set intersection over file paths; it does not consult a model.

## 6. What you need before you start

- **Python 3.9 or later**, and `pip install lanekeeper`. On a Microsoft Store Python
  the `lanekeeper` command may not be on your PATH; `python -m lanekeeper` is the same
  program.
- **Git**, and a repository with a remote. Lanekeeper uses git worktrees and branches,
  and looks at the remote before making a branch.
- **A ticket tracker lanekeeper can read.** GitHub Issues, through the `gh` command,
  signed in. Without one, `lanekeeper init` reads lanes from your directory layout
  instead; that path is cruder.
- **Tickets that name their files.** This is the one real prerequisite, and the one
  that decides whether lanekeeper is cheap or annoying for you. The repository ships an
  issue form (`templates/issue-template-task.yml`) whose required field is *Allowed File
  Paths*. A ticket that names no files can still be handed out with `--allow`, or with a
  proposed list you confirm, but every one of those is a small tax.
- **A coding agent**, any one: Claude Code, Cursor, a person. Lanekeeper prepares the
  desk and hands over the prompt; it does not care who sits down.
- **Optional:** VS Code or another editor for `lanekeeper open`; Claude Code on your
  PATH for proposals; branch protection on GitHub if you want the gate to block merges
  rather than only report.

## 7. The steps, in order

Once per repository:

1. `pip install --upgrade lanekeeper`
2. Make sure your tickets name their files.
3. `lanekeeper spawn --ticket <n>` for the first ticket. This writes the policy. On a
   terminal it offers to install the gate; say yes.
4. Commit the policy and the gate workflow, in your main checkout, as a pull request
   labelled `lane: policy`.
5. Optionally `lanekeeper install-gate --hooks`, so every push from an agent's branch
   runs the check first.

Per ticket, after that:

1. `lanekeeper spawn --ticket <n>` — the worktree, the branch, the ports, the lane. If
   another lane claims some of the same files, answer the question it asks.
2. `lanekeeper work agent-00N -- claude` — start the agent in its worktree with its
   prompt. (Install the dependencies in the worktree once; `spawn` names the command.)
3. `lanekeeper check --lane <lane> --base main --working-tree` from the worktree,
   whenever you want to know. If the gate blocks a file the ticket forgot,
   `lanekeeper allow` records the decision.
4. `lanekeeper pr agent-00N` — check, push, and open the labelled pull request.
5. Merge when green. `lanekeeper cleanup agent-00N` removes the worktree and releases
   the ports; the branch is deleted only if it is merged into the base.

At any point, `lanekeeper next` reads the state of the repository and says which of
these is the one thing to do now.

## 8. What it will not do

- It will not stop an agent *typing* outside its lane. It stops the change *merging*.
  Reading is unrestricted.
- It will not tell two agents in one lane apart. Both are inside the boundary, so both
  pass. `spawn` refuses the second agent for that reason.
- It will not invent a boundary. A ticket that names no files is refused, or proposed
  and confirmed, never guessed.
- It will not judge whether an overlap is a dependency or a collision. It reports the
  overlap and asks. The shared zone is the answer a person gives.
- It will not write or assign the work. That is the ticket tracker's job, and the job of
  whoever writes the tickets.

The full command reference is in the [README](../README.md); every command with real
output is in [Getting started](getting-started.md).
