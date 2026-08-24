"""Phase 8b: the rename script.

The case that makes this a script instead of sed: `stack-arr-import` is a
prefix of `stack-arr-import-all`, `stack-arr-import-backlog`,
`stack-arr-import-candidates` and `stack-arr-import-starvation`. A naive
substring replace turns stack-arr-import-all into <new-name>-all and silently
breaks four commands plus every doc that mentions them.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/fish-rename.py"


@pytest.fixture(scope="module")
def renamer():
    spec = importlib.util.spec_from_file_location("_script_fish_rename", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_script_fish_rename"] = module
    spec.loader.exec_module(module)
    return module


def test_exact_name_is_replaced(renamer):
    out = renamer.rename_text("run stack-arr-blocklist-clear now",
                              {"stack-arr-blocklist-clear": "stack-arr-clear-blocklist"})
    assert out == "run stack-arr-clear-blocklist now"


def test_longer_name_with_the_same_prefix_is_untouched(renamer):
    """The whole reason this file exists."""
    text = "stack-arr-import and stack-arr-import-all and stack-arr-import-backlog"
    out = renamer.rename_text(text, {"stack-arr-import": "stack-arr-pull"})
    assert out == "stack-arr-pull and stack-arr-import-all and stack-arr-import-backlog"


def test_name_inside_a_path_or_quotes_is_replaced(renamer):
    text = 'fish-functions/stack-plex-rss-import.fish and "stack-plex-rss-import"'
    out = renamer.rename_text(text, {"stack-plex-rss-import": "stack-plex-import-rss"})
    assert out == 'fish-functions/stack-plex-import-rss.fish and "stack-plex-import-rss"'


def test_name_as_part_of_a_longer_word_is_untouched(renamer):
    out = renamer.rename_text("xstack-plex-rss-importer",
                              {"stack-plex-rss-import": "stack-plex-import-rss"})
    assert out == "xstack-plex-rss-importer"


def test_multiple_renames_in_one_pass_do_not_cascade(renamer):
    """A -> B and B -> C must not turn A into C."""
    out = renamer.rename_text("stack-a stack-b", {"stack-a": "stack-b", "stack-b": "stack-c"})
    assert out == "stack-b stack-c"


def test_every_rename_target_is_a_new_name(renamer):
    """Guards the map itself: a typo that maps two old names onto the same new
    one would silently delete a command."""
    assert len(set(renamer.RENAMES.values())) == len(renamer.RENAMES)
    assert not set(renamer.RENAMES) & set(renamer.RENAMES.values())


def _tree(tmp_path):
    (tmp_path / "fish-functions").mkdir()
    (tmp_path / "fish-functions/stack-x.fish").write_text("x")
    (tmp_path / "fish-functions/README.md").write_text("x")
    (tmp_path / "control-panel/static").mkdir(parents=True)
    (tmp_path / "control-panel/static/commands.json").write_text("[]")
    (tmp_path / "control-panel/services").mkdir(parents=True)
    (tmp_path / "control-panel/services/router.py").write_text("x")
    (tmp_path / ".claude/skills/demo").mkdir(parents=True)
    (tmp_path / ".claude/skills/demo/SKILL.md").write_text("x")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a_router.py").write_text("x")
    (tmp_path / "tests/test_fish_naming.py").write_text("x")
    (tmp_path / "docs/superpowers/specs").mkdir(parents=True)
    (tmp_path / "docs/superpowers/specs/design.md").write_text("x")
    for name in ("README.md", "STACK.md", "AGENTS.md", "PLANS.md"):
        (tmp_path / name).write_text("x")
    return tmp_path


def test_targets_include_every_live_reference_surface(renamer, tmp_path):
    """Routers name .fish files in comments and router tests name the command
    they cover. Both were missed by the first draft of targets()."""
    found = {p.relative_to(tmp_path).as_posix() for p in renamer.targets(_tree(tmp_path))}
    assert {"fish-functions/stack-x.fish", "fish-functions/README.md",
            "control-panel/static/commands.json", "control-panel/services/router.py",
            ".claude/skills/demo/SKILL.md", "tests/test_a_router.py",
            "README.md", "STACK.md", "AGENTS.md"} <= found


def test_targets_exclude_the_files_that_describe_the_rename(renamer, tmp_path):
    """The spec's table reads `old -> new`. Rewriting it turns both sides into
    the new name and destroys the only record of what changed."""
    found = {p.relative_to(tmp_path).as_posix() for p in renamer.targets(_tree(tmp_path))}
    assert not found & {"PLANS.md", "tests/test_fish_naming.py",
                        "docs/superpowers/specs/design.md"}


def test_targets_are_unique(renamer, tmp_path):
    """README.md matches both the root loop and no other glob; a duplicate
    would rewrite the same file twice and double-count the edit lines."""
    found = renamer.targets(_tree(tmp_path))
    assert len(found) == len(set(found))
