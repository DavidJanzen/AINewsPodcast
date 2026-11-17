"""
News Manager Module

Fetches articles into the database and selects the articles of one day for an episode.
"""

import logging
from typing import Dict, List, Optional

from ..database.article_tracker import ArticleTracker
from ..fetchers.rss_fetcher import RSSFetcher
from ..fetchers.website_fetcher import WebsiteFetcher


logger = logging.getLogger(__name__)


class NewsManager:
    """Connects the fetchers with the article database."""

    def __init__(self, config: Dict, db_tracker: ArticleTracker):
        self.db_tracker = db_tracker

        rss_config = config.get('rss', {})
        feed_url = rss_config.get('source_url', '')
        self.max_articles_per_fetch = rss_config.get('max_articles_per_fetch', 50)
        self.rss_fetcher = RSSFetcher(feed_url)
        self.website_fetcher = WebsiteFetcher(feed_url)

        episode_config = config.get('episode', {})
        self.min_articles = episode_config.get('min_articles', 1)
        self.max_articles = episode_config.get('max_articles_per_episode', 20)

    def fetch_new_articles(self) -> List[Dict]:
        """Fetch the RSS feed and store new articles. Returns the newly added ones."""
        articles = self.rss_fetcher.fetch_articles(max_articles=self.max_articles_per_fetch)
        new_articles = self._store(articles)
        logger.info(f"Fetched {len(new_articles)} new articles")
        return new_articles

    def get_articles_for_daily_episode(self, date: str, force_regenerate: bool = False) -> List[Dict]:
        """
        Return the articles for the episode of date (YYYY-MM-DD), newest first.

        Normally only unprocessed articles are used; with force_regenerate all articles
        of that day are used. If the database has none, the website listing pages are
        scraped as a fallback (the RSS feed only holds the latest articles).
        """
        articles = self._load_articles(date, force_regenerate)

        if not articles:
            logger.info(f"No articles in database for {date}, trying website scraping fallback")
            imported = self._store(self.website_fetcher.fetch_articles_for_date(date))
            logger.info(f"Imported {len(imported)} articles from website for {date}")
            articles = self._load_articles(date, force_regenerate)

        if len(articles) < self.min_articles:
            logger.warning(f"Not enough articles for {date} ({len(articles)} < {self.min_articles})")
            return []

        articles.sort(key=lambda a: a.get('published_date', ''), reverse=True)
        if self.max_articles and len(articles) > self.max_articles:
            logger.info(f"Limiting episode to {self.max_articles} of {len(articles)} articles")
            articles = articles[:self.max_articles]

        logger.info(f"Selected {len(articles)} articles for the episode of {date}")
        return articles

    def mark_articles_processed(self, articles: List[Dict], episode_id: str,
                                summaries: Optional[Dict[str, str]] = None,
                                original_contents: Optional[Dict[str, str]] = None) -> bool:
        """Mark articles as part of episode_id and store their summaries (keyed by URL)."""
        summaries = summaries or {}
        original_contents = original_contents or {}

        results = [
            self.db_tracker.mark_processed(
                url=article['url'],
                episode_id=episode_id,
                summary=summaries.get(article['url']),
                original_content=original_contents.get(article['url']),
            )
            for article in articles
        ]
        if not all(results):
            logger.warning("Some articles could not be marked as processed")
        return all(results)

    def validate_feed(self) -> bool:
        """Validate that the RSS feed is reachable and has entries."""
        return self.rss_fetcher.validate_feed()

    def _load_articles(self, date: str, force_regenerate: bool) -> List[Dict]:
        """Articles of date from the database: all of them, or only unprocessed ones."""
        articles = self.db_tracker.get_articles_by_date(date)
        if not force_regenerate:
            articles = [a for a in articles if not a.get('processed')]
        logger.info(f"Found {len(articles)} {'' if force_regenerate else 'unprocessed '}"
                    f"articles in database for {date}")
        return articles

    def _store(self, articles: List[Dict]) -> List[Dict]:
        """Add articles to the database; returns those that were new."""
        return [
            article for article in articles
            if self.db_tracker.add_article(
                url=article['url'],
                title=article['title'],
                published_date=article['published_date'],
                content_hash=article.get('content_hash'),
            )
        ]
