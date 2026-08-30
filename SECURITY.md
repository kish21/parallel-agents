# Security Policy 🛡️

The **Parallel Agents** maintainers take the security of this framework, its automation tooling, and downstream agent workflows seriously.

---

## 📦 Supported Versions

We provide security updates and patches for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| `0.1.x` | :white_check_mark: |
| `< 0.1` | :x:                |

---

## 🚨 Reporting a Vulnerability

If you discover a security vulnerability (such as a command injection in `bootstrap.sh`, a secret leak risk in the git hooks, or an unsafe pattern in the agent instructions):

1. **Do NOT open a public issue.**
2. Report the vulnerability privately via **GitHub Security Advisory** on the repository:
   - Navigate to the repository's [Security Advisories tab](https://github.com/kish21/parallel-agents/security/advisories).
   - Click **"Report a vulnerability"**.
3. Alternatively, email the maintainer at `kishorekv2@gmail.com` with the subject line `[SECURITY] Parallel Agents Vulnerability Report`.

Please include:
* Description of the vulnerability and potential impact.
* Step-by-step reproduction instructions or proof-of-concept.
* Suggested remediations (if known).

We will acknowledge receipt within 48 hours and work with you to coordinate a responsible public patch.

---

## 🔒 Security Best Practices for Parallel Agent Operators

When running AI agents on your codebase:

1. **Never Commit Secrets**: Use `.env` files and enforce pre-commit secret scanning hooks (`templates/git-hooks/pre-commit`).
2. **Restrict Agent File Permissions**: Ensure agents only have write permissions within their checked-out worktree.
3. **Review Database & Auth Changes**: Require Senior (`SR1`/`SR2`) human or lead verification on any PR touching authentication, tenant isolation, or database migrations.
