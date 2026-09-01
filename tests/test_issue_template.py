"""The ticket template is the input contract for dividing work, so it is guarded.

A lane is a feature slice, not a technology layer (#23). The templates used to teach the
opposite: `Lane` was a dropdown offering interface/service/data/platform, which is not a
wording slip but a structural commitment — layers are the only lane names that generalise
across projects, so any fixed enum ends up teaching them. The fix is free text, and this
file is what stops the dropdown coming back.

The other half is `Allowed File Paths`. Under the settled design a lane may be a single
ticket, bounded by that ticket's own paths, so a ticket filed without them has nothing
for the merge gate to enforce. Its absence removes a safety guarantee silently, which is
exactly the kind of regression that deserves a test rather than a review.

See docs/ticket-template.md. Step 2 (#38) is the first thing that will parse these
fields; until then this file is the only thing holding the contract.
"""

import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

#: The four copies. The `templates/` pair is what ships to users and is copied by hand
#: into their projects; the `.github/` pair is this repository's own. Nothing in code or
#: CI copies one to the other, and they have drifted once already.
TEMPLATES = {
    "task (this repo)": REPO / ".github" / "ISSUE_TEMPLATE" / "task.yml",
    "bug (this repo)": REPO / ".github" / "ISSUE_TEMPLATE" / "bug.yml",
    "task (shipped)": REPO / "templates" / "issue-template-task.yml",
    "bug (shipped)": REPO / "templates" / "issue-template-bug.yml",
}

#: The pairs that must agree on their contract, whatever their prose says.
COPY_PAIRS = (("task (this repo)", "task (shipped)"),
              ("bug (this repo)", "bug (shipped)"))

#: Named rather than inferred, so that restoring the dropdown fails loudly instead of
#: passing under some cleverer rule that a future edit happens to satisfy.
LAYER_WORDS = ("interface", "service", "data", "platform",
               "backend", "frontend", "infra")


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def fields(form):
    """The body elements that collect an answer, by id. Markdown blocks have no id."""
    return {el["id"]: el for el in form["body"] if el.get("id")}


def required(field):
    return bool(field.get("validations", {}).get("required", False))


def text_of(field):
    """Everything the user is shown for one field, lowercased."""
    attrs = field.get("attributes", {})
    parts = [str(attrs.get(key, "")) for key in ("label", "description", "placeholder")]
    parts += [str(opt) for opt in attrs.get("options", [])]
    return " ".join(parts).lower()


class TemplateShape(unittest.TestCase):
    """Each file is a valid GitHub issue form."""

    def test_parses_as_an_issue_form(self):
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                self.assertTrue(path.is_file(), f"{path} is missing")
                form = load(path)
                for key in ("name", "description", "body"):
                    self.assertIn(key, form)
                self.assertTrue(form["body"])
                for element in form["body"]:
                    self.assertIn("type", element)


class AllowedFilePaths(unittest.TestCase):
    """The boundary field. Its absence is the regression that matters.

    A ticket without it can still be picked as a one-ticket lane, and then there is
    nothing to enforce: no boundary means no gate, so the agent ships a safety guarantee
    that quietly does not exist.
    """

    def test_present_and_required_everywhere(self):
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                field = fields(load(path)).get("allowed_paths")
                self.assertIsNotNone(field, f"{name} does not ask for file paths")
                self.assertTrue(required(field),
                                f"{name} asks for file paths but does not require them")

    def test_states_one_path_per_line(self):
        """#38 has to parse this. An unstated format means #38 guesses."""
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                text = text_of(fields(load(path))["allowed_paths"])
                self.assertIn("per line", text,
                              f"{name} does not say how to write the paths")


class LaneIsAFeatureNotALayer(unittest.TestCase):
    """The #23 guard: the layer model must not come back."""

    def test_lane_is_free_text_not_a_dropdown(self):
        """A fixed list of lane names can only ever be a list of layers.

        Real lane names are project-specific -- checkout, search, billing, voiceover --
        so no enum in a shipped template can know them.
        """
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                field = fields(load(path))["lane"]
                self.assertEqual(field["type"], "input",
                                 f"{name} offers a fixed list of lanes")
                self.assertNotIn("options", field.get("attributes", {}))

    def test_lane_is_optional(self):
        """A required lane asks the filer to guess the grouping before step 2 has
        proposed one, and a guessed lane name is worse input than a blank one."""
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                self.assertFalse(required(fields(load(path))["lane"]),
                                 f"{name} forces a lane name to be guessed")

    def test_lane_never_offers_a_layer_as_the_answer(self):
        """The label and the rule may name layers; a suggested answer must not be one.

        The prose has to say "not backend" to teach anything, so this checks only the
        places a layer would be presented as a usable answer: `placeholder`, and
        `value`, which GitHub pre-fills into the field so it becomes what every filer
        submits unless they delete it.
        """
        for name, path in TEMPLATES.items():
            attrs = fields(load(path))["lane"].get("attributes", {})
            for key in ("placeholder", "value"):
                with self.subTest(f"{name}: {key}"):
                    suggested = str(attrs.get(key, "")).strip().lower()
                    self.assertNotIn(suggested, LAYER_WORDS,
                                     f"{name} suggests '{suggested}' as a lane name")

    def test_allowed_paths_example_spans_the_stack(self):
        """The example is the strongest teaching in the form, so it must not quietly
        contradict the prose above it by showing one side of the stack."""
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                lines = [ln.strip().split("/")[0].lower()
                         for ln in str(fields(load(path))["allowed_paths"]
                                       .get("attributes", {}).get("placeholder", "")).splitlines()
                         if ln.strip()]
                self.assertTrue(lines, f"{name} shows no example paths")
                self.assertGreater(
                    len(set(lines)), 1,
                    f"{name} shows an example confined to '{lines[0]}' -- a layer slice")

    def test_lane_teaches_the_feature_slice_rule(self):
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                text = text_of(fields(load(path))["lane"])
                self.assertIn("feature", text, f"{name} does not say a lane is a feature")
                self.assertIn("not a technology layer", text,
                              f"{name} does not say a lane is not a layer")

    def test_lane_says_a_blank_one_is_fine(self):
        """Optional is not enough if the form does not say so; a blank field reads as an
        omission unless the user is told it is an expected answer."""
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                text = text_of(fields(load(path))["lane"])
                self.assertIn("blank", text,
                              f"{name} does not tell the user a blank lane is fine")


class DoesNotTellAnyoneToMoveTheirFiles(unittest.TestCase):
    """Lanes are globs and carve a feature slice out of a messy tree without moving a
    file. Telling users to restructure locks out the legacy projects that need this
    most, so the form must not even hint at it."""

    def test_no_restructuring_advice(self):
        banned = ("restructure", "reorganise", "reorganize", "rename your", "move your")
        for name, path in TEMPLATES.items():
            with self.subTest(name):
                text = path.read_text(encoding="utf-8").lower()
                for phrase in banned:
                    self.assertNotIn(phrase, text, f"{name} says '{phrase}'")


class CopiesAgree(unittest.TestCase):
    """The shipped and repository copies drifted once already.

    Prose may differ -- the shipped ones carry generic examples and this repository's
    carry its own. The contract may not.
    """

    def test_same_fields_and_same_required_flags(self):
        for own, shipped in COPY_PAIRS:
            with self.subTest(f"{own} vs {shipped}"):
                a, b = fields(load(TEMPLATES[own])), fields(load(TEMPLATES[shipped]))
                self.assertEqual(sorted(a), sorted(b), "the copies ask for different things")
                for field_id in a:
                    self.assertEqual(a[field_id]["type"], b[field_id]["type"],
                                     f"'{field_id}' is a different kind of field")
                    self.assertEqual(required(a[field_id]), required(b[field_id]),
                                     f"'{field_id}' is required in one copy but not the other")


class StillLooksLikeATemplateToTheCli(unittest.TestCase):
    """`cli._has_issue_template` feeds a hint step 1 prints. It only tests for
    existence, but that is worth pinning: the edits must not have moved the files."""

    def test_cli_still_finds_them(self):
        from lanekeeper.cli import _has_issue_template
        self.assertTrue(_has_issue_template(REPO))


if __name__ == "__main__":
    unittest.main()
