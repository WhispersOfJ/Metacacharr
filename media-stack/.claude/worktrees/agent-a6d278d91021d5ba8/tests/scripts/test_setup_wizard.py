def test_parse_env_example_sections_and_help_text(setup_wizard, tmp_path):
    content = """\
# ---- Core ----
# The PUID to run containers as.
# Second help line.
PUID=1000
PGID=1000

# ---- Plex ----
PLEX_URL=http://changeme:32400
"""
    path = tmp_path / ".env.example"
    path.write_text(content)

    sections = setup_wizard.parse_env_example(path)
    assert [s["name"] for s in sections] == ["Core", "Plex"]
    core_fields = sections[0]["fields"]
    assert core_fields[0] == {"key": "PUID", "default": "1000", "help": "The PUID to run containers as. Second help line."}
    assert core_fields[1] == {"key": "PGID", "default": "1000", "help": ""}
    assert sections[1]["fields"] == [{"key": "PLEX_URL", "default": "http://changeme:32400", "help": ""}]


def test_parse_env_values_ignores_comments_and_blanks(setup_wizard, tmp_path):
    path = tmp_path / ".env"
    path.write_text("PUID=1000\n# a comment\n\nPLEX_URL=http://host:32400\n")
    values = setup_wizard.parse_env_values(path)
    assert values == {"PUID": "1000", "PLEX_URL": "http://host:32400"}


def test_parse_env_values_missing_file_is_empty(setup_wizard, tmp_path):
    assert setup_wizard.parse_env_values(tmp_path / "does-not-exist.env") == {}


def test_initial_value_prefers_existing_over_default(setup_wizard):
    assert setup_wizard.initial_value("PUID", "1000", {"PUID": "1001"}) == "1001"


def test_initial_value_falls_back_to_default(setup_wizard):
    assert setup_wizard.initial_value("PUID", "1000", {}) == "1000"


def test_initial_value_auto_generates_only_for_listed_keys(setup_wizard, monkeypatch):
    monkeypatch.setattr(setup_wizard, "AUTO_GENERATE_KEYS", {"SOME_SECRET"})
    generated = setup_wizard.initial_value("SOME_SECRET", "changeme", {})
    assert generated != "changeme"
    assert len(generated) == 32  # secrets.token_hex(16)


def test_initial_value_no_auto_generate_for_unlisted_key(setup_wizard, monkeypatch):
    monkeypatch.setattr(setup_wizard, "AUTO_GENERATE_KEYS", {"SOME_SECRET"})
    assert setup_wizard.initial_value("OTHER_KEY", "changeme", {}) == "changeme"


def test_escape_handles_all_html_special_chars(setup_wizard):
    assert setup_wizard.escape('<a href="x">&Y</a>') == "&lt;a href=&quot;x&quot;&gt;&amp;Y&lt;/a&gt;"


def test_render_env_file_prefers_submitted_over_existing_over_default(setup_wizard, tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("# ---- Core ----\nPUID=1000\nPGID=1000\nHOST_IP=changeme\n")

    result = setup_wizard.render_env_file(
        example,
        submitted={"PUID": "2000", "PGID": ""},
        existing={"PGID": "1500"},
    )
    lines = dict(line.split("=", 1) for line in result.strip().splitlines() if "=" in line)
    assert lines["PUID"] == "2000"   # submitted wins
    assert lines["PGID"] == "1500"   # blank submission falls back to existing
    assert lines["HOST_IP"] == "changeme"  # no submission/existing -> example default


def test_render_env_file_preserves_non_field_lines(setup_wizard, tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("# ---- Core ----\n# a comment\nPUID=1000\n")
    result = setup_wizard.render_env_file(example, {}, {})
    assert "# a comment" in result
    assert result.endswith("\n")


def test_write_env_atomic_writes_content_and_cleans_up_tmp(setup_wizard, tmp_path):
    target = tmp_path / ".env"
    setup_wizard.write_env_atomic(target, "PUID=1000\n")
    assert target.read_text() == "PUID=1000\n"
    assert not (tmp_path / ".env.env.tmp").exists()


def test_write_env_atomic_overwrites_existing_file(setup_wizard, tmp_path):
    target = tmp_path / ".env"
    target.write_text("OLD=1\n")
    setup_wizard.write_env_atomic(target, "NEW=2\n")
    assert target.read_text() == "NEW=2\n"
