"""Command-Line Interface for parallel-agents."""

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
from .config import Config, load_config, save_config
from .doctor import Doctor
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
    config_file = root / ".parallel-agents" / "config.yaml"

    if config_file.exists() and not args.force:
        print(f"ℹ️ Configuration already exists at {config_file}. Use --force to re-initialize.")
        return 0

    cfg = Config.default(project_name=project_name)
    save_config(cfg, root)

    state_mgr = StateManager(root)
    # Ensure worktree directory exists
    (root / cfg.worktree_dir).mkdir(parents=True, exist_ok=True)

    print(f"✨ Initialized parallel-agents for '{project_name}'")
    print(f"📁 Configuration written to {config_file}")
    print(f"📁 Worktrees directory: {cfg.worktree_dir}")
    print("\nNext: Run 'parallel-agents doctor' or spawn an agent with 'parallel-agents spawn --name <name> --lane <lane> --task <task>'")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    doctor = Doctor()
    report = doctor.diagnose()

    print("\n🩺 PARALLEL AGENTS DOCTOR\n")
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
        print(f"⚠️ {report.problem_count} problem(s) detected. Run 'parallel-agents repair' to fix.")
        return 1


def cmd_repair(args: argparse.Namespace) -> int:
    doctor = Doctor()
    actions = doctor.repair(args.agent)
    print("\n🔧 PARALLEL AGENTS REPAIR\n")
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
        print(f"❌ Error loading parallel-agents state: {e}", file=sys.stderr)
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

    print(f"\n📋 PARALLEL AGENTS — {config.project_name.upper()}\n")
    if not agents:
        print("  No active agents found. Run 'parallel-agents spawn' to start one.\n")
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

    # Check capacity
    active_agents = [a for a in state_mgr.list_agents() if a.status != AgentStatus.STOPPED.value]
    if len(active_agents) >= config.max_agents and not args.force:
        print(f"❌ Max concurrent agents reached ({config.max_agents}). Use --force or stop an existing agent.", file=sys.stderr)
        return 1

    # Generate sequential ID
    existing_ids = {a.id for a in state_mgr.list_agents()}
    idx = 1
    while f"agent-{idx:03d}" in existing_ids:
        idx += 1
    agent_id = f"agent-{idx:03d}"

    name = args.name or f"worker-{idx}"
    lane = args.lane
    task = args.task or "General development"
    seat = args.seat or ("SR1" if "senior" in name.lower() else "JR1")

    # 1. Allocate Ports
    try:
        allocated_ports = port_mgr.allocate_ports_for_agent(agent_id)
    except Exception as e:
        print(f"❌ Port allocation failed: {e}", file=sys.stderr)
        return 1

    # 2. Create Worktree & Branch
    branch_name = worktree_mgr.make_branch_name(agent_id, task, config.git.branch_prefix)
    target_worktree_path = root / config.worktree_dir / agent_id

    try:
        print(f"🔨 Creating Git worktree for {agent_id} on branch '{branch_name}'...")
        resolved_path = worktree_mgr.create_worktree(target_worktree_path, branch_name)
    except Exception as e:
        port_mgr.release_ports(agent_id)
        print(f"❌ Worktree creation failed: {e}", file=sys.stderr)
        return 1

    # 3. Create Agent State
    agent = AgentState(
        id=agent_id,
        name=name,
        seat=seat,
        lane=lane,
        task=task,
        branch=branch_name,
        worktree_path=str(resolved_path),
        ports=allocated_ports,
        status=AgentStatus.CREATED.value,
    )

    # 4. Generate .env and .lane files in worktree
    env_mgr.write_agent_environment(resolved_path, agent)

    # 5. Start Agent (if command supplied) or initialize seat
    agent = adapter.start(agent, resolved_path, command=args.command)
    state_mgr.save_agent(agent)

    ports_display = ", ".join(f"{k}: {v}" for k, v in allocated_ports.items())
    print(f"\n🚀 Agent '{name}' ({agent_id}) successfully spawned!")
    print(f"  • Worktree: {resolved_path}")
    print(f"  • Branch:   {branch_name}")
    print(f"  • Lane:     {lane}")
    print(f"  • Ports:    {ports_display}")
    print(f"  • Seat:     {seat}")
    print(f"\nTo inspect:  parallel-agents inspect {agent_id}")
    print(f"To validate: parallel-agents validate {agent_id}")
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
    lane_config = config.lanes.get(agent.lane)
    lane_res = LaneEngine.validate_files(changed_files, lane_config) if lane_config else None

    print(f"\n📝 DIFF SUMMARY FOR {agent.name} ({agent.id})")
    print(f"Branch: {agent.branch}")
    print(f"Total Modified Files: {len(changed_files)}\n")

    for f in changed_files:
        norm_f = LaneEngine.normalize_path(f)
        if norm_f in (".env", ".lane", ".gitignore") or any(norm_f.startswith(p) for p in (".parallel-agents/", ".git/")):
            continue

        violation = None
        if lane_res:
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

    # Quality commands
    if report.quality_results:
        print("\n  [Quality & Test Commands]")
        for q in report.quality_results:
            icon = "✓" if q.passed else "✗"
            print(f"    {icon} {q.command} (Exit Code: {q.exit_code})")

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

    # 3. Remove worktree
    if worktree_path.exists():
        try:
            worktree_mgr.remove_worktree(worktree_path, force=args.force)
        except Exception as e:
            print(f"⚠️ Warning removing worktree: {e}")

    # 4. Remove state record
    state_mgr.remove_agent(agent.id)

    print(f"🧹 Successfully cleaned up agent '{agent.name}' ({agent.id}).")
    if released:
        print(f"   Released ports: {', '.join(str(p) for p in released)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parallel-agents",
        description="Parallel Agents — Mechanical Safety & Coordination Tool for AI Coding Agents",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init
    p_init = subparsers.add_parser("init", help="Initialize parallel-agents in current Git repository")
    p_init.add_argument("--name", help="Project name")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing configuration")
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
