"""The version the CLI reports must be the version the project actually is.

Before this, `__version__` was a literal that nobody updated: the package announced
0.1.0 while pyproject and VERSION both said 0.6.0. Nothing failed, because nothing
compared them. These tests are that comparison.
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

# `unittest discover` imports these as top-level modules, so a package-relative import
# would not resolve. Put the tests directory on the path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import run_cli  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def declared_version() -> str:
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


class TestVersion(unittest.TestCase):
    def test_pyproject_agrees_with_version_file(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml declares no version")
        self.assertEqual(match.group(1), declared_version())

    def test_package_version_is_not_a_stale_literal(self):
        from lanekeeper import __version__

        self.assertEqual(__version__, declared_version())

    def test_cli_version_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cli(["--version"], cwd=tmp)
        output = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, output)
        self.assertIn(declared_version(), output)
        self.assertIn("lanekeeper", output)


if __name__ == "__main__":
    unittest.main()
