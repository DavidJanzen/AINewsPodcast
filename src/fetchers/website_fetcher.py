"""
Website Fetcher Module

Finds the articles of a given day by scraping the-decoder.de listing pages.
Used as a fallback when the RSS feed no longer contains that day.
"""

import hashlib
import logging
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

from .http import REQUEST_DELAY, REQUEST_TIMEOUT, make_session


logger = logging.getLogger(__name__)

MAX_LISTING_PAGES = 20
LINK_TEXT_PREFIXES = ('Read full article about:', 'Lies den vollständigen Artikel über:')
GERMAN_MONTHS = {
    'januar': 1, 'februar': 2, 'märz': 3, 'april': 4,
    'mai': 5, 'juni': 6, 'juli': 7, 'august': 8,
    'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12,
}


def parse_german_date(date_text: str) -> Optional[str]:
    """Parse a German date like '5. April 2026' into 'YYYY-MM-DD' (None if invalid)."""
    parts = date_text.strip().replace('.', '').split()
    if len(parts) != 3:
        return None
    month = GERMAN_MONTHS.get(parts[1].lower())
    try:
        day, year = int(parts[0]), int(parts[2])
    except ValueError:
        return None
    if not month:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _has_classes(*names: str):
    """BeautifulSoup class filter matching elements that have all given CSS classes."""
    # BeautifulSoup calls the filter with each single class and with the joined class string
    return lambda classes: bool(classes) and set(names) <= set(classes.split())


def extract_title_and_url(article_tag: Tag) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (title, url) from a listing <article>. The site uses three layouts:
    A: <a class="flex-1 ...">Title</a>
    B: <a class="absolute inset-0 ...">Read full article about: Title</a>
    C: <h2>Title</h2> plus a copy-url link
    """
    title = url = None

    flex_link = article_tag.find('a', class_=_has_classes('flex-1'))
    if flex_link:
        title = flex_link.get_text(strip=True) or None
        url = flex_link.get('href') or None

    if not title or not url:
        overlay_link = article_tag.find('a', class_=_has_classes('absolute', 'inset-0'))
        if overlay_link:
            text = overlay_link.get_text(strip=True)
            for prefix in LINK_TEXT_PREFIXES:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
                    break
            title = title or text or None
            url = url or overlay_link.get('href') or None

    if not title:
        heading = article_tag.find(['h2', 'h3'])
        if heading:
            title = heading.get_text(strip=True) or None

    if not url:
        copy_link = article_tag.find('a', class_=_has_classes('copy-url-link'))
        if copy_link:
            url = copy_link.get('href') or None

    return title, url


class WebsiteFetcher:
    """Scrapes the-decoder.de listing pages for the articles of one day."""

    def __init__(self, feed_url: str):
        parsed = urlparse(feed_url)
        self.site_url = f"{parsed.scheme}://{parsed.netloc}"
        self.session = make_session()

    def fetch_articles_for_date(self, target_date: str) -> List[Dict]:
        """
        Return the articles published on target_date (YYYY-MM-DD), as dicts with
        'url', 'title', 'published_date' (ISO) and 'content_hash'.
        """
        logger.info(f"Scraping {self.site_url} to find articles for {target_date}")
        found = self._scan_listing_pages(target_date)
        if not found:
            logger.info(f"No articles found on website for {target_date}")
            return []

        return [
            {
                'url': art['url'],
                'title': art['title'],
                'published_date': self._published_time(art['url'], target_date),
                'content_hash': hashlib.md5((art['url'] + art['title']).encode('utf-8')).hexdigest(),
            }
            for art in found
        ]

    def _scan_listing_pages(self, target_date: str) -> List[Dict]:
        """Walk the listing pages (newest first) until articles older than target_date appear."""
        found: List[Dict] = []

        for page_num in range(1, MAX_LISTING_PAGES + 1):
            soup = self._fetch_listing_page(page_num)
            if soup is None:
                break

            oldest_date = None
            articles_on_page = 0
            for article_tag in soup.find_all('article'):
                date_span = article_tag.find('span', attrs={'alt': 'Date of publication'})
                date_only = parse_german_date(date_span.get_text(strip=True)) if date_span else None
                title, url = extract_title_and_url(article_tag)
                if not date_only or not title or not url:
                    continue

                articles_on_page += 1
                oldest_date = min(oldest_date or date_only, date_only)
                if date_only == target_date:
                    found.append({'url': url, 'title': title})

            logger.info(f"Page {page_num}: {articles_on_page} articles, oldest: {oldest_date}, "
                        f"found {len(found)} matching {target_date} so far")

            if oldest_date and oldest_date < target_date:
                break

        return found

    def _fetch_listing_page(self, page_num: int) -> Optional[BeautifulSoup]:
        """Return the parsed listing page, or None when there are no more pages or on error."""
        page_url = f"{self.site_url}/" if page_num == 1 else f"{self.site_url}/page/{page_num}/"
        logger.info(f"Fetching listing page {page_num}: {page_url}")
        time.sleep(REQUEST_DELAY)

        try:
            response = self.session.get(page_url, timeout=REQUEST_TIMEOUT)
            if response.status_code == 404:
                logger.info(f"Page {page_num} returned 404, stopping pagination")
                return None
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching listing page {page_num}: {e}")
            return None

        return BeautifulSoup(response.content, 'html.parser')

    def _published_time(self, url: str, date_only: str) -> str:
        """Exact publication time from the article's meta tags (noon UTC if unavailable)."""
        fallback = f"{date_only}T12:00:00+00:00"
        time.sleep(REQUEST_DELAY)
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not fetch exact date for {url}: {e}")
            return fallback

        meta = BeautifulSoup(response.content, 'html.parser').find(
            'meta', attrs={'property': 'article:published_time'})
        return meta['content'] if meta and meta.get('content') else fallback
