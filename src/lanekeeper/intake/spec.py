"""Finding the description of the product that the issues are compared against.

Lanekeeper cannot judge "are all the features covered?" on its own — it has no idea
what the product is meant to do. It needs something to compare the issues against, and
the order of preference is not arbitrary:

1. `PRODUCT.md` — product-playbook's own output, whose Scope and Plan sections list the
   features. This is the intended path and the reason the two tools are a pair.
2. A README or other document describing the product.
3. Nothing — in which case coverage is not judged, and that is said plainly.

The parse is deliberately dumb and deterministic: markdown headings naming a configured
section, and the bullet list underneath. A heuristic that guessed harder would produce
confident feature lists from documents that do not contain one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .models import Feature, ProductSpec, SpecSource

#: `## Scope`, `### Plan — milestones`, `# Features`.
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
#: `- item`, `* item`, `1. item`, and task-list boxes.
_BULLET = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*\S)\s*$")
#: Trailing explanation after a feature's name. The dashes need a space in front of them
#: (a hyphenated name is one word); a colon does not, because `Billing: Stripe checkout`
#: is how most people write it.
_TRAILER = re.compile(r"\s+[-–—]\s+|\s*:\s+")
_MARKUP = re.compile(r"[`*_]+")
#: ``` or ~~~ opening or closing a code block. A `# comment` inside one is not a heading.
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def resolve_spec(root: Path, settings) -> ProductSpec:
    """Returns the first configured document that actually yields features.

    A file that exists but has no matching section is not an answer: it falls through
    to the next candidate, and the files considered are reported either way so a bad
    read is visible rather than silent.
    """
    considered: List[str] = []
    for candidate in settings.spec_sources:
        if not _is_inside_project(candidate):
            # A configured path is joined onto the repository root, so an absolute path
            # or one climbing out of it would read a file outside the project. Refused
            # the same way `paths` refuses it for lanekeeper's own directory.
            continue
        path = root / candidate
        if not path.is_file():
            continue
        considered.append(candidate)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        features = extract_features(text, settings.spec_sections)
        if features:
            return ProductSpec(
                source=_source_of(candidate),
                path=candidate,
                features=tuple(features),
                considered=tuple(considered),
            )
    return ProductSpec(source=SpecSource.NONE, path=None, features=(),
                       considered=tuple(considered))


def _is_inside_project(candidate: str) -> bool:
    path = Path(candidate)
    return not (path.is_absolute() or path.drive or path.root or ".." in path.parts)


def _source_of(candidate: str) -> SpecSource:
    """`PRODUCT.md` anywhere is the playbook's output; anything else is a document."""
    return (SpecSource.PRODUCT_MD
            if Path(candidate).name.lower() == "product.md"
            else SpecSource.DOCS)


def extract_features(text: str, section_names: List[str]) -> List[Feature]:
    """Bullets under any heading naming one of the configured sections.

    Collection stops at the next heading of the same or a higher level, so a Scope
    section's sub-heading is included and the section after it is not. Fenced code
    blocks are skipped whole: a `# comment` inside one is not a heading.
    """
    wanted = [s.strip().lower() for s in section_names if s.strip()]
    features: List[Feature] = []
    seen = set()

    # `section_level` is the depth of the wanted heading currently being read.
    # `suppress_level` is the depth of an exclusion heading inside it — an "Out of
    # scope" list is commonly a sub-heading of the very section it excludes from, and
    # a sibling sub-section after it is back in scope, so suppression has to end.
    section_level: Optional[int] = None
    suppress_level: Optional[int] = None
    in_fence = False

    for raw_line in text.splitlines():
        if _FENCE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            # A shell comment inside a code block is not a heading, and treating it as
            # one silently swallowed every feature listed after it.
            continue

        heading = _HEADING.match(raw_line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip().lower()
            if suppress_level is not None and level <= suppress_level:
                suppress_level = None
            if section_level is not None and level <= section_level:
                section_level = None
            if _is_exclusion(title):
                suppress_level = level
                continue
            if any(_names_section(title, name) for name in wanted):
                section_level = level
            continue

        if section_level is None or suppress_level is not None:
            continue

        bullet = _BULLET.match(raw_line)
        if not bullet:
            continue
        name = _feature_name(bullet.group(1))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        features.append(Feature(name=name, source_line=raw_line.strip()))
    return features


def _is_exclusion(heading_title: str) -> bool:
    """Headings that introduce what the product deliberately does NOT do."""
    return (heading_title.startswith("out of ")
            or heading_title.startswith("not ")
            or heading_title.startswith("non-goal")
            or heading_title.startswith("nongoal")
            or "out of scope" in heading_title)


def _names_section(heading_title: str, section: str) -> bool:
    """Whether a heading names a wanted section.

    Matched on whole words, so `Scope` matches "Scope" and "Scope (locked)" without
    matching every heading that happens to contain the letters.
    """
    words = re.findall(r"[a-z0-9]+", heading_title)
    return section in words or heading_title == section


def _feature_name(text: str) -> str:
    """The name of the feature, without the sentence explaining it."""
    cleaned = _LINK.sub(r"\1", text)
    cleaned = _MARKUP.sub("", cleaned).strip()
    # Cut an explanatory trailer: "Billing — Stripe checkout and invoices" is one
    # feature called Billing, not a feature called the whole sentence.
    cleaned = _TRAILER.split(cleaned, maxsplit=1)[0].strip()
    cleaned = cleaned.split(". ")[0].strip().rstrip(".")
    return cleaned


def tokens(text: str) -> Tuple[str, ...]:
    """Comparable words, shared by the spec and the issues so both are read alike."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return tuple(w for w in words if w not in _STOPWORDS and len(w) > 1)


#: Words carrying no signal about which feature something is. Not configuration: this
#: is a property of English, not of a project's judgement.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for", "from",
    "has", "have", "in", "into", "is", "it", "its", "not", "of", "on", "or", "should",
    "that", "the", "their", "then", "there", "this", "to", "up", "was", "when",
    "which", "with", "will", "you", "your",
}
