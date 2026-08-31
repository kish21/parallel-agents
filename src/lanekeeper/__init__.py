"""Lanekeeper — Multi-Agent Coordination and Safety Tooling."""

from pathlib import Path

try:  # Python 3.8+
    from importlib.metadata import PackageNotFoundError, version as _installed_version
except ImportError:  # pragma: no cover - not reachable under requires-python >= 3.9
    PackageNotFoundError = Exception  # type: ignore[assignment,misc]
    _installed_version = None  # type: ignore[assignment]


def _read_version() -> str:
    """Resolves the version without declaring it a third time.

    The number lives in pyproject.toml, and CI asserts the VERSION file agrees with it.
    Hardcoding a literal here is what let the package report 0.1.0 while the project was
    at 0.6.0: a stale constant nothing compared to anything.

    The VERSION file is consulted first, and it answers in exactly one situation — a
    source checkout, where it sits two directories above this file and is the truth. It
    is deliberately not shipped in the wheel, so an installed package never finds one
    (`parents[2]` there is the environment directory) and falls through to its own
    metadata. That ordering matters: an editable install carries `egg-info` generated at
    install time, which goes stale the moment the version is bumped, and reading it in a
    source tree reported a version the tree had not been at for five releases.
    """
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass

    if _installed_version is not None:
        try:
            return _installed_version("lanekeeper")
        except PackageNotFoundError:
            pass

    return "0+unknown"


__version__ = _read_version()

__all__ = ["__version__"]
