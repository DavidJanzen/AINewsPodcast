"""Shared HTTP session settings for scraping the-decoder.de."""

import requests

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; PodcastBot/1.0)"
REQUEST_TIMEOUT = 30  # seconds
REQUEST_DELAY = 1  # seconds between requests, to be polite to the server


def make_session(user_agent: str = DEFAULT_USER_AGENT) -> requests.Session:
    """Return a requests session with browser-like headers for German pages."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
    })
    return session
