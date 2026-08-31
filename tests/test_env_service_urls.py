"""Service URLs in the generated .env — the variable that actually connects the stack."""

import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import generate_default_config
from lanekeeper.environment import (
    EnvironmentManager,
    UnresolvedTemplateError,
    expand_template,
)
from lanekeeper.state import AgentState


def agent(agent_id: str, backend: int, frontend: int) -> AgentState:
    return AgentState(
        id=agent_id, name=agent_id, seat="SR1", lane="backend", task="t",
        branch=f"parallel/{agent_id}/t", worktree_path=".",
        ports={"backend": backend, "frontend": frontend},
    )


class TestExpandTemplate(unittest.TestCase):
    def test_expands_known_placeholders(self):
        self.assertEqual(
            expand_template("API_URL", "http://${HOST}:${BACKEND_PORT}",
                            {"HOST": "127.0.0.1", "BACKEND_PORT": "8001"}),
            "http://127.0.0.1:8001",
        )

    def test_unknown_placeholder_fails_closed(self):
        """A half-expanded URL is worse than none: it fails far from its cause."""
        with self.assertRaises(UnresolvedTemplateError):
            expand_template("API_URL", "http://${HOST}:${BACKEND_PORT}", {"HOST": "h"})


class TestServiceUrls(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.worktree = Path(self.tmp_dir.name)
        self.config = generate_default_config("UrlApp")
        self.config.environment.url_templates["VITE_API_URL"] = "http://${HOST}:${BACKEND_PORT}"
        self.env_mgr = EnvironmentManager(self.config)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_api_url_points_at_this_agent_own_backend(self):
        env = self.env_mgr.generate_env_vars(agent("agent-002", 8002, 3002))
        self.assertEqual(env["API_URL"], "http://127.0.0.1:8002")
        self.assertEqual(env["VITE_API_URL"], "http://127.0.0.1:8002")
        self.assertEqual(env["FRONTEND_URL"], "http://127.0.0.1:3002")

    def test_two_agents_never_share_a_backend_url(self):
        """The defect this fixes: both agents' frontends addressed the same server."""
        first = self.env_mgr.generate_env_vars(agent("agent-001", 8001, 3001))
        second = self.env_mgr.generate_env_vars(agent("agent-002", 8002, 3002))
        self.assertNotEqual(first["VITE_API_URL"], second["VITE_API_URL"])
        self.assertEqual(first["VITE_API_URL"], "http://127.0.0.1:8001")
        self.assertEqual(second["VITE_API_URL"], "http://127.0.0.1:8002")

    def test_template_naming_an_absent_port_category_is_dropped(self):
        self.config.environment.url_templates["CACHE_URL"] = "redis://${HOST}:${CACHE_PORT}"
        env = self.env_mgr.generate_env_vars(agent("agent-001", 8001, 3001))
        self.assertNotIn("CACHE_URL", env)
        self.assertIn("API_URL", env)

    def test_host_is_configurable_not_hardcoded(self):
        self.config.environment.host = "0.0.0.0"
        env = self.env_mgr.generate_env_vars(agent("agent-001", 8001, 3001))
        self.assertEqual(env["HOST"], "0.0.0.0")
        self.assertEqual(env["API_URL"], "http://0.0.0.0:8001")

    def test_urls_are_written_into_the_env_file(self):
        self.env_mgr.write_agent_environment(self.worktree, agent("agent-002", 8002, 3002))
        content = (self.worktree / ".env").read_text(encoding="utf-8")
        self.assertIn("VITE_API_URL='http://127.0.0.1:8002'", content)
        self.assertIn("API_URL='http://127.0.0.1:8002'", content)


if __name__ == "__main__":
    unittest.main()
