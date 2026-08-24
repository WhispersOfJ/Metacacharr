from bs4 import BeautifulSoup


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def test_list_urls_on_page_matches_user_list_slug_shape(scrape_letterboxd):
    html = """
    <a href="/someuser/list/best-of-2024/">A list</a>
    <a href="/otheruser/list/another-list/">Another list</a>
    """
    urls = scrape_letterboxd.list_urls_on_page(_soup(html), "https://letterboxd.com/lists/featured/")
    assert urls == {
        "https://letterboxd.com/someuser/list/best-of-2024/",
        "https://letterboxd.com/otheruser/list/another-list/",
    }


def test_list_urls_on_page_excludes_sort_filter_subpaths(scrape_letterboxd):
    html = """
    <a href="/someuser/list/best-of-2024/by/rating/">Sorted view</a>
    <a href="/someuser/list/best-of-2024/detail/">Detail view</a>
    """
    urls = scrape_letterboxd.list_urls_on_page(_soup(html), "https://letterboxd.com/lists/featured/")
    assert urls == set()


def test_list_urls_on_page_excludes_unrelated_links(scrape_letterboxd):
    html = """
    <a href="/someuser/">Profile</a>
    <a href="/films/popular/">Popular films</a>
    """
    urls = scrape_letterboxd.list_urls_on_page(_soup(html), "https://letterboxd.com/lists/featured/")
    assert urls == set()


def test_next_page_url_present(scrape_letterboxd):
    html = '<a class="next" href="/lists/featured/page/2/">Next</a>'
    result = scrape_letterboxd.next_page_url(_soup(html), "https://letterboxd.com/lists/featured/")
    assert result == "https://letterboxd.com/lists/featured/page/2/"


def test_next_page_url_absent_on_last_page(scrape_letterboxd):
    html = "<p>No more pages</p>"
    result = scrape_letterboxd.next_page_url(_soup(html), "https://letterboxd.com/lists/featured/")
    assert result is None
