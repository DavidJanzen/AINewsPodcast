"""
Article Scraper Module

Extracts the full article text from the-decoder.de article pages.
"""

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .http import REQUEST_DELAY, REQUEST_TIMEOUT, make_session


logger = logging.getLogger(__name__)

# Tried in order; the first match is used as the article body
CONTENT_SELECTORS = (
    'article .entry-content',
    'article .post-content',
    '.article-content',
    'article',
    '.entry-content',
    '.post-content',
)
MIN_PARAGRAPH_CHARS = 20  # shorter elements are usually navigation or captions
MIN_ARTICLE_CHARS = 100


class ArticleScraper:
    """Scrapes the full article text from the-decoder.de."""

    def __init__(self):
        self.session = make_session()

    def fetch_article_content(self, url: str) -> Optional[str]:
        """Return the article text (paragraphs separated by blank lines), or None on failure."""
        logger.info(f"Fetching article content from: {url}")
        time.sleep(REQUEST_DELAY)

        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching article {url}: {e}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        body = None
        for selector in CONTENT_SELECTORS:
            body = soup.select_one(selector)
            if body is not None:
                break
        if body is None:
            logger.warning(f"Could not find article content for: {url}")
            return None

        paragraphs = (elem.get_text(strip=True) for elem in body.find_all(['p', 'h2', 'h3', 'h4', 'li']))
        content = '\n\n'.join(text for text in paragraphs if len(text) > MIN_PARAGRAPH_CHARS)

        if len(content) <= MIN_ARTICLE_CHARS:
            logger.warning(f"Article content too short: {len(content)} characters")
            return None

        logger.info(f"Extracted {len(content)} characters from article")
        return content
