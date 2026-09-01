"""Reading a feature name out of a path.

This is the whole of the difference between the model this project argues for and the
one it used to ship. `layout.ROLE_BY_DIR_NAME` asks "what kind of code is this?" and
answers `backend`. This asks "which feature is this?" and answers `checkout`, from
`backend/app/domains/checkout/service.py` and `frontend/src/components/checkout/Cart.tsx`
alike — which is why the two paths end up in one lane here and in two lanes there.

A directory whose name says what kind of code it holds — `src`, `api`, `components` —
names no feature, so it is skipped. The lists live in configuration, because no fixed
list of English directory names is right for every repository.
"""

from __future__ import annotations

import re
from typing import List, Sequence

#: Word-forms that describe what a file is rather than which feature it serves. These
#: are suffixes of English identifiers (`ProductPage`, `checkoutService`), not project
#: structure — the structural lists are `divide.containers` and `divide.generic_dirs`
#: in the configuration, and both are also applied here.
_ROLE_WORDS = {
    "page", "pages", "view", "views", "screen", "service", "services", "client",
    "server", "controller", "handler", "provider", "adapter", "repository", "repo",
    "store", "slice", "reducer", "context", "hook", "index", "main", "app", "test",
    "tests", "spec", "specs", "util", "utils", "helper", "helpers", "type", "types",
    "model", "models", "schema", "schemas", "api", "route", "routes", "router", "form",
    "list", "modal", "card", "panel", "table", "button", "new", "old", "base", "impl",
    "use", "get", "set", "create", "update", "delete", "fetch", "handle", "with",
}

#: Splits `ProductPage`, `product_page`, `product-page` and `productPage` alike.
_WORDS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|[0-9]+")

#: A path segment that is a wildcard names nothing.
_WILDCARD = re.compile(r"[*?\[\]]")


def candidates(path: str, settings) -> List[str]:
    """Every feature name a single path could be about, most specific first.

    Order matters: the deepest meaningful directory is the most specific statement the
    path makes, and a filename is more specific still only when the directories above
    it said nothing.
    """
    cleaned = (path or "").replace("\\", "/").strip("/")
    if not cleaned:
        return []

    segments = cleaned.split("/")
    skip = _skip_words(settings)
    feature_containers = {c.lower() for c in settings.feature_containers}

    names: List[str] = []
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        looks_like_file = is_last and "." in segment and not segment.endswith("/**")
        if _WILDCARD.search(segment) or segment.startswith("."):
            continue
        if looks_like_file:
            continue
        lowered = segment.lower()
        # A child of `domains/` or `features/` is a feature by construction, even when
        # its name would otherwise read as a bucket.
        parent = segments[index - 1].lower() if index else ""
        if lowered in skip and parent not in feature_containers:
            continue
        names.append(lowered)

    # Deepest directory first: `domains/checkout` says "checkout" more than "domains".
    names.reverse()

    last = segments[-1]
    if "." in last and not _WILDCARD.search(last):
        stem_name = from_filename(last, settings)
        if stem_name:
            names.append(stem_name)

    return _unique(names)


def best(path: str, settings) -> str:
    """The single most specific feature name a path offers, or nothing."""
    found = candidates(path, settings)
    return found[0] if found else ""


def words_in_filename(filename: str, settings) -> List[str]:
    """The feature-shaped words in a filename: `useAuth.ts` → `["auth"]`.

    A list, because a filename can carry more than one word and joining them produces
    a word that is in no project: `useAuth` is about `auth`, and `useauth` is about
    nothing. `use` is dropped with the other role words — it says the file is a hook,
    not which feature the hook serves.
    """
    stem = filename.split("/")[-1].split(".")[0]
    skip = _skip_words(settings)
    words = [w.lower() for w in _WORDS.findall(stem)]
    return [w for w in words
            if w not in _ROLE_WORDS and w not in skip and not w.isdigit() and len(w) > 2]


def from_filename(filename: str, settings) -> str:
    """The one feature a filename is most likely about, or nothing.

    The longest surviving word: `ProductGrid` is about the product, `useAuth` about
    auth, `LoginPage` about login. Nothing at all is the honest answer for `index.ts`
    and `service.py`, where every word describes a role.
    """
    words = words_in_filename(filename, settings)
    return max(words, key=len) if words else ""


def from_text(text: str, settings) -> List[str]:
    """Feature-shaped words in a ticket title, used only to match against names that
    already exist. Nothing is ever named from prose alone."""
    skip = _skip_words(settings)
    words = [w.lower() for w in _WORDS.findall(text or "")]
    return _unique([w for w in words
                    if len(w) > 2 and w not in _ROLE_WORDS and w not in skip])


def slug(text: str) -> str:
    """A lane name from free text, in the shape the lane file uses."""
    parts = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    return "-".join(parts)[:40].strip("-")


def _skip_words(settings) -> set:
    return ({c.lower() for c in settings.containers}
            | {g.lower() for g in settings.generic_dirs})


def _unique(values: Sequence[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
