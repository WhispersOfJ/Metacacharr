"""Phase 8a: the invariant that keeps fish-functions/ the only source of truth.

This test is why the drift cannot come back. It fails the commit if any
stack-* function on this host is a plain copy instead of a symlink into the
repo, or if either side has a name the other does not.

It is host-coupled by design: it asserts something about the live shell
environment, not about repo contents. On a machine with no ~/.config/fish it
skips rather than fails, so CI and a fresh clone stay green.
"""
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent / "fish-functions"
INSTALLED_DIR = Path.home() / ".config/fish/functions"

pytestmark = pytest.mark.skipif(
    not INSTALLED_DIR.is_dir(),
    reason="no fish function directory on this host",
)


def _names(directory: Path) -> set[str]:
    return {path.name for path in directory.glob("stack-*.fish")}


def test_every_installed_stack_function_is_a_symlink_into_the_repo():
    offenders = []
    for path in sorted(INSTALLED_DIR.glob("stack-*.fish")):
        if not path.is_symlink():
            offenders.append(f"{path.name}: plain copy, not a link")
        elif path.resolve() != (REPO_DIR / path.name).resolve():
            offenders.append(f"{path.name}: links to {path.resolve()}")
    assert not offenders, (
        "Run scripts/fish-functions-install.py. Offenders:\n  " + "\n  ".join(offenders))


def test_repo_and_installed_name_sets_are_identical():
    repo, installed = _names(REPO_DIR), _names(INSTALLED_DIR)
    assert repo == installed, (
        f"repo-only: {sorted(repo - installed)}\n"
        f"installed-only: {sorted(installed - repo)}\n"
        "Run scripts/fish-functions-install.py.")


def test_no_dangling_links():
    dangling = [p.name for p in INSTALLED_DIR.iterdir()
                if p.name.startswith("stack-") and p.is_symlink() and not p.exists()]
    assert not dangling, f"dangling links: {dangling}"
