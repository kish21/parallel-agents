"""Unit tests for Lane path matching and boundary enforcement."""

import unittest
from pathlib import Path
from parallel_agents.config import LaneConfig
from parallel_agents.lanes import LaneEngine, LaneViolation


class TestLaneEngine(unittest.TestCase):
    def setUp(self):
        self.backend_lane = LaneConfig(
            name="backend",
            allow=["backend/**", "src/backend/**", "tests/backend/**"],
            deny=["frontend/**", "src/frontend/**", "infra/**", "secrets/**"],
        )

    def test_allowed_paths(self):
        self.assertIsNone(LaneEngine.check_file("backend/app/main.py", self.backend_lane))
        self.assertIsNone(LaneEngine.check_file("src/backend/services/auth.py", self.backend_lane))
        self.assertIsNone(LaneEngine.check_file("tests/backend/test_api.py", self.backend_lane))

    def test_denied_paths(self):
        v = LaneEngine.check_file("frontend/src/App.tsx", self.backend_lane)
        self.assertIsNotNone(v)
        self.assertEqual(v.reason, "denied")

        v2 = LaneEngine.check_file("infra/terraform/main.tf", self.backend_lane)
        self.assertIsNotNone(v2)
        self.assertEqual(v2.reason, "denied")

    def test_not_allowed_paths(self):
        # File that is neither in allow nor deny
        v = LaneEngine.check_file("docs/index.md", self.backend_lane)
        self.assertIsNotNone(v)
        self.assertEqual(v.reason, "not_allowed")

    def test_validate_files_batch(self):
        files = [
            "backend/api/users.py",
            "backend/models/user.py",
            "frontend/components/Button.tsx",  # Denied
            "docs/architecture.md",            # Not allowed
            ".git/HEAD",                       # Ignored
            ".parallel-agents/config.yaml",    # Ignored
        ]
        res = LaneEngine.validate_files(files, self.backend_lane)
        self.assertFalse(res.is_valid)
        self.assertEqual(len(res.allowed_files), 2)
        self.assertEqual(len(res.violations), 2)
        self.assertEqual(res.violations[0].filepath, "frontend/components/Button.tsx")
        self.assertEqual(res.violations[0].reason, "denied")
        self.assertEqual(res.violations[1].filepath, "docs/architecture.md")
        self.assertEqual(res.violations[1].reason, "not_allowed")


if __name__ == "__main__":
    unittest.main()
