from core.nzbdav_client import NZBDAV_API_KEY, NZBDAV_REST_URL, NZBDAV_URL, nzbdav_api


def test_nzbdav_url_constants_are_strings():
    assert isinstance(NZBDAV_URL, str)
    assert isinstance(NZBDAV_REST_URL, str)
    assert NZBDAV_API_KEY is None or isinstance(NZBDAV_API_KEY, str)


def test_nzbdav_api_is_callable():
    assert callable(nzbdav_api)
