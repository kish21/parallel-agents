# `lanekeeper codeowners` — the lanes, as the file GitHub already enforces

Design note for [#42](https://github.com/kish21/parallel-agents/issues/42). Written
alongside the code, not after it, so the three decisions that are easy to get silently
wrong are on the record.

## What it is for

The lane file says which paths belong to whom. GitHub has a native file that says the
same thing and already enforces it, in every repository, with nothing installed: once
*Require review from Code Owners* is on in branch protection, a pull request touching
an owned path needs that owner's approval.

So this command emits one from the other. The value is not enforcement — the gate
already does that, earlier and better — it is that **the lanes become legible to people
and tools that have never heard of lanekeeper.** A reviewer who has never installed it
still sees the right name on the right file.

## What it does not replace

| | `CODEOWNERS` | `lanekeeper check` |
|---|---|---|
| Question | Who must approve this file? | Should this branch have touched it at all? |
| When | After the work is done | Before the work starts |
| Who can act on it | A human reviewer | **The agent itself** |

With one maintainer and several agents, every path's code owner is the same person, so
`CODEOWNERS` alone just renames the bottleneck. Both are worth having; neither is the
other.

## The three decisions

### 1. The source is `config.yaml`, not `lanes.yaml`

The issue says "from the lane file (#34)". Nothing reads `lanes.yaml` — the gate reads
`.lanekeeper/config.yaml`, and `divide --confirm` writes the confirmed lanes there.
Generating a routing file from a document nothing enforces would drift from the boundary
it claims to describe, which is worse than having no routing file. So the source is the
file the gate reads, and the generated header says which file that was.

### 2. Last match wins, so the order is this tool's own precedence, backwards

In the lane engine, `deny` beats `allow` and a shared zone beats both. In `CODEOWNERS`
the **last** matching pattern wins. The emission order is therefore inverted on purpose:

```
feature lanes  →  shared zones  →  the policy files
```

Get it the other way round and a feature lane whose `allow` happens to cover the shared
store silently takes the shared zone's ownership — the exact failure the zone exists to
prevent, in the file meant to advertise it.

Hand-written rules **below** the managed block also win, for anything they match. That
is legitimate and easy to do by accident, so the command counts them and says so.

### 3. Anchoring, and the patterns that cannot be translated

A lane pattern is matched against a path from the repository root. An unanchored
`CODEOWNERS` pattern matches at *every* level. So `src/*.ts` — two files in `src/` to a
lane — would also claim `vendor/other/src/x.ts` and route somebody else's review here.
Every pattern is therefore anchored with a leading `/`, except one already anchored and
one deliberately written `**/…`, which means "at any level" in both systems.

`CODEOWNERS` has no `!` negation, no `[a-z]` ranges, no `?`, and no way to write a
path containing a space — every line is split on whitespace, so `My Docs/** @a` parses
as the pattern `/My` owned by `Docs/**` and `@a`. Those patterns are
**not written**, and the file itself says which and why on a comment line beside the
lane they came from. A lane's `deny` list has no representation at all: it is noted in
the file rather than approximated, because an approximation of a carve-out is a wrong
owner.

## Owners

`CODEOWNERS` routes to people, and the gate has never needed to know who a person is.
So ownership is one new optional field and one new setting:

```yaml
lanes:
  - name: checkout
    owner: "@kish21"          # or a list: ["@kish21", "@org/reviewers"]
    allow: [...]

codeowners:
  path: .github/CODEOWNERS
  default_owner: "@kish21"    # what a lane without its own owner gets
```

`--owner @handle` overrides the default for one run. A lane nobody owns produces **no
rule** — an owner-less line is a syntax error, and inventing an owner would route
reviews to somebody who never agreed to them.

Owners are validated as GitHub would read them (`@user`, `@org/team`, or an email),
because a handle written without its `@` is not an error GitHub reports: the line is
ignored, the routing quietly does not happen, and the command that wrote it said it
succeeded.

**The policy files are routed last, whenever anyone owns them.** Without that rule a
lane pattern as ordinary as `**/*.yaml` becomes the code owner of the file that defines
every lane. With no default owner and no policy owner there is nobody to route them to,
so the command says so rather than leaving it to be discovered.

## The size limit

Above 3 MB, GitHub stops loading `CODEOWNERS` **entirely and silently**, taking all the
routing with it. So the command refuses to write a file over the limit rather than
switching the feature off on the user's behalf, and warns from 90% of it.

## The managed block

Markers, exactly like the `.gitignore` block `init` writes:

```
# --- lanekeeper (managed) — do not edit between these markers ---
...
# --- end lanekeeper ---
```

A file with one marker and not the other, or with the end before the start, is
**refused**: the text around a broken marker is somebody's routing, and neither
deleting it nor writing a second block below it is a repair.

Re-running replaces only what is between them. `lanekeeper uninit` removes only what is
between them, and removes the file only if nothing else was ever in it.

`lanekeeper codeowners --check` writes nothing and fails when the file no longer matches
the lanes — one line in CI to stop the two drifting apart.
