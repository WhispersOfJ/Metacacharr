from core.plex_client import PLEX_URL, plex_headers, plex_sections


def test_plex_url_is_a_string():
    assert isinstance(PLEX_URL, str)


def test_plex_helpers_are_callable():
    assert callable(plex_headers)
    assert callable(plex_sections)
