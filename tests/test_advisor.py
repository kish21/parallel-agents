"""The advisor: Claude Code asked what a pathless ticket touches, and never obeyed.

The model is a fake runner replaying answers. What is tested is everything around it:
that only unplaced tickets are asked, that invented paths are dropped, that the
suggestion lands in the draft switched off and marked as proposed, and that a broken
advisor is reported once rather than crashing the division.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper.config import Config, DivideConfig, InvalidDivideSettingError, load_config, save_config
from lanekeeper.divide import advisor as advisor_mod
from lanekeeper.divide import draft as draft_mod
from lanekeeper.divide.models import PathSource
from lanekeeper.divide.proposal import propose
from lanekeeper.intake.models import IntakeResult
from lanekeeper.trackers.github_issues import CommandResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _divide_fixtures import feature_files, ticket  # noqa: E402


class FakeRunner:
    def __init__(self, stdout="", returncode=0, stderr="", raise_exc=None):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.raise_exc = raise_exc
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if self.raise_exc:
            raise self.raise_exc
        return CommandResult(self.returncode, self.stdout, self.stderr)


def intake_with(issues):
    return IntakeResult.__new__(IntakeResult) if False else _result(issues)


def _result(issues):
    # Only the tickets matter to step 2; the rest of the result is step 1's business.
    from lanekeeper.intake.models import CoverageReport, CoverageVerdict, Verdict
    return IntakeResult(verdict=Verdict.READY, issue_count=len(issues),
                        coverage=CoverageReport(verdict=CoverageVerdict.CANNOT_JUDGE),
                        issues=tuple(issues))


class TestParsingTheAnswer(unittest.TestCase):
    def test_json_object_anywhere_in_the_text(self):
        text = 'Sure. Here you go:\n{"paths": ["backend/app/domains/catalog/**", "x.py"]}\nDone.'
        self.assertEqual(advisor_mod.parse_paths(text),
                         ("backend/app/domains/catalog/**", "x.py"))

    def test_no_json_is_no_paths(self):
        self.assertEqual(advisor_mod.parse_paths("I don't know"), ())
        self.assertEqual(advisor_mod.parse_paths('{"paths": "one"}'), ())
        self.assertEqual(advisor_mod.parse_paths("{bad json"), ())

    def test_only_paths_that_name_something_real_survive(self):
        files = ["backend/app/domains/catalog/list.py", "frontend/src/pages/Catalog.tsx"]
        kept = advisor_mod.keep_real_paths(
            ("backend/app/domains/catalog/**", "backend/app/domains/invented/**",
             "frontend/src/pages/Catalog.tsx", "docs/made-up.md"), files)
        self.assertEqual(kept, ("backend/app/domains/catalog/**", "frontend/src/pages/Catalog.tsx"))

    def test_the_prompt_asks_for_json_and_shows_the_files(self):
        prompt = advisor_mod.build_prompt("7", "Add cart", "A body", ["a.py", "b.py"])
        self.assertIn('{"paths"', prompt)
        self.assertIn("a.py\nb.py", prompt)
        self.assertIn("Ticket #7: Add cart", prompt)


class TestClaudeCodeAdvisor(unittest.TestCase):
    def test_runs_claude_headless_and_filters(self):
        runner = FakeRunner('{"paths": ["backend/app/domains/catalog/**", "nope/**"]}')
        adv = advisor_mod.ClaudeCodeAdvisor("claude", Path("."), runner=runner)
        got = adv.propose_paths("7", "Catalog", "body", feature_files())
        self.assertEqual(got, ("backend/app/domains/catalog/**",))
        argv = runner.calls[0]
        self.assertEqual(argv[:2], ["claude", "-p"])
        self.assertIn("--output-format", argv)

    def test_a_failing_command_is_an_advisor_error(self):
        adv = advisor_mod.ClaudeCodeAdvisor("claude", Path("."),
                                            runner=FakeRunner(returncode=1, stderr="not logged in"))
        with self.assertRaises(advisor_mod.AdvisorError) as ctx:
            adv.propose_paths("7", "t", "b", [])
        self.assertIn("not logged in", str(ctx.exception))

    def test_a_missing_command_is_named(self):
        adv = advisor_mod.ClaudeCodeAdvisor("no-such-claude-xyz", Path("."))
        with self.assertRaises(advisor_mod.AdvisorError) as ctx:
            adv.check_available()
        self.assertIn("no-such-claude-xyz", str(ctx.exception))
        self.assertIn("divide.advisor", str(ctx.exception))

    def test_get_advisor_fails_closed_on_an_unknown_name(self):
        class S:
            advisor = "gpt"
            advisor_command = "x"
        with self.assertRaises(advisor_mod.AdvisorError):
            advisor_mod.get_advisor(S(), Path("."))
        self.assertIsInstance(advisor_mod.get_advisor(DivideConfig(), Path(".")),
                              advisor_mod.NoAdvisor)


class TestTheAdvisorInTheDivision(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.settings = DivideConfig()
        self.files = feature_files()

    def test_only_an_unplaced_ticket_is_asked(self):
        runner = FakeRunner('{"paths": ["backend/app/domains/catalog/**"]}')
        adv = advisor_mod.ClaudeCodeAdvisor("claude", self.tmp, runner=runner)
        issues = [
            ticket(1, "Catalog list", ["backend/app/domains/catalog/**"]),
            ticket(2, "Something with no files and no matching name", []),
        ]
        proposal = propose(self.tmp, self.settings, _result(issues), files=self.files,
                           advisor=adv)
        self.assertEqual(adv.asked, ["2"])
        self.assertEqual(proposal.unplaced, ())
        suggested = [b for b in proposal.needs_paths if b.ref == "2"]
        self.assertEqual(len(suggested), 1)
        self.assertEqual(suggested[0].source, PathSource.PROPOSED)
        self.assertEqual(suggested[0].paths, ("backend/app/domains/catalog/**",))

    def test_the_suggestion_is_in_the_draft_switched_off(self):
        adv = advisor_mod.ClaudeCodeAdvisor(
            "claude", self.tmp, runner=FakeRunner('{"paths": ["backend/app/domains/catalog/**"]}'))
        issues = [ticket(2, "Mystery work", [])]
        proposal = propose(self.tmp, self.settings, _result(issues), files=self.files,
                           advisor=adv)
        text = draft_mod.render(proposal, self.settings)
        self.assertIn("#       - backend/app/domains/catalog/**", text)
        self.assertIn("nobody has confirmed them", text)
        loaded = yaml.safe_load(text)
        self.assertNotIn("work-2", loaded.get("lanes") or {},
                         "a suggestion must not load as a lane until the user switches it on")

    def test_a_broken_advisor_is_a_note_not_a_crash(self):
        adv = advisor_mod.ClaudeCodeAdvisor("claude", self.tmp,
                                            runner=FakeRunner(returncode=2, stderr="boom"))
        issues = [ticket(2, "Mystery work", []), ticket(3, "Other mystery", [])]
        notes = []
        proposal = propose(self.tmp, self.settings, _result(issues), files=self.files,
                           advisor=adv, notes=notes)
        self.assertEqual(len(notes), 1)
        self.assertIn("boom", notes[0])
        self.assertEqual({b.ref for b in proposal.unplaced}, {"2", "3"})
        self.assertEqual(adv.asked, ["2"], "asked once, not once per ticket")

    def test_an_answer_naming_nothing_real_leaves_the_ticket_unplaced(self):
        adv = advisor_mod.ClaudeCodeAdvisor(
            "claude", self.tmp, runner=FakeRunner('{"paths": ["made/up/**"]}'))
        proposal = propose(self.tmp, self.settings, _result([ticket(2, "Mystery", [])]),
                           files=self.files, advisor=adv)
        self.assertEqual([b.ref for b in proposal.unplaced], ["2"])



class TestAnchoringNewWork(unittest.TestCase):
    """#71: a ticket for new work names files that do not exist yet.

    The model may name them. What reaches the draft is the nearest directory that does
    exist, widened to a glob — still something real, never an invention. What it cannot
    be anchored to anything is dropped, and the drop is said, not swallowed.
    """

    FILES = [
        "src/components/settings/Panel.tsx",
        "src/components/App.tsx",
        "src/hooks/useAuth.ts",
        "src/index.ts",
        "README.md",
    ]

    def _advise(self, *paths):
        payload = '{"paths": [' + ", ".join(f'"{p}"' for p in paths) + "]}"
        return advisor_mod.ClaudeCodeAdvisor("claude", Path("."), runner=FakeRunner(payload))

    def test_a_new_file_becomes_its_existing_directory(self):
        adv = self._advise("src/components/settings/ThemeToggle.tsx", "src/hooks/useTheme.ts")
        proposal = adv.propose("9", "Theme toggle", "body", self.FILES)
        self.assertEqual(proposal.paths, ("src/components/settings/**", "src/hooks/**"))
        self.assertEqual(proposal.widened, (
            ("src/components/settings/ThemeToggle.tsx", "src/components/settings/**"),
            ("src/hooks/useTheme.ts", "src/hooks/**"),
        ))
        self.assertEqual(proposal.dropped, ())
        self.assertIs(adv.last_proposal, proposal)
        self.assertEqual(adv.propose_paths("9", "Theme toggle", "body", self.FILES),
                         proposal.paths, "the old entry point returns the same list")

    def test_a_missing_parent_walks_up_to_the_grandparent(self):
        proposal = advisor_mod.anchor_paths(
            ("src/components/theme/ThemeToggle.tsx",), self.FILES)
        self.assertEqual(proposal.paths, ("src/components/**",))
        self.assertEqual(proposal.widened,
                         (("src/components/theme/ThemeToggle.tsx", "src/components/**"),))

    def test_nothing_widens_to_a_top_level_container(self):
        # `src` exists, but `src/**` is the project, not a boundary.
        proposal = advisor_mod.anchor_paths(
            ("src/theme/ThemeToggle.tsx", "lib/new/thing.ts", "NewFile.ts"), self.FILES)
        self.assertEqual(proposal.paths, ())
        self.assertEqual(proposal.widened, ())
        self.assertEqual([orig for orig, _ in proposal.dropped],
                         ["src/theme/ThemeToggle.tsx", "lib/new/thing.ts", "NewFile.ts"])
        for _, reason in proposal.dropped:
            self.assertTrue(reason, "a drop carries its reason")
        self.assertIn("src", dict(proposal.dropped)["src/theme/ThemeToggle.tsx"])

    def test_every_path_written_matches_something_real(self):
        suggested = ("src/components/settings/ThemeToggle.tsx", "src/hooks/useTheme.ts",
                     "src/components/theme/Toggle.tsx", "src/theme/x.ts", "made/up/**",
                     "src/hooks/useAuth.ts", "src/components/**")
        proposal = advisor_mod.anchor_paths(suggested, self.FILES)
        self.assertTrue(proposal.paths)
        self.assertEqual(advisor_mod.keep_real_paths(proposal.paths, self.FILES),
                         proposal.paths, "keep_real_paths' guarantee survives the widening")
        for path in proposal.paths:
            self.assertTrue(any(advisor_mod.LaneEngine.match_glob(f, path) for f in self.FILES),
                            path)

    def test_an_existing_file_is_kept_verbatim(self):
        proposal = advisor_mod.anchor_paths(
            ("src/hooks/useAuth.ts", "src/components/settings/**"), self.FILES)
        self.assertEqual(proposal.paths, ("src/hooks/useAuth.ts", "src/components/settings/**"))
        self.assertEqual(proposal.widened, ())
        self.assertEqual(proposal.dropped, ())

    def test_duplicate_widening_is_written_once(self):
        proposal = advisor_mod.anchor_paths(
            ("src/hooks/useTheme.ts", "src/hooks/useColour.ts", "src/hooks/**"), self.FILES)
        self.assertEqual(proposal.paths, ("src/hooks/**",))
        self.assertEqual(proposal.widened, (
            ("src/hooks/useTheme.ts", "src/hooks/**"),
            ("src/hooks/useColour.ts", "src/hooks/**"),
        ), "both are recorded even though one glob is written")

    def test_the_prompt_allows_files_that_do_not_exist_yet(self):
        prompt = advisor_mod.build_prompt("9", "Theme toggle", "body", self.FILES)
        self.assertIn("do not exist yet", prompt)
        self.assertIn(f"At most {advisor_mod.MAX_PATHS}", prompt)

class TestConfiguration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _load(self, divide):
        cfg = Config.default("p").to_dict()
        cfg["divide"] = divide
        d = self.tmp / ".lanekeeper"
        d.mkdir(exist_ok=True)
        (d / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
        return load_config(self.tmp)

    def test_claude_code_is_accepted_and_round_trips(self):
        cfg = self._load({"advisor": "claude-code", "advisor_command": "/opt/claude"})
        self.assertEqual(cfg.divide.advisor, "claude-code")
        self.assertEqual(cfg.divide.advisor_command, "/opt/claude")
        save_config(cfg, self.tmp)
        self.assertEqual(load_config(self.tmp).divide.advisor_command, "/opt/claude")

    def test_an_unknown_advisor_still_fails_the_load(self):
        with self.assertRaises(InvalidDivideSettingError):
            self._load({"advisor": "gpt"})


if __name__ == "__main__":
    unittest.main()
