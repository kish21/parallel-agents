"""Agent ids are monotonic — an id names a directory, so reuse collides with it."""

import tempfile
import unittest
from pathlib import Path

from lanekeeper.state import AgentState, StateManager


class TestAgentIdAllocation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.state = StateManager(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def _save(self, agent_id: str):
        self.state.save_agent(AgentState(
            id=agent_id, name=agent_id, seat="SR1", lane="backend", task="t",
            branch="b", worktree_path=".",
        ))

    def test_ids_increment(self):
        self.assertEqual(self.state.allocate_next_agent_id(), "agent-001")
        self._save("agent-001")
        self.assertEqual(self.state.allocate_next_agent_id(), "agent-002")

    def test_id_is_not_reissued_after_its_agent_is_removed(self):
        self.assertEqual(self.state.allocate_next_agent_id(), "agent-001")
        self._save("agent-001")
        self.state.remove_agent("agent-001")

        self.assertEqual(self.state.allocate_next_agent_id(), "agent-002")

    def test_sequence_resumes_when_the_counter_file_is_lost(self):
        """A missing counter may only resume the sequence, never rewind it."""
        for _ in range(3):
            self._save(self.state.allocate_next_agent_id())
        self.state.counter_file.unlink()

        self.assertEqual(self.state.allocate_next_agent_id(), "agent-004")

    def test_corrupt_counter_falls_back_to_state(self):
        self._save("agent-007")
        self.state.counter_file.write_text("{ not json", encoding="utf-8")

        self.assertEqual(self.state.allocate_next_agent_id(), "agent-008")


if __name__ == "__main__":
    unittest.main()
