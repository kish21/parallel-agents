# Legacy process documents

These six documents and the walkthrough predate the tool. They describe a way of running
agents by hand, with lanes named after **technology layers** — `interface`, `service`,
`data`, `platform` — and seats declared in a hand-written `.lane` file.

Lanekeeper no longer works that way. A lane is a **feature slice**, read from the
tickets and confirmed by you (`lanekeeper start`, then `lanekeeper divide --confirm`);
the `.lane` file is generated; the board is created from the configuration
(`lanekeeper board`); and the boundary is enforced by `lanekeeper check` on every pull
request. The README at the repository root is the current description.

The documents are kept because parts of them are still right — the capability card
schema in `03-orchestration.md` is the one the code implements, and the board mechanics
in `05-github-mechanics.md` are what `bootstrap.sh` automates — and because the
codebase's docstrings cite them by name. Read them as history, not as instructions.
