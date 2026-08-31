"""Regression tests for LaneEngine.match_glob.

The previous implementation short-circuited on any pattern ending in '/**', returning a
plain prefix comparison. A pattern that both began with '**/' and ended with '/**' — the
natural way to write "anywhere under a directory named X", e.g. '**/secrets/**' — could
therefore never match anything. A lane denying that path silently denied nothing, and any
capability gate written that way was inert.
"""

import unittest

from parallel_agents.config import LaneConfig
from parallel_agents.lanes import LaneEngine


class TestMatchGlob(unittest.TestCase):
    def assert_match(self, path, pattern, expected):
        self.assertEqual(
            LaneEngine.match_glob(path, pattern), expected,
            f"{path!r} vs {pattern!r} should be {expected}",
        )

    def test_double_star_on_both_ends(self):
        """The case that was entirely broken."""
        for path in ["src/secrets/prod.pem", "a/b/c/secrets/x", "secrets/x"]:
            with self.subTest(path=path):
                self.assert_match(path, "**/secrets/**", True)

    def test_interior_double_star_spans_whole_segments(self):
        self.assert_match("src/backend/auth/login.py", "**/auth/**", True)
        self.assert_match("auth/login.py", "**/auth/**", True)

    def test_double_star_does_not_match_partial_segments(self):
        """'**/auth/**' must not match a directory merely starting with 'auth'."""
        self.assert_match("src/authentic/x.py", "**/auth/**", False)
        self.assert_match("src/oauth/x.py", "**/auth/**", False)

    def test_single_star_never_crosses_a_separator(self):
        self.assert_match("src/api.py", "src/*.py", True)
        self.assert_match("src/backend/api.py", "src/*.py", False)

    def test_trailing_double_star_matches_dir_and_contents(self):
        self.assert_match("src/backend", "src/backend/**", True)
        self.assert_match("src/backend/api.py", "src/backend/**", True)
        self.assert_match("src/backend/deep/nested/x.py", "src/backend/**", True)
        self.assert_match("src/frontend/App.tsx", "src/backend/**", False)

    def test_leading_double_star_filename_patterns(self):
        for path in ["test_a.py", "tests/test_a.py", "a/b/c/test_a.py"]:
            with self.subTest(path=path):
                self.assert_match(path, "**/test_*.py", True)
        self.assert_match("a/b/helper.py", "**/test_*.py", False)

    def test_exact_and_question_mark(self):
        self.assert_match("README.md", "README.md", True)
        self.assert_match("READMEX.md", "README.md", False)
        self.assert_match("a1.py", "a?.py", True)
        self.assert_match("a/1.py", "a?.py", False)

    def test_regex_metacharacters_are_literal(self):
        """A dot in a pattern must not match an arbitrary character."""
        self.assert_match("READMEXmd", "README.md", False)
        self.assert_match("src/a+b/x.py", "src/a+b/**", True)


class TestLaneDenyActuallyDenies(unittest.TestCase):
    def test_recursive_deny_pattern_is_enforced(self):
        """The user-visible consequence of the bug: a deny rule that denied nothing."""
        lane = LaneConfig(name="backend", allow=["src/**"], deny=["**/secrets/**"])
        result = LaneEngine.validate_files(
            ["src/secrets/prod.pem", "src/backend/api.py"], lane)
        self.assertFalse(result.is_valid, "a recursive deny pattern must be enforced")
        flagged = {v.filepath for v in result.violations}
        self.assertIn("src/secrets/prod.pem", flagged)
        self.assertNotIn("src/backend/api.py", flagged)

    def test_deny_takes_precedence_over_allow(self):
        lane = LaneConfig(name="backend", allow=["**"], deny=["**/secrets/**"])
        result = LaneEngine.validate_files(["deep/nested/secrets/key.pem"], lane)
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()
