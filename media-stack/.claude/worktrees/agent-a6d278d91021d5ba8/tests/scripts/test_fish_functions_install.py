"""Phase 8a: the symlink installer that makes fish-functions/ the single
source of truth.

Two sources of truth existed before this: the repo's fish-functions/ and the
host's ~/.config/fish/functions/, hand-copied between. They drifted 9 names
apart. Symlinks make drift structurally impossible rather than discouraged,
which is the same pattern this repo's systemd units already use.

The prune path is the sharp edge: it deletes files from the user's live shell
environment, so it must only ever touch stack-*.fish, never a real file the
user wrote by hand outside this repo, and never anything without the prefix.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/fish-functions-install.py"


@pytest.fixture(scope="module")
def installer():
    spec = importlib.util.spec_from_file_location("_script_fish_functions_install", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_script_fish_functions_install"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dirs(tmp_path):
    repo = tmp_path / "fish-functions"
    installed = tmp_path / "functions"
    repo.mkdir()
    installed.mkdir()
    return repo, installed


def _write(directory: Path, name: str, body: str = "function x\nend\n") -> Path:
    path = directory / f"{name}.fish"
    path.write_text(body)
    return path


def test_missing_function_is_linked(installer, dirs):
    repo, installed = dirs
    _write(repo, "stack-plex-scan")
    actions = installer.plan(repo, installed)
    assert actions["link"] == [installed / "stack-plex-scan.fish"]
    installer.apply(actions, repo_dir=repo)
    link = installed / "stack-plex-scan.fish"
    assert link.is_symlink()
    assert link.resolve() == (repo / "stack-plex-scan.fish").resolve()


def test_plain_copy_is_replaced_by_a_link(installer, dirs):
    """The starting state on the real host: 191 plain copies."""
    repo, installed = dirs
    _write(repo, "stack-plex-scan", "function new\nend\n")
    _write(installed, "stack-plex-scan", "function stale copy\nend\n")
    actions = installer.plan(repo, installed)
    assert actions["relink"] == [installed / "stack-plex-scan.fish"]
    installer.apply(actions, repo_dir=repo)
    assert (installed / "stack-plex-scan.fish").is_symlink()
    assert (installed / "stack-plex-scan.fish").read_text() == "function new\nend\n"


def test_host_only_stack_function_is_pruned(installer, dirs):
    """The 5 restic orphans: installed, not in the repo, dead."""
    repo, installed = dirs
    _write(installed, "stack-backup-verify")
    actions = installer.plan(repo, installed)
    assert actions["prune"] == [installed / "stack-backup-verify.fish"]
    installer.apply(actions, repo_dir=repo)
    assert not (installed / "stack-backup-verify.fish").exists()


def test_non_stack_functions_are_never_touched(installer, dirs):
    """The user's own fish functions live in the same directory. Pruning one
    would delete work that has no other copy anywhere.

    __stack_*.fish became installable on 2026-08-14 but deliberately did not
    become prunable: a helper present on the host and absent from the repo is
    the host's only copy."""
    repo, installed = dirs
    _write(installed, "my-own-helper")
    _write(installed, "__stack_api")
    actions = installer.plan(repo, installed)
    assert actions["prune"] == []
    installer.apply(actions, repo_dir=repo)
    assert (installed / "my-own-helper.fish").exists()
    assert (installed / "__stack_api.fish").exists()


def test_repo_helpers_are_installed_like_commands(installer, dirs):
    """The drift this closes: a helper edited in the repo kept running from a
    stale hand-copied version on the host, invisibly, because a private
    helper produces no output of its own."""
    repo, installed = dirs
    source = _write(repo, "__stack_arr_app")
    actions = installer.plan(repo, installed)
    assert installed / "__stack_arr_app.fish" in actions["link"]
    installer.apply(actions, repo_dir=repo)
    assert (installed / "__stack_arr_app.fish").resolve() == source.resolve()


def test_stale_helper_copy_is_relinked_not_left(installer, dirs):
    """A plain copy shadowing a repo helper is the drift itself."""
    repo, installed = dirs
    source = _write(repo, "__stack_arr_app")
    _write(installed, "__stack_arr_app")  # plain copy, not a link
    actions = installer.plan(repo, installed)
    assert installed / "__stack_arr_app.fish" in actions["relink"]
    installer.apply(actions, repo_dir=repo)
    assert (installed / "__stack_arr_app.fish").resolve() == source.resolve()


def test_correct_link_is_left_alone(installer, dirs):
    """Idempotence: a second run does nothing, so it is safe to re-run."""
    repo, installed = dirs
    source = _write(repo, "stack-plex-scan")
    (installed / "stack-plex-scan.fish").symlink_to(source)
    actions = installer.plan(repo, installed)
    assert actions == {"link": [], "relink": [], "prune": [], "keep": [installed / "stack-plex-scan.fish"]}


def test_dangling_link_is_repaired(installer, dirs):
    """A link left behind by a renamed function points at nothing. It is a
    prune, not a relink - the repo no longer has that name."""
    repo, installed = dirs
    (installed / "stack-gone.fish").symlink_to(repo / "stack-gone.fish")
    actions = installer.plan(repo, installed)
    assert actions["prune"] == [installed / "stack-gone.fish"]
    installer.apply(actions, repo_dir=repo)
    assert not (installed / "stack-gone.fish").is_symlink()


def test_dry_run_changes_nothing(installer, dirs):
    repo, installed = dirs
    _write(repo, "stack-plex-scan")
    _write(installed, "stack-backup-verify")
    lines = installer.apply(installer.plan(repo, installed), repo_dir=repo, dry_run=True)
    assert not (installed / "stack-plex-scan.fish").exists()
    assert (installed / "stack-backup-verify.fish").exists()
    assert any("stack-plex-scan" in line for line in lines)
