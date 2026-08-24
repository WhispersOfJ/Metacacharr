"""Gate tests for scripts/fish-completions-generate.py.

The generator's value is that completions cannot drift from the functions
they describe. That only holds if something fails when they do, so the
sync check here is the real test - the rest cover the parsing rules it
depends on.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_DIR = REPO_ROOT / "fish-functions"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location(
        "fish_completions_generate", REPO_ROOT / "scripts" / "fish-completions-generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path, name, body):
    p = tmp_path / f"{name}.fish"
    p.write_text(body)
    return p


# --- The sync gate ----------------------------------------------------

def test_committed_completions_match_the_functions(gen):
    """If this fails, a function changed and its completion did not.
    Run scripts/fish-completions-generate.py."""
    wanted = gen.generate(REPO_DIR)
    out_dir = REPO_DIR / gen.COMPLETIONS_DIRNAME
    existing = {p.name: p.read_text() for p in out_dir.glob("*.fish")}
    assert existing == wanted


def test_every_command_has_a_completion_file(gen):
    commands = {p.stem for p in REPO_DIR.glob("stack-*.fish")}
    completions = {p.stem for p in (REPO_DIR / gen.COMPLETIONS_DIRNAME).glob("*.fish")}
    assert commands == completions


# --- Parsing rules ----------------------------------------------------

def test_argparse_flags_become_completions(gen, tmp_path):
    p = _write(tmp_path, "stack-thing", """
function stack-thing --description 'Do a thing'
    argparse 'label=' 'anime' 'dry-run' -- $argv
end
""")
    out = gen.render(p)
    assert "-l label -r" in out, "a flag taking a value must be marked -r"
    assert "-l anime" in out
    assert "-l dry-run" in out


def test_contains_guard_becomes_positional_completion(gen, tmp_path):
    p = _write(tmp_path, "stack-thing", """
# Usage: stack-thing <a|b>
function stack-thing --description 'Do a thing'
    if not contains -- $argv[1] radarr sonarr radarr_anime sonarr_anime
        return 1
    end
end
""")
    out = gen.render(p)
    assert "-eq 1' -a 'radarr sonarr radarr_anime sonarr_anime'" in out


def test_usage_header_supplies_choices_when_no_guard_exists(gen, tmp_path):
    """The converted commands validate through __stack_arr_app, so there is
    no `contains` list left to read - the header is the only source."""
    p = _write(tmp_path, "stack-thing", """
# Usage: stack-thing <radarr|sonarr|radarr_anime|sonarr_anime> [limit]
function stack-thing --description 'Do a thing'
    if not __stack_arr_app $argv[1] >/dev/null
        return 1
    end
end
""")
    out = gen.render(p)
    assert "-a 'radarr sonarr radarr_anime sonarr_anime'" in out


def test_free_form_placeholder_gets_no_literal_completion(gen, tmp_path):
    """Offering the literal string "movie-id" would be worse than nothing."""
    p = _write(tmp_path, "stack-thing", """
# Usage: stack-thing <movie-id>
function stack-thing --description 'Do a thing'
end
""")
    out = gen.render(p)
    assert "movie-id'" not in out
    assert "complete -c stack-thing -f" in out


def test_file_completion_disabled_by_default(gen, tmp_path):
    p = _write(tmp_path, "stack-thing", """
function stack-thing --description 'Do a thing'
end
""")
    assert "complete -c stack-thing -f\n" in gen.render(p)


def test_description_quotes_are_escaped(gen, tmp_path):
    """`--description 'Tail an *arr app''s log'` must not break the file."""
    p = _write(tmp_path, "stack-thing", """
function stack-thing --description 'Tail an *arr app''s container log'
end
""")
    out = gen.render(p)
    assert r"app\'s" in out


def test_check_mode_reports_drift(gen, tmp_path, capsys):
    (tmp_path / "stack-thing.fish").write_text(
        "function stack-thing --description 'Do a thing'\nend\n")
    (tmp_path / gen.COMPLETIONS_DIRNAME).mkdir()
    (tmp_path / gen.COMPLETIONS_DIRNAME / "stack-thing.fish").write_text("stale\n")

    import sys
    argv = sys.argv
    sys.argv = ["gen", "--check", "--repo-dir", str(tmp_path)]
    try:
        assert gen.main() == 1
    finally:
        sys.argv = argv
    assert "differs" in capsys.readouterr().out
