import unittest
from pathlib import Path

from lanekeeper.config import LaneConfig
from lanekeeper.lanes import LaneEngine


class TestLaneEngine(unittest.TestCase):
    def setUp(self):
        self.backend_lane = LaneConfig(
            name="backend",
            allow=[
                "src/api/**",
                "src/services/**",
                "tests/api/**",
            ],
            deny=[
                "src/frontend/**",
                "infrastructure/**",
            ],
        )

    def test_normalize_path(self):
        self.assertEqual(LaneEngine.normalize_path("src\\api\\users.py"), "src/api/users.py")
        self.assertEqual(LaneEngine.normalize_path("/src/api/users.py"), "src/api/users.py")
        self.assertEqual(LaneEngine.normalize_path(Path("src/api/users.py")), "src/api/users.py")
        self.assertEqual(LaneEngine.normalize_path("frontend/"), "frontend")

    def test_match_glob_wildcards(self):
        self.assertTrue(LaneEngine.match_glob("src/api/users.py", "src/api/**"))
        self.assertTrue(LaneEngine.match_glob("src/api/v1/auth/token.py", "src/api/**"))
        self.assertTrue(LaneEngine.match_glob("tests/test_users.py", "**/test_*.py"))
        self.assertFalse(LaneEngine.match_glob("src/frontend/App.tsx", "src/api/**"))

    def test_allowed_file(self):
        violation = LaneEngine.check_file("src/api/routes.py", self.backend_lane)
        self.assertIsNone(violation)

    def test_denied_file(self):
        violation = LaneEngine.check_file("src/frontend/App.tsx", self.backend_lane)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.reason, "denied")

    def test_unmatched_file_treated_as_not_allowed(self):
        violation = LaneEngine.check_file("docs/index.md", self.backend_lane)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.reason, "not_allowed")

    def test_validate_multiple_files(self):
        files = [
            "src/api/users.py",
            "src/services/auth.py",
            "src/frontend/Login.tsx",
            ".env",
            ".lane",
        ]
        res = LaneEngine.validate_files(files, self.backend_lane)
        self.assertFalse(res.is_valid)
        self.assertEqual(len(res.violations), 1)
        self.assertEqual(res.violations[0].filepath, "src/frontend/Login.tsx")
        self.assertIn("src/api/users.py", res.allowed_files)
        self.assertIn("src/services/auth.py", res.allowed_files)


if __name__ == "__main__":
    unittest.main()
