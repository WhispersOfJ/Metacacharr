import json
import time

from posters import state


class TestLoadPosterState:
    def test_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "POSTER_STATE_PATH", str(tmp_path / "missing.json"))
        assert state.load_poster_state() == {}

    def test_corrupt_file_returns_empty_dict(self, tmp_path, monkeypatch):
        path = tmp_path / "state.json"
        path.write_text("not json")
        monkeypatch.setattr(state, "POSTER_STATE_PATH", str(path))
        assert state.load_poster_state() == {}

    def test_valid_file_returns_parsed_dict(self, tmp_path, monkeypatch):
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"123": 456.0}))
        monkeypatch.setattr(state, "POSTER_STATE_PATH", str(path))
        assert state.load_poster_state() == {"123": 456.0}


class TestSavePosterState:
    def test_writes_atomically_via_tmp_file(self, tmp_path, monkeypatch):
        path = tmp_path / "state.json"
        monkeypatch.setattr(state, "POSTER_STATE_PATH", str(path))
        state.save_poster_state({"42": 100.0})
        assert json.loads(path.read_text()) == {"42": 100.0}
        assert not (tmp_path / "state.json.tmp").exists()


class TestPosterCooldownRemaining:
    def test_no_entry_is_zero(self):
        assert state.poster_cooldown_remaining({}, "123") == 0

    def test_recent_entry_has_remaining_time(self):
        remaining = state.poster_cooldown_remaining({"123": time.time()}, "123")
        assert 0 < remaining <= state.POSTER_COOLDOWN_SECONDS

    def test_old_entry_is_clear(self):
        old = time.time() - state.POSTER_COOLDOWN_SECONDS - 3600
        assert state.poster_cooldown_remaining({"123": old}, "123") == 0
