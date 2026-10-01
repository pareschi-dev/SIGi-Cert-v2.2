from certhub.core.browser_handler import BrowserSession


def test_browser_session_can_open_and_close_a_page():
    session = BrowserSession(headless=True)
    page = session.start()

    page.goto("https://example.com", wait_until="domcontentloaded")
    assert "Example Domain" in page.title()

    session.close()
    assert session.page is None
