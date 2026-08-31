# Contributing to Lanekeeper 🤝

Thank you for your interest in contributing to **Lanekeeper**! We welcome contributions from both human developers and teams operating AI-assisted coding harnesses.

This project is a practical, vendor-neutral framework designed to make parallel multi-agent software engineering reliable, scalable, and conflict-free.

---

## 🧭 How to Contribute

### 1. Reporting Bugs & Proposing Enhancements
* **Search Existing Issues**: Before opening a new issue, check if a similar topic is already being discussed.
* **Use Issue Forms**: When filing a bug or proposing a feature, use the structured GitHub Issue templates:
  * **Tasks & Features**: Include the target **Lane** (`interface`, `service`, `data`, `platform`) and allowed path boundaries.
  * **Defects**: Provide exact reproduction steps and error logs.

---

## 🛠️ Development & Submission Workflow

Whether you are writing documentation, improving bootstrap scripts, or adding templates, follow our standard parallel-agent discipline:

### 1. Work in a Feature Branch or Worktree
```bash
# Checkout a dedicated branch from main
git checkout -b feat/your-feature-name origin/main
```

### 2. Follow the Core Guidelines
* **Vendor & Project Neutrality**: Keep all documentation, scripts, and examples strictly vendor-neutral (no hardcoded model names or proprietary company references).
* **Copy-Paste Ready**: Code examples and bash snippets must be runnable and self-contained.
* **Markdown Integrity**: Use clear headers, tables, alerts (`[!NOTE]`, `[!IMPORTANT]`, `[!TIP]`), and standard syntax.

### 3. Open a Pull Request
* Use the [Pull Request Template](.github/pull_request_template.md).
* Explicitly declare which verification checks you executed (e.g. linter passes, script tests).
* Ensure PR threads and comments are resolved before requesting a merge.

---

## 🛡️ Working Agreement & Definition of Done

All pull requests must satisfy our [01 — Working Agreement](01-working-agreement.md):
- [ ] Changes adhere to path boundaries and file structure.
- [ ] No hardcoded secrets, tokens, or local environment variables.
- [ ] Added or updated documentation in `README.md` / `CHANGELOG.md` where applicable.
- [ ] Rebased on the latest `origin/main`.

---

## 🚢 Releasing

Releases publish themselves. Pushing a `v*` tag runs `.github/workflows/release.yml`,
which builds the distributions, checks their metadata, installs the wheel into a clean
virtual environment to confirm it reports the right version, and uploads to PyPI through
Trusted Publishing — there is no API token in this repository.

To cut a release:

1. Bump `version` in `pyproject.toml` and the `VERSION` file to match. CI fails if they
   disagree, and the release workflow fails if the tag disagrees with either.
2. Add the section to `CHANGELOG.md`.
3. Merge to `main`, then tag it: `git tag v0.7.0 && git push origin v0.7.0`.
4. Create the GitHub release from that tag, with the changelog section as its notes.

A published version is permanent. PyPI never allows a version number to be reused, even
after deletion — a bad upload costs a version number, so let the workflow do the checks.

---

## 📜 Code of Conduct

All contributors are expected to uphold our [Code of Conduct](CODE_OF_CONDUCT.md) to maintain a welcoming, respectful, and inclusive environment.
