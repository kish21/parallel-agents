"""The lanes, written out as the file GitHub already enforces — issue #42.

Three properties carry this feature, and each one is a way it can be silently wrong:
the ordering (CODEOWNERS reads last-match-wins, the opposite of the lane engine), the
managed block (a hand-written section has to survive), and the size limit (over it,
GitHub stops loading the file and says nothing).
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import codeowners as co
from lanekeeper.config import (CodeownersConfig, InvalidLaneError, LaneConfig,
                               generate_default_config, load_config, save_config)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


def _config(**kw):
    cfg = generate_default_config("Shop")
    cfg.lanes = {
        "checkout": LaneConfig(name="checkout",
                               allow=["backend/checkout/**", "frontend/src/**"]),
        "shared-ui": LaneConfig(name="shared-ui", allow=["frontend/src/store/**"],
                                shared=True),
    }
    for key, value in kw.items():
        setattr(cfg, key, value)
    return cfg


class TestTranslation(unittest.TestCase):
    """A lane pattern is matched from the repository root; an unanchored CODEOWNERS
    pattern matches at every level. Everything else follows from that."""

    def test_a_plain_pattern_is_anchored(self):
        self.assertEqual(co.translate("backend/app/**"), "/backend/app/**")

    def test_an_already_anchored_pattern_is_left_alone(self):
        self.assertEqual(co.translate("/backend/app/**"), "/backend/app/**")

    def test_a_deliberately_unanchored_pattern_stays_unanchored(self):
        # `**/` means "at any level" in both systems; anchoring it would change what
        # the lane said.
        self.assertEqual(co.translate("**/vendor/**"), "**/vendor/**")

    def test_a_single_star_is_anchored_not_widened(self):
        # The whole reason anchoring matters: unanchored, this would also claim
        # vendor/other/src/x.ts and route somebody else's review here.
        self.assertEqual(co.translate("src/*.ts"), "/src/*.ts")

    def test_character_ranges_are_refused_with_the_reason(self):
        with self.assertRaises(co.UntranslatablePattern) as caught:
            co.translate("src/[ab]/**")
        self.assertIn("character ranges", caught.exception.reason)

    def test_negation_is_refused(self):
        with self.assertRaises(co.UntranslatablePattern):
            co.translate("!src/**")

    def test_question_marks_are_refused(self):
        with self.assertRaises(co.UntranslatablePattern):
            co.translate("src/?.ts")


class TestOrdering(unittest.TestCase):
    """The property this feature lives or dies on: last match wins."""

    def test_the_shared_zone_comes_after_the_lane_that_overlaps_it(self):
        plan = co.build_plan(_config(), ["@kish21"])
        names = [r.lane for r in plan.rules]
        self.assertLess(names.index("checkout"), names.index("shared-ui"),
                        "a feature lane written after the shared zone would take it")

    def test_the_policy_comes_last_of_all(self):
        plan = co.build_plan(_config(), ["@kish21"])
        self.assertEqual(plan.rules[-1].lane, "policy")

    def test_the_shared_zone_wins_in_the_rendered_file(self):
        # 'checkout' claims frontend/src/**, the shared store sits inside it, and the
        # file has to hand the store to the shared zone's owner.
        cfg = _config()
        cfg.lanes["shared-ui"].owner = ["@stewards"]
        text = co.render_block(co.build_plan(cfg, ["@kish21"]), "config.yaml")
        store = text.index("/frontend/src/store/**")
        feature = text.index("/frontend/src/**")
        self.assertLess(feature, store)
        self.assertIn("@stewards", text[store:store + 80])


class TestOwners(unittest.TestCase):
    def test_a_lane_owner_beats_the_default(self):
        cfg = _config()
        cfg.lanes["checkout"].owner = ["@a", "@b"]
        plan = co.build_plan(cfg, ["@default"])
        rule = next(r for r in plan.rules if r.lane == "checkout")
        self.assertEqual(rule.owners, ("@a", "@b"))

    def test_a_lane_nobody_owns_is_left_out_not_invented(self):
        plan = co.build_plan(_config(), [])
        self.assertEqual(plan.rules, [])
        self.assertIn("checkout", plan.unowned_lanes)

    def test_one_handle_or_a_list_both_load(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(root), ignore_errors=True)
        cfg = _config(codeowners=CodeownersConfig(default_owner=["@kish21"]))
        cfg.lanes["checkout"].owner = ["@team"]
        save_config(cfg, root)
        loaded = load_config(root)
        self.assertEqual(loaded.lanes["checkout"].owner, ["@team"])
        self.assertEqual(loaded.codeowners.default_owner, ["@kish21"])

    def test_a_bad_owner_value_is_refused(self):
        from lanekeeper.config import _parse_lane
        with self.assertRaises(InvalidLaneError):
            _parse_lane("x", {"allow": ["a/**"], "owner": {"who": "me"}})


class TestTheManagedBlock(unittest.TestCase):
    def test_hand_written_rules_survive_on_both_sides(self):
        block = co.render_block(co.build_plan(_config(), ["@kish21"]), "config.yaml")
        existing = "# mine\n/docs/** @writers\n"
        merged = co.merge(existing, block)
        merged = co.merge(merged + "\n*.md @writers\n", block)
        self.assertIn("/docs/** @writers", merged)
        self.assertIn("*.md @writers", merged)
        self.assertEqual(merged.count(co.BEGIN), 1)

    def test_rewriting_is_idempotent(self):
        block = co.render_block(co.build_plan(_config(), ["@kish21"]), "config.yaml")
        once = co.merge("", block)
        self.assertEqual(co.merge(once, block), once)

    def test_rules_below_the_block_are_reported_because_they_win(self):
        block = co.render_block(co.build_plan(_config(), ["@kish21"]), "config.yaml")
        text = co.merge("", block) + "\n# note\n*.md @writers\n"
        self.assertEqual(co.rules_after_block(text), ["*.md @writers"])

    def test_comments_below_the_block_are_not_rules(self):
        block = co.render_block(co.build_plan(_config(), ["@kish21"]), "config.yaml")
        self.assertEqual(co.rules_after_block(co.merge("", block) + "\n# just a note\n"), [])


class TestTheSizeLimit(unittest.TestCase):
    def test_under_the_limit_is_not_flagged(self):
        self.assertIsNone(co.too_big("small\n"))

    def test_over_the_limit_is_flagged(self):
        self.assertIsNotNone(co.too_big("x" * (co.MAX_BYTES + 1)))

    def test_the_command_refuses_rather_than_writing_a_file_github_ignores(self):
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(root), ignore_errors=True)
        _init_repo(root)
        cfg = _config()
        # One lane with enough patterns to pass 3 MB. Nothing else about it matters.
        cfg.lanes = {"huge": LaneConfig(
            name="huge", allow=[f"src/generated/module{i}/**" for i in range(90_000)])}
        save_config(cfg, root)
        res = run_cli(["codeowners", "--owner", "@kish21"], cwd=root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("limit", res.stdout + res.stderr)
        self.assertFalse((root / ".github" / "CODEOWNERS").exists(),
                         "it wrote a file GitHub would ignore entirely")


def _init_repo(root):
    for cmd in (["git", "init", "-q", "-b", "main", "."],
                ["git", "config", "user.email", "t@t.c"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=str(root), check=True, capture_output=True)
    (root / "README.md").write_text("# r\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=str(root), check=True)


class TestTheCommand(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        _init_repo(self.root)
        save_config(_config(), self.root)

    def target(self):
        return self.root / ".github" / "CODEOWNERS"

    def test_it_writes_the_file(self):
        res = run_cli(["codeowners", "--owner", "@kish21"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        text = self.target().read_text(encoding="utf-8")
        self.assertIn("/backend/checkout/**", text)
        self.assertIn("@kish21", text)

    def test_running_it_twice_changes_nothing(self):
        run_cli(["codeowners", "--owner", "@kish21"], cwd=self.root)
        first = self.target().read_text(encoding="utf-8")
        run_cli(["codeowners", "--owner", "@kish21"], cwd=self.root)
        self.assertEqual(self.target().read_text(encoding="utf-8"), first)

    def test_check_passes_when_it_matches_and_fails_when_it_drifts(self):
        run_cli(["codeowners", "--owner", "@kish21"], cwd=self.root)
        ok = run_cli(["codeowners", "--check", "--owner", "@kish21"], cwd=self.root)
        self.assertEqual(ok.returncode, 0, output_of(ok))

        self.target().write_text(
            self.target().read_text(encoding="utf-8").replace("@kish21", "@someone"),
            encoding="utf-8")
        drifted = run_cli(["codeowners", "--check", "--owner", "@kish21"], cwd=self.root)
        self.assertEqual(drifted.returncode, 1, output_of(drifted))
        self.assertIn("does not match", drifted.stdout + drifted.stderr)

    def test_check_never_writes(self):
        res = run_cli(["codeowners", "--check", "--owner", "@kish21"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertFalse(self.target().exists())

    def test_with_nobody_to_route_to_it_refuses_and_says_how(self):
        res = run_cli(["codeowners"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn("--owner", out)
        self.assertIn("default_owner", out)
        self.assertFalse(self.target().exists())

    def test_the_default_owner_in_config_is_enough_on_its_own(self):
        cfg = _config(codeowners=CodeownersConfig(default_owner=["@kish21"]))
        save_config(cfg, self.root)
        res = run_cli(["codeowners"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("@kish21", self.target().read_text(encoding="utf-8"))

    def test_the_policy_files_are_owned_last(self):
        run_cli(["codeowners", "--owner", "@kish21"], cwd=self.root)
        text = self.target().read_text(encoding="utf-8")
        self.assertIn("/.lanekeeper/config.yaml", text)
        self.assertLess(text.index("/backend/checkout/**"),
                        text.index("/.lanekeeper/config.yaml"))


class TestTheReviewFindings(unittest.TestCase):
    """Seven ways this could have been silently wrong, each reproduced before it was
    fixed. Every one of them writes a file that looks right and routes reviews wrong."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        _init_repo(self.root)

    def test_the_policy_is_routed_even_with_only_per_lane_owners(self):
        # Without a policy rule, a lane pattern as ordinary as `**/*.yaml` becomes the
        # code owner of the file that defines every lane.
        cfg = _config()
        cfg.lanes = {"cfg": LaneConfig(name="cfg", allow=["**/*.yaml"], owner=["@a"])}
        cfg.codeowners = CodeownersConfig(default_owner=["@boss"])
        text = co.render_block(co.build_plan(cfg, ["@boss"]), "config.yaml")
        self.assertLess(text.index("**/*.yaml"), text.index("/.lanekeeper/config.yaml"))

    def test_nobody_owning_the_policy_is_said_out_loud(self):
        cfg = _config()
        cfg.lanes = {"cfg": LaneConfig(name="cfg", allow=["**/*.yaml"], owner=["@a"])}
        save_config(cfg, self.root)
        res = run_cli(["codeowners"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Nobody owns the policy files", res.stdout, output_of(res))

    def test_a_configured_path_is_the_one_the_gate_lets_through(self):
        from lanekeeper.check import policy_lane_paths
        cfg = _config(codeowners=CodeownersConfig(path="CODEOWNERS"))
        self.assertIn("CODEOWNERS", policy_lane_paths(cfg))
        self.assertNotIn(".github/CODEOWNERS", policy_lane_paths(cfg))

    def test_a_configured_path_is_the_one_uninit_strips(self):
        cfg = _config(codeowners=CodeownersConfig(path="CODEOWNERS",
                                                  default_owner=["@kish21"]))
        save_config(cfg, self.root)
        self.assertEqual(run_cli(["codeowners"], cwd=self.root).returncode, 0)
        target = self.root / "CODEOWNERS"
        self.assertIn(co.BEGIN, target.read_text(encoding="utf-8"))
        res = run_cli(["uninit", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertFalse(target.exists(), "our block was left behind at the configured path")

    def test_untranslatable_everything_does_not_ask_for_an_owner_it_has(self):
        cfg = _config()
        cfg.lanes = {"odd": LaneConfig(name="odd", allow=["src/[ab]/**"], owner=["@a"])}
        save_config(cfg, self.root)
        res = run_cli(["codeowners"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn("cannot express", out)
        self.assertIn("character ranges", out)
        self.assertNotIn("no lane has an owner", out)

    def test_a_space_in_a_path_is_refused_not_written(self):
        # CODEOWNERS splits on whitespace: `/My Docs/**  @a` is the pattern `/My` owned
        # by `Docs/**` and `@a`.
        with self.assertRaises(co.UntranslatablePattern) as caught:
            co.translate("My Docs/**")
        self.assertIn("whitespace", caught.exception.reason)

    def test_a_handle_without_its_at_sign_is_refused(self):
        cfg = _config(codeowners=CodeownersConfig(default_owner=["@kish21"]))
        save_config(cfg, self.root)
        res = run_cli(["codeowners", "--owner", "kish21"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("@kish21", res.stdout + res.stderr)
        self.assertFalse((self.root / ".github" / "CODEOWNERS").exists())

    def test_an_orphan_marker_stops_rather_than_eating_the_users_lines(self):
        block = co.render_block(co.build_plan(_config(), ["@kish21"]), "config.yaml")
        with self.assertRaises(co.MalformedBlock):
            co.merge("# mine\n" + co.BEGIN + "\n/docs/** @writers\n", block)
        with self.assertRaises(co.MalformedBlock):
            co.merge(co.END + "\n/docs/** @writers\n" + co.BEGIN + "\n", block)

    def test_a_malformed_file_is_reported_and_nothing_is_written(self):
        cfg = _config(codeowners=CodeownersConfig(default_owner=["@kish21"]))
        save_config(cfg, self.root)
        target = self.root / ".github" / "CODEOWNERS"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(co.BEGIN + "\n/docs/** @writers\n", encoding="utf-8")
        res = run_cli(["codeowners"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("marker", res.stdout + res.stderr)
        self.assertIn("/docs/** @writers", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
