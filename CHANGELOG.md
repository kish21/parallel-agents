# Changelog

All notable changes to the `parallel-agents` framework and scaffolding will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v0.1.0] - 2026-08-30 (Initial v0 Release)

### Added
- **Core Architecture & Guide (Chapters 01–06)**:
  - `01-working-agreement.md`: Definition-of-Done checklist, path boundary contracts, security DoD, and merge discipline.
  - `02-conflict-management.md`: Port allocation matrix (SR1/SR2/JR1/JR2), worktree vs. clone setup, migration collision prevention via ticket IDs, and `.gitattributes` union merge rules.
  - `03-orchestration.md`: 3-state capability model (`native`, `author-required`, `unavailable`), seat vs. vendor separation, scaling rules (2→4→6), and review chains.
  - `04-agent-setup.md`: Drop-in prompts for senior and junior agent sessions, `.lane` configuration specification, and context cost management.
  - `05-github-mechanics.md`: Board single-select fields (`Lane`, `Seat`, `Owner`), disjoint milestones, sub-issues, and single-account routing.
  - `06-free-tier-ops.md`: Public vs. private repository matrix, verified mirror sync scripts, divergence checkers, and CI minute optimizations.
- **Scaffolding & Tooling**:
  - `bootstrap.sh` & `bootstrap.conf.example`: Automated idempotent script to create GitHub Project boards, fields, standard labels, and milestones in < 30 seconds.
  - `templates/pull_request_template.md`: PR template with mandatory gate execution declaration and lane verification.
  - `templates/issue-template-task.yml` & `templates/issue-template-bug.yml`: GitHub Issue forms for lane-partitioned tasks and defects.
  - `templates/ci.yml`: GitHub Actions workflow with path filtering and auto-cancellation of superseded runs.
  - `templates/git-hooks/`: Pre-push test verification gate and pre-commit secret/env leak blocker.
  - `templates/dot-lane.example`: Local checkout seat configuration file.
  - `templates/gitattributes`: Union merge rules for generated indexes and registries.
- **Documentation**:
  - `README.md`: 5-minute replication quickstart guide and project overview.
