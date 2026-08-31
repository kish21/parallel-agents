"""Command-Line Interface for lanekeeper."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .adapters.process_adapter import ProcessAdapter
from .capabilities import (
    CapabilityRegistry,
    CapabilityState,
    UnknownSeatError,
    default_cards,
    save_card,
)
from .config import Config, UnknownLaneError, load_config, save_config
from .doctor import Doctor
from . import paths
from .layout import detect_layout, measure_coverage
from .environment import EnvironmentManager
from .lanes import LaneEngine
from .ports import PortManager
from .state import AgentState, AgentStatus, StateManager
from .validator import Validator
from .worktree import WorktreeManager


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    worktree_mgr = WorktreeManager(root)
    if not worktree_mgr.is_git_repo():
        print("❌ Error: Must run inside a valid Git repository root.", file=sys.stderr)
        return 1

    project_name = args.name or root.name
    config_file = paths.config_path(root)

    if config_file.exists() and not args.force:
        print(f"ℹ️ Configuration already exists at {config_file}. Use --force to re-initialize.")
        return 0

    cfg = Config.default(project_name=project_name)

    # Derive lanes from the repository that exists. The stock lanes assume backend/ and
    # frontend/ directories; on a project laid out any other way they match nothing, and
    # the first validate fails on legitimate work.
    detection = None
    if not getattr(args, "generic", False):
        detection = detect_layout(root)
        if detection.is_meaningful:
            cfg.lanes = detection.lanes

    save_config(cfg, root)

    state_mgr = StateManager(root)
    # Ensure worktree directory exists
    (root / cfg.worktree_dir).mkdir(parents=True, exist_ok=True)
    gitignore_updated = ensure_gitignore(root)

    # Capability gates are configured by default, and a configured gate requires a card
    # for every seat — otherwise validation fails closed for want of one. Write the
    # starter cards so the feature is usable and visible from the first spawn.
    written_cards = [save_card(card, root) for card in default_cards(sorted(cfg.lanes))]

    print(f"✨ Initialized lanekeeper for '{project_name}'")
    print(f"📁 Configuration written to {config_file}")
    print(f"📁 Worktrees directory: {cfg.worktree_dir}")

    coverage, total, uncovered = measure_coverage(root, cfg.lanes)
    lane_names = ", ".join(sorted(cfg.lanes))
    if detection is not None and detection.is_meaningful:
        print(f"🧭 Detected {len(cfg.lanes)} lanes from the repository layout: {lane_names}")
    else:
        print(f"🧭 Using generic starter lanes: {lane_names}")
    print(f"   Coverage: {coverage:.0%} of {total} tracked files fall inside a lane.")

    if total and coverage < 0.5:
        print("\n⚠️  These lanes match little of this repository, so validation will report")
        print("   legitimate work as out-of-lane. Edit the 'lanes' section of config.yaml to")
        print("   match your directory structure before spawning agents.")
        if uncovered:
            print(f"   Unowned paths include: {', '.join(uncovered[:3])}")
    elif len(cfg.lanes) < 2 and total:
        print("\n⚠️  Only one lane was found, so there is nothing to run in parallel.")
        print("   Parallel agents scale with the number of *separable* lanes, not with the")
        print("   number of agents. Split the codebase further, or run a single agent.")
    print(f"🎫 Capability cards written for {len(written_cards)} seats: "
          + ", ".join(c.stem for c in written_cards))
    if gitignore_updated:
        print("📝 Added lanekeeper rules to .gitignore (runtime state ignored, config tracked)")
    print(f"\n⚠️  Commit {paths.display_config_path(root)} — it is the lane policy every agent is validated against.")
    print("\nNext: Run 'lanekeeper doctor' or spawn an agent with 'lanekeeper spawn --name <name> --lane <lane> --task <task>'")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    doctor = Doctor()
    report = doctor.diagnose()

    print("\n🩺 LANEKEEPER DOCTOR\n")
    for check in report.checks:
        icon = "✓" if check.passed else "✗"
        print(f"  {icon} {check.name}: {check.message}")
        if not check.passed and check.details:
            for line in check.details.splitlines():
                print(f"      ↳ {line}")

    print()
    if report.is_healthy:
        print("✅ Environment is clean and ready for parallel execution.")
        return 0
    else:
        print(f"⚠️ {report.problem_count} problem(s) detected. Run 'lanekeeper repair' to fix.")
        return 1


def cmd_repair(args: argparse.Namespace) -> int:
    doctor = Doctor()
    actions = doctor.repair(args.agent)
    print("\n🔧 LANEKEEPER REPAIR\n")
    if not actions:
        print("  No repair actions required.")
    else:
        for act in actions:
            print(f"  ✓ {act}")
    print("\n✅ Repair pass complete.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        config = load_config()
        state_mgr = StateManager()
    except Exception as e:
        print(f"❌ Error loading lanekeeper state: {e}", file=sys.stderr)
        return 1

    agents = state_mgr.list_agents()

    if args.json:
        output_data = {
            "project": config.project_name,
            "max_agents": config.max_agents,
            "agents": [a.to_dict() for a in agents],
        }
        print(json.dumps(output_data, indent=2))
        return 0

    print(f"\n📋 LANEKEEPER — {config.project_name.upper()}\n")
    if not agents:
        print("  No active agents found. Run 'lanekeeper spawn' to start one.\n")
        return 0

    header = f"{'Agent ID':<12} {'Name':<14} {'Seat':<6} {'Lane':<12} {'Status':<10} {'Ports':<16} {'Task'}"
    print(header)
    print("-" * len(header) + "-" * 20)

    for a in agents:
        ports_str = "/".join(str(p) for p in a.ports.values()) or "-"
        task_snippet = (a.task[:30] + "...") if len(a.task) > 30 else a.task
        print(f"{a.id:<12} {a.name:<14} {a.seat:<6} {a.lane:<12} {a.status:<10} {ports_str:<16} {task_snippet}")

    print()
    return 0


GITIGNORE_BEGIN = "# --- lanekeeper (managed) ---"
GITIGNORE_END = "# --- end lanekeeper ---"


def gitignore_block(root: Optional[Path] = None) -> str:
    """The managed ignore block, built from the configured directory name.

    Built on demand rather than as a module constant so that an overridden
    directory name is reflected in what `init` writes.
    """
    ignore, keep = paths.gitignore_lines(root)
    return f"""{GITIGNORE_BEGIN}
# Runtime state, logs and agent worktrees are machine-local and must never be committed.
# Without these rules an agent running `git add -A` would sweep every other agent's
# worktree into its own commit.
{ignore}
# The lane policy is the team's shared contract - keep it tracked.
{keep}
{GITIGNORE_END}
"""


def ensure_gitignore(root: Path) -> bool:
    """Adds the managed ignore block to the repository .gitignore. Idempotent.

    Returns True if the file was modified.
    """
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if GITIGNORE_BEGIN in existing:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with open(gitignore, "a", encoding="utf-8") as f:
        f.write(f"{prefix}\n{gitignore_block(root)}")
    return True


def target_path_for(root: Path, config: Config, agent_id: str) -> Path:
    """Resolves the on-disk worktree location for an agent."""
    return root / config.worktree_dir / agent_id


def cmd_spawn(args: argparse.Namespace) -> int:
    root = Path.cwd()
    try:
        config = load_config(root)
        state_mgr = StateManager(root)
        worktree_mgr = WorktreeManager(root)
        port_mgr = PortManager(config, state_mgr)
        env_mgr = EnvironmentManager(config)
        adapter = ProcessAdapter(root)
    except Exception as e:
        print(f"❌ Error loading project: {e}", file=sys.stderr)
        return 1

    # Reject an undeclared lane before any resource is provisioned. A lane that is not
    # in the config has no allow/deny policy, so an agent spawned into it could never be
    # meaningfully validated.
    if not config.has_lane(args.lane):
        known = ", ".join(sorted(config.lanes)) or "(none declared)"
        print(f"❌ Unknown lane '{args.lane}'. Declared lanes: {known}.", file=sys.stderr)
        print(f"   Add the lane to {paths.display_config_path()}, or spawn into an existing one.", file=sys.stderr)
        return 1

    # A seat must have a capability card whenever gates are configured, and its card must
    # permit the requested lane. Both are checked before anything is provisioned, so an
    # impossible assignment fails at the point it is made rather than at review time.
    registry = CapabilityRegistry.load(root)
    default_seat = args.seat or "JR1"
    if config.capability_gates:
        if registry.is_empty:
            print("❌ Capability gates are configured but no capability cards were found.", file=sys.stderr)
            print(f"   Expected cards in {paths.display_capabilities_dir()}. Run 'lanekeeper init --force'", file=sys.stderr)
            print("   to write the starter cards, or remove capability_gates from config.yaml.", file=sys.stderr)
            return 1
        try:
            card = registry.get(default_seat)
        except UnknownSeatError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1
        if not card.allows_lane(args.lane):
            scope = ", ".join(card.max_allowed_lane_scope) or "(none)"
            print(f"❌ Seat '{default_seat}' is not permitted in lane '{args.lane}'. "
                  f"Allowed lanes for this seat: {scope}.", file=sys.stderr)
            return 1

    # Phase 1 (locked): reserve identity and ports. The placeholder agent record is
    # persisted inside the lock so a concurrent spawn immediately sees the ID as taken.
    try:
        with state_mgr.lock():
            active_agents = [a for a in state_mgr.list_agents() if a.status != AgentStatus.STOPPED.value]
            if len(active_agents) >= config.max_agents and not args.force:
                print(f"❌ Max concurrent agents reached ({config.max_agents}). Use --force or stop an existing agent.", file=sys.stderr)
                return 1

            agent_id = state_mgr.allocate_next_agent_id()
            idx_str = agent_id.split("-")[-1]

            name = args.name or f"worker-{int(idx_str)}"
            lane = args.lane
            task = args.task or "General development"
            seat = args.seat or default_seat
            branch_name = worktree_mgr.make_branch_name(agent_id, task, config.git.branch_prefix)

            try:
                allocated_ports = port_mgr.allocate_ports_for_agent(agent_id)
            except Exception as e:
                print(f"❌ Port allocation failed: {e}", file=sys.stderr)
                return 1

            agent = AgentState(
                id=agent_id, name=name, seat=seat, lane=lane, task=task,
                branch=branch_name,
                worktree_path=str(root / config.worktree_dir / agent_id),
                ports=allocated_ports,
                status=AgentStatus.CREATED.value,
            )
            state_mgr.save_agent(agent)
    except Exception as e:
        print(f"❌ Failed to reserve agent resources: {e}", file=sys.stderr)
        return 1

    # Phase 2: create the worktree under the dedicated git lock, then do the rest
    # unlocked. Concurrent `git worktree add` against one repository races on refs and the
    # index, so it must be serialised — but only against other git operations, not against
    # readers of the state file.
    try:
        print(f"🔨 Creating Git worktree for {agent_id} on branch '{branch_name}'...")
        with state_mgr.git_lock():
            resolved_path = worktree_mgr.create_worktree(target_path_for(root, config, agent_id), branch_name)
        agent.worktree_path = str(resolved_path)
        env_mgr.write_agent_environment(resolved_path, agent)
        agent = adapter.start(agent, resolved_path, command=args.command)
    except Exception as e:
        # Roll the reservation back so a failed spawn leaks neither ports nor an ID.
        port_mgr.release_ports(agent_id)
        state_mgr.remove_agent(agent_id)
        print(f"❌ Spawn failed: {e}", file=sys.stderr)
        return 1

    # Phase 3 (locked): commit the final, running state.
    state_mgr.save_agent(agent)

    ports_display = ", ".join(f"{k}: {v}" for k, v in allocated_ports.items())
    print(f"\n🚀 Agent '{name}' ({agent_id}) successfully spawned!")
    print(f"  • Worktree: {resolved_path}")
    print(f"  • Branch:   {branch_name}")
    print(f"  • Lane:     {lane}")
    print(f"  • Ports:    {ports_display}")
    print(f"  • Seat:     {seat}")
    print(f"\nTo inspect:  lanekeeper inspect {agent_id}")
    print(f"To validate: lanekeeper validate {agent_id}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state_mgr = StateManager()
    agent = state_mgr.get_agent(args.agent)
    if not agent:
        print(f"❌ Agent '{args.agent}' not found.", file=sys.stderr)
        return 1

    adapter = ProcessAdapter()
    adapter.stop(agent)
    state_mgr.save_agent(agent)
    print(f"⏹️ Agent '{agent.name}' ({agent.id}) stopped.")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    state_mgr = StateManager()
    agent = state_mgr.get_agent(args.agent)
    if not agent:
        print(f"❌ Agent '{args.agent}' not found.", file=sys.stderr)
        return 1

    adapter = ProcessAdapter()
    adapter.restart(agent, Path(agent.worktree_path))
    state_mgr.save_agent(agent)
    print(f"🔄 Agent '{agent.name}' ({agent.id}) restarted.")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    state_mgr = StateManager()
    agent = state_mgr.get_agent(args.agent)
    if not agent:
        print(f"❌ Agent '{args.agent}' not found.", file=sys.stderr)
        return 1

    print(f"\n🔍 AGENT INSPECTION: {agent.name} ({agent.id})\n")
    print(f"  • Status:     {agent.status}")
    print(f"  • Seat:       {agent.seat}")
    print(f"  • Lane:       {agent.lane}")
    print(f"  • Task:       {agent.task}")
    print(f"  • Branch:     {agent.branch}")
    print(f"  • Worktree:   {agent.worktree_path}")
    print(f"  • PID:        {agent.pid or 'None (Manual Session)'}")
    print(f"  • Created At: {agent.created_at}")
    print("  • Allocated Ports:")
    for k, v in agent.ports.items():
        print(f"      - {k}: {v}")
    print()
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    state_mgr = StateManager()
    agent = state_mgr.get_agent(args.agent)
    if not agent:
        print(f"❌ Agent '{args.agent}' not found.", file=sys.stderr)
        return 1

    adapter = ProcessAdapter()
    logs = adapter.get_logs(agent, tail=args.tail or 50)
    print(f"\n📜 LOGS FOR {agent.name} ({agent.id}):\n")
    for line in logs:
        print(line)
    print()
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    root = Path.cwd()
    try:
        config = load_config(root)
        state_mgr = StateManager(root)
        worktree_mgr = WorktreeManager(root)
    except Exception as e:
        print(f"❌ Error loading project: {e}", file=sys.stderr)
        return 1

    agent = state_mgr.get_agent(args.agent)
    if not agent:
        print(f"❌ Agent '{args.agent}' not found.", file=sys.stderr)
        return 1

    worktree_path = Path(agent.worktree_path)
    if not worktree_path.exists():
        print(f"❌ Worktree {worktree_path} does not exist.", file=sys.stderr)
        return 1

    changed_files = worktree_mgr.get_changed_files(worktree_path)
    try:
        lane_config = config.get_lane(agent.lane)
    except UnknownLaneError as e:
        print(f"❌ {e}", file=sys.stderr)
        print(f"   Agent '{agent.id}' cannot be diffed against an undeclared lane.", file=sys.stderr)
        return 1
    lane_res = LaneEngine.validate_files(changed_files, lane_config)

    print(f"\n📝 DIFF SUMMARY FOR {agent.name} ({agent.id})")
    print(f"Branch: {agent.branch}")
    print(f"Total Modified Files: {len(changed_files)}\n")

    for f in changed_files:
        norm_f = LaneEngine.normalize_path(f)
        if norm_f in (".env", ".lane", ".gitignore") or any(norm_f.startswith(prefix) for prefix in paths.ignored_prefixes()):
            continue

        violation = None
        for v in lane_res.violations:
            if v.filepath == norm_f:
                violation = v
                break

        if violation:
            print(f"  ✗ [OUT-OF-LANE] {norm_f} ({violation.reason})")
        else:
            print(f"  ✓ [LANE OK]    {norm_f}")

    print()
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path.cwd()
    try:
        config = load_config(root)
        state_mgr = StateManager(root)
        worktree_mgr = WorktreeManager(root)
        validator = Validator(config, state_mgr, worktree_mgr)
    except Exception as e:
        print(f"❌ Error loading project: {e}", file=sys.stderr)
        return 1

    try:
        report = validator.validate_agent(args.agent)
    except Exception as e:
        print(f"❌ Validation error: {e}", file=sys.stderr)
        return 1

    print(f"\n🛡️ VALIDATION REPORT: {report.agent_name} ({report.agent_id})")
    print(f"Lane: {report.lane}\n")

    # Lane checks
    print("  [Lane Compliance]")
    if report.lane_result.is_valid:
        print(f"    ✓ All {len(report.lane_result.allowed_files)} changed files are within allowed lane paths.")
    else:
        for v in report.lane_result.violations:
            print(f"    ✗ Violation: {v.filepath} (Reason: {v.reason})")

    # Capability gates
    if report.gates_evaluated:
        print(f"\n  [Capability Gates] seat {report.seat} — evaluated: {', '.join(report.gates_evaluated)}")
        if not report.capability_violations:
            print("    ✓ No gated path was touched by a capability this seat lacks.")
        else:
            for cv in report.capability_violations:
                print(f"    ✗ {cv.filepath}")
                print(f"        requires '{cv.capability}' — seat is '{cv.state}'")
                print(f"        {cv.detail}")

    # Quality commands
    if report.quality_results:
        print("\n  [Quality & Test Commands]")
        for q in report.quality_results:
            icon = "✓" if q.passed else "✗"
            tag = f" [satisfies: {q.satisfies}]" if q.satisfies else ""
            print(f"    {icon} {q.command}{tag} (Exit Code: {q.exit_code})")

    # Always surface the error list. Some failure modes (an undeclared lane, a missing
    # worktree) produce no per-file violations, and printing nothing but "FAILED" left the
    # operator with no way to tell what went wrong.
    if report.errors:
        print("\n  [Errors]")
        for err in report.errors:
            print(f"    ✗ {err}")

    print("\n" + "=" * 50)
    if report.is_valid:
        print("✅ VALIDATION PASSED: PR is safe to submit and merge.")
        return 0
    else:
        print("❌ VALIDATION FAILED: Must resolve errors before merging.")
        return 2


def cmd_cleanup(args: argparse.Namespace) -> int:
    root = Path.cwd()
    try:
        state_mgr = StateManager(root)
        worktree_mgr = WorktreeManager(root)
        adapter = ProcessAdapter(root)
    except Exception as e:
        print(f"❌ Error loading project: {e}", file=sys.stderr)
        return 1

    agent = state_mgr.get_agent(args.agent)
    if not agent:
        print(f"❌ Agent '{args.agent}' not found.", file=sys.stderr)
        return 1

    worktree_path = Path(agent.worktree_path)

    # Check uncommitted changes
    if worktree_path.exists() and worktree_mgr.has_uncommitted_changes(worktree_path):
        if not args.force:
            print(f"⚠️ Agent '{agent.name}' has uncommitted changes in {worktree_path}.")
            confirm = input("Are you sure you want to delete this worktree? [y/N]: ").strip().lower()
            if confirm != "y":
                print("❌ Cleanup aborted. Changes preserved.")
                return 1

    # 1. Stop process
    adapter.stop(agent)

    # 2. Release ports
    released = state_mgr.release_ports_for_agent(agent.id)

    # 3. Remove worktree (repository-mutating: same lock as creation)
    if worktree_path.exists():
        try:
            with state_mgr.git_lock():
                worktree_mgr.remove_worktree(worktree_path, force=args.force)
        except Exception as e:
            print(f"⚠️ Warning removing worktree: {e}")

    # 4. Remove state record
    state_mgr.remove_agent(agent.id)

    print(f"🧹 Successfully cleaned up agent '{agent.name}' ({agent.id}).")
    if released:
        print(f"   Released ports: {', '.join(str(p) for p in released)}")
    return 0


def cmd_declare(args: argparse.Namespace) -> int:
    """Generates the PR gate declaration from recorded state.

    The PR template asks the author to hand-write which gate they ran. Typing it is an
    honour-system step; deriving it from the agent's seat, card, and actual command exit
    codes makes it an artefact instead.
    """
    root = Path.cwd()
    try:
        config = load_config(root)
        state_mgr = StateManager(root)
        worktree_mgr = WorktreeManager(root)
        registry = CapabilityRegistry.load(root)
        validator = Validator(config, state_mgr, worktree_mgr, registry)
    except Exception as e:
        print(f"❌ Error loading project: {e}", file=sys.stderr)
        return 1

    try:
        report = validator.validate_agent(args.agent)
    except Exception as e:
        print(f"❌ Could not build declaration: {e}", file=sys.stderr)
        return 1

    card = registry.cards.get(report.seat)
    harness = (card.vendor_harness if card and card.vendor_harness else "unspecified")

    print(f"### Seat & Lane Information")
    print(f"- **Seat**: {report.seat}")
    print(f"- **Lane**: {report.lane}")
    print(f"- **Harness**: {harness}")
    print()
    print("### Capability Gate Executed")
    if not report.gates_evaluated:
        print("- No capability gates are configured for this repository.")
    else:
        for name in report.gates_evaluated:
            state = card.state_for(name).value if card else "no card"
            triggered = [cv for cv in report.capability_violations if cv.capability == name]
            mark = "x" if not triggered else " "
            note = "" if not triggered else f" — BLOCKED on {len(triggered)} file(s)"
            print(f"- [{mark}] `{name}` (seat rated: {state}){note}")
    print()
    print("### Gate Declaration")
    print("```bash")
    if not report.quality_results:
        print("# No quality commands configured.")
    for q in report.quality_results:
        tag = f"   # satisfies: {q.satisfies}" if q.satisfies else ""
        print(f"$ {q.command}{tag}")
        print(f"exit {q.exit_code}")
    print("```")
    passed = sum(1 for q in report.quality_results if q.passed)
    failed = len(report.quality_results) - passed
    print(f"- **Checks Run**: {passed} Passed, {failed} Failed")
    print(f"- **Lane Compliance**: {len(report.lane_result.allowed_files)} file(s) in lane, "
          f"{len(report.lane_result.violations)} violation(s)")
    print(f"- **Status**: {'Clean / All Passed' if report.is_valid else 'BLOCKED — see errors'}")
    if report.errors:
        print()
        print("### Blocking Errors")
        for e in report.errors:
            print(f"- {e}")
    return 0 if report.is_valid else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lanekeeper",
        description="Lanekeeper — Mechanical Safety & Coordination Tool for AI Coding Agents",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init
    p_init = subparsers.add_parser("init", help="Initialize lanekeeper in current Git repository")
    p_init.add_argument("--name", help="Project name")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing configuration")
    p_init.add_argument("--generic", action="store_true",
                        help="Use the generic starter lanes instead of detecting the repository layout")
    p_init.set_defaults(func=cmd_init)

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Diagnose repository, worktree, and port health")
    p_doc.set_defaults(func=cmd_doctor)

    # repair
    p_rep = subparsers.add_parser("repair", help="Repair stale agent states and orphaned resources")
    p_rep.add_argument("agent", nargs="?", help="Specific agent ID to repair")
    p_rep.set_defaults(func=cmd_repair)

    # status
    p_stat = subparsers.add_parser("status", help="Show active parallel agents and resource allocation")
    p_stat.add_argument("--json", action="store_true", help="Output status as JSON")
    p_stat.set_defaults(func=cmd_status)

    # spawn
    p_spawn = subparsers.add_parser("spawn", help="Spawn a new isolated agent worktree and allocate ports")
    p_spawn.add_argument("--name", help="Human-readable agent name (e.g. backend-1)")
    p_spawn.add_argument("--lane", required=True, help="Assigned lane (e.g. backend, frontend, data)")
    p_spawn.add_argument("--task", default="General feature development", help="Task description")
    p_spawn.add_argument("--seat", help="Seat slot (e.g. SR1, SR2, JR1, JR2)")
    p_spawn.add_argument("--command", help="Optional CLI command/harness to start in worktree")
    p_spawn.add_argument("--force", action="store_true", help="Bypass max agent capacity check")
    p_spawn.set_defaults(func=cmd_spawn)

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop a running agent process")
    p_stop.add_argument("agent", help="Agent ID or name")
    p_stop.set_defaults(func=cmd_stop)

    # restart
    p_res = subparsers.add_parser("restart", help="Restart an agent process")
    p_res.add_argument("agent", help="Agent ID or name")
    p_res.set_defaults(func=cmd_restart)

    # inspect
    p_ins = subparsers.add_parser("inspect", help="Inspect detailed agent state and environment")
    p_ins.add_argument("agent", help="Agent ID or name")
    p_ins.set_defaults(func=cmd_inspect)

    # logs
    p_logs = subparsers.add_parser("logs", help="View agent execution logs")
    p_logs.add_argument("agent", help="Agent ID or name")
    p_logs.add_argument("--tail", type=int, default=50, help="Number of lines to show")
    p_logs.set_defaults(func=cmd_logs)

    # diff
    p_diff = subparsers.add_parser("diff", help="View changed files and lane compliance")
    p_diff.add_argument("agent", help="Agent ID or name")
    p_diff.set_defaults(func=cmd_diff)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate lane boundaries and quality checks")
    p_val.add_argument("agent", help="Agent ID or name")
    p_val.set_defaults(func=cmd_validate)

    # declare
    p_dec = subparsers.add_parser("declare", help="Generate the PR gate declaration for an agent")
    p_dec.add_argument("agent", help="Agent ID or name")
    p_dec.set_defaults(func=cmd_declare)

    # cleanup
    p_cln = subparsers.add_parser("cleanup", help="Safely remove agent process, worktree, and ports")
    p_cln.add_argument("agent", help="Agent ID or name")
    p_cln.add_argument("--force", action="store_true", help="Force deletion even if uncommitted changes exist")
    p_cln.set_defaults(func=cmd_cleanup)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
