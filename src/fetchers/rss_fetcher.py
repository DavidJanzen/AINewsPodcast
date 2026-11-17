"""
RSS Feed Fetcher Module

Fetches the news RSS feed and turns its entries into article dicts.
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.error import URLError

import feedparser


logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds


class RSSFetcher:
    """Fetches and parses an RSS feed."""

    def __init__(self, feed_url: str):
        self.feed_url = feed_url

    def fetch_articles(self, max_articles: Optional[int] = None) -> List[Dict]:
        """
        Fetch the feed (retrying on network errors) and return up to max_articles
        dicts with 'url', 'title', 'published_date' (ISO) and 'content_hash'.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"Fetching RSS feed from: {self.feed_url} (attempt {attempt}/{MAX_RETRIES})")
            feed = self._parse_feed()
            if feed is not None:
                break
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
        else:
            logger.error(f"RSS feed fetch failed after {MAX_RETRIES} attempts")
            return []

        entries = feed.entries[:max_articles] if max_articles else feed.entries
        articles = [article for article in map(self._parse_entry, entries) if article]
        logger.info(f"Fetched {len(articles)} articles from the RSS feed")
        return articles

    def validate_feed(self) -> bool:
        """Check that the feed is reachable and has entries."""
        logger.info(f"Validating RSS feed: {self.feed_url}")
        feed = self._parse_feed()
        if feed is None:
            return False
        if not feed.entries:
            logger.warning("Feed has no entries")
            return False
        logger.info("Feed validation successful")
        return True

    def _parse_feed(self):
        """Download and parse the feed. Returns None on network errors."""
        feed = feedparser.parse(self.feed_url)
        # feedparser also sets 'bozo' for harmless issues such as a mismatched
        # encoding declaration; only network errors are fatal.
        if feed.bozo and isinstance(feed.bozo_exception, (URLError, OSError)):
            logger.warning(f"Network error fetching feed: {feed.bozo_exception}")
            return None
        if feed.bozo:
            logger.warning(f"Feed parsing warning: {feed.bozo_exception}")
        return feed

    @staticmethod
    def _parse_entry(entry) -> Optional[Dict]:
        url = entry.get('link', '')
        if not url:
            logger.warning("Entry missing URL, skipping")
            return None

        title = entry.get('title', 'Untitled')
        content = entry.content[0].get('value', '') if entry.get('content') else entry.get('summary', '')
        return {
            'url': url,
            'title': title,
            'published_date': RSSFetcher._parse_date(entry),
            'content_hash': hashlib.md5((url + title + content).encode('utf-8')).hexdigest(),
        }

    @staticmethod
    def _parse_date(entry) -> str:
        """ISO publication date of an entry (UTC as given by the feed, or now as a last resort)."""
        for key in ('published_parsed', 'updated_parsed'):
            parsed = entry.get(key)
            if parsed:
                return datetime(*parsed[:6]).isoformat()
        for key in ('published', 'updated'):
            if entry.get(key):
                return entry[key]
        logger.warning("Could not parse entry date, using current time")
        return datetime.now().isoformat()
