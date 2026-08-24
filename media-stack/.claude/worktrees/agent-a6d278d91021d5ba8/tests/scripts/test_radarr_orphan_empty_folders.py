"""Gate tests for scripts/radarr-orphan-empty-folders.py.

This script deletes directories, so the tests focus on the guards that decide
what is deletable - every skip reason is a case where deleting would have been
wrong.
"""
import importlib.util

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "radarr-orphan-empty-folders.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("orphan_folders", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def root(tmp_path):
    return tmp_path


def make(root, name, files=()):
    d = root / name
    d.mkdir()
    for f in files:
        (d / f).write_text("x")
    return d


def test_empty_orphan_folder_is_deletable(mod, root):
    # Arrange
    make(root, "A Movie (1999) {tmdb-111}")

    # Act
    deletable, skipped = mod.classify(["A Movie (1999) {tmdb-111}"], set(), str(root))

    # Assert
    assert deletable == ["A Movie (1999) {tmdb-111}"]
    assert skipped == []


def test_folder_with_files_is_never_deletable(mod, root):
    """The whole point: a folder holding media must survive."""
    # Arrange
    make(root, "Real Movie (2001) {tmdb-222}", files=["movie.mkv"])

    # Act
    deletable, skipped = mod.classify(["Real Movie (2001) {tmdb-222}"], set(), str(root))

    # Assert
    assert deletable == []
    assert "not empty" in skipped[0][1]


def test_folder_whose_movie_still_exists_is_skipped(mod, root):
    """Radarr can report a folder unmapped while the movie exists at another path."""
    # Arrange
    make(root, "Still Tracked (2002) {tmdb-333}")

    # Act
    deletable, skipped = mod.classify(["Still Tracked (2002) {tmdb-333}"], {333}, str(root))

    # Assert
    assert deletable == []
    assert skipped[0][1] == "tmdb id still present in Radarr"


def test_folder_without_tmdb_tag_is_skipped(mod, root):
    """An untagged folder cannot be proven orphaned, so it is left alone."""
    # Arrange
    make(root, "Mystery Folder")

    # Act
    deletable, skipped = mod.classify(["Mystery Folder"], set(), str(root))

    # Assert
    assert deletable == []
    assert skipped[0][1] == "no tmdb tag in folder name"


def test_missing_folder_is_skipped_not_crashed(mod, root):
    # Arrange / Act
    deletable, skipped = mod.classify(["Gone (2003) {tmdb-444}"], set(), str(root))

    # Assert
    assert deletable == []
    assert skipped[0][1] == "folder no longer exists"


def test_hidden_file_counts_as_non_empty(mod, root):
    """A dotfile still means the folder is not empty - rmdir would fail anyway."""
    # Arrange
    make(root, "Sneaky (2004) {tmdb-555}", files=[".nfo-backup"])

    # Act
    deletable, skipped = mod.classify(["Sneaky (2004) {tmdb-555}"], set(), str(root))

    # Assert
    assert deletable == []
    assert "not empty" in skipped[0][1]


def test_delete_folders_removes_only_empty_dirs(mod, root):
    """Race guard: a folder that gains a file after classification must survive."""
    # Arrange
    make(root, "Empty (2005) {tmdb-666}")
    make(root, "Filled (2006) {tmdb-777}", files=["late-arrival.mkv"])

    # Act - both passed in as if classified deletable
    removed, failed = mod.delete_folders(
        ["Empty (2005) {tmdb-666}", "Filled (2006) {tmdb-777}"], str(root)
    )

    # Assert
    assert removed == ["Empty (2005) {tmdb-666}"]
    assert len(failed) == 1
    assert (root / "Filled (2006) {tmdb-777}" / "late-arrival.mkv").exists()


def test_dry_run_is_the_default(mod, root, monkeypatch, capsys):
    """Running with no flags must not delete anything."""
    # Arrange
    make(root, "A Movie (1999) {tmdb-111}")
    monkeypatch.setattr(mod, "fetch_unmapped_folders", lambda *a: ["A Movie (1999) {tmdb-111}"])
    monkeypatch.setattr(mod, "fetch_known_tmdb_ids", lambda *a: set())

    # Act
    rc = mod.main(["--api-key", "k", "--host-root", str(root)])

    # Assert
    assert rc == 0
    assert (root / "A Movie (1999) {tmdb-111}").exists()
    assert "DRY RUN" in capsys.readouterr().out


def test_apply_deletes_and_snapshot_is_written_first(mod, root, monkeypatch, tmp_path):
    # Arrange
    make(root, "A Movie (1999) {tmdb-111}")
    snap = tmp_path / "snap.json"
    monkeypatch.setattr(mod, "fetch_unmapped_folders", lambda *a: ["A Movie (1999) {tmdb-111}"])
    monkeypatch.setattr(mod, "fetch_known_tmdb_ids", lambda *a: set())

    # Act
    rc = mod.main(["--api-key", "k", "--host-root", str(root), "--apply", "--snapshot", str(snap)])

    # Assert
    assert rc == 0
    assert not (root / "A Movie (1999) {tmdb-111}").exists()
    assert snap.exists()


def test_missing_api_key_exits_rather_than_guessing(mod, root, monkeypatch):
    # Arrange
    monkeypatch.delenv("RADARR_API_KEY", raising=False)

    # Act / Assert
    with pytest.raises(SystemExit):
        mod.main(["--host-root", str(root)])
