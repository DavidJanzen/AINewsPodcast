"""
Article Tracker Database Module

SQLite storage for articles and episodes. Prevents articles from being processed twice.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


class ArticleTracker:
    """Tracks articles and episodes in a SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        logger.info(f"ArticleTracker initialized with database: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """Create tables if they don't exist and apply column migrations."""
        with self._connect() as conn:
            # Note: articles.audio_file / duration_seconds / error and episodes.rss_published
            # are legacy columns kept for compatibility with existing databases.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    url_hash TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    published_date TEXT NOT NULL,
                    fetched_date TEXT NOT NULL,
                    processed BOOLEAN DEFAULT 0,
                    processed_date TEXT,
                    episode_id TEXT,
                    content_hash TEXT,
                    summary TEXT,
                    audio_file TEXT,
                    duration_seconds REAL,
                    error TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    created_date TEXT NOT NULL,
                    published_date TEXT NOT NULL,
                    audio_file TEXT NOT NULL,
                    duration_seconds REAL,
                    article_count INTEGER DEFAULT 0,
                    file_size_bytes INTEGER,
                    rss_published BOOLEAN DEFAULT 0,
                    article_links TEXT,
                    chapters_file TEXT
                )
            """)

            # Migrations for databases created by older versions
            for table, column in (('episodes', 'article_links'),
                                  ('episodes', 'chapters_file'),
                                  ('articles', 'original_content')):
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists

            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles(url_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_processed ON articles(processed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles(published_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_episode_id ON articles(episode_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_published_date ON episodes(published_date)")

    @staticmethod
    def _hash_url(url: str) -> str:
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    # -----------------------------------------------------------------------
    # Articles
    # -----------------------------------------------------------------------

    def add_article(self, url: str, title: str, published_date: str,
                    content_hash: Optional[str] = None) -> bool:
        """Add a new article. Returns False if it already exists."""
        try:
            with self._connect() as conn:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO articles
                    (url, url_hash, title, published_date, fetched_date, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (url, self._hash_url(url), title, published_date,
                      datetime.now().isoformat(), content_hash))
                if cursor.rowcount > 0:
                    logger.info(f"Added new article: {title}")
                    return True
                return False
        except sqlite3.Error as e:
            logger.error(f"Error adding article: {e}")
            return False

    def mark_processed(self, url: str, episode_id: str, summary: Optional[str] = None,
                       original_content: Optional[str] = None) -> bool:
        """Mark an article as processed and store its summary."""
        try:
            with self._connect() as conn:
                cursor = conn.execute("""
                    UPDATE articles
                    SET processed = 1, processed_date = ?, episode_id = ?,
                        summary = ?, original_content = COALESCE(?, original_content)
                    WHERE url_hash = ?
                """, (datetime.now().isoformat(), episode_id, summary,
                      original_content, self._hash_url(url)))
                if cursor.rowcount > 0:
                    logger.info(f"Marked article as processed: {url}")
                    return True
                logger.warning(f"Article not found in database: {url}")
                return False
        except sqlite3.Error as e:
            logger.error(f"Error marking article as processed: {e}")
            return False

    def set_original_content(self, url: str, original_content: str) -> bool:
        """Store the scraped article text of an article."""
        try:
            with self._connect() as conn:
                cursor = conn.execute("UPDATE articles SET original_content = ? WHERE url_hash = ?",
                                      (original_content, self._hash_url(url)))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error storing article content: {e}")
            return False

    def get_articles_without_content(self) -> List[Dict]:
        """Return all articles whose scraped text has not been stored yet."""
        return self._query("SELECT * FROM articles WHERE original_content IS NULL ORDER BY published_date ASC")

    def get_articles_by_date(self, date: str) -> List[Dict]:
        """Return all articles published on a date (YYYY-MM-DD)."""
        return self._query("SELECT * FROM articles WHERE published_date LIKE ? ORDER BY published_date ASC",
                           (f"{date}%",))

    def get_episode_articles(self, episode_id: str) -> List[Dict]:
        """Return all articles belonging to an episode."""
        return self._query("SELECT * FROM articles WHERE episode_id = ? ORDER BY published_date ASC",
                           (episode_id,))

    # -----------------------------------------------------------------------
    # Episodes
    # -----------------------------------------------------------------------

    def add_episode(self, episode_id: str, title: str, description: str, published_date: str,
                    audio_file: str, duration: float, article_count: int,
                    file_size: Optional[int] = None, article_links: Optional[str] = None,
                    chapters_file: Optional[str] = None) -> bool:
        """Insert or replace an episode."""
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO episodes
                    (id, title, description, created_date, published_date, audio_file,
                     duration_seconds, article_count, file_size_bytes, article_links, chapters_file)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (episode_id, title, description, datetime.now().isoformat(), published_date,
                      audio_file, duration, article_count, file_size, article_links, chapters_file))
            logger.info(f"Saved episode: {episode_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding episode: {e}")
            return False

    def get_all_episodes(self) -> List[Dict]:
        """Return all episodes, newest first, with article_links parsed from JSON."""
        episodes = self._query("SELECT * FROM episodes ORDER BY published_date DESC")
        for episode in episodes:
            try:
                episode['article_links'] = json.loads(episode.get('article_links') or '[]')
            except (json.JSONDecodeError, TypeError):
                episode['article_links'] = []
        return episodes

    def get_statistics(self) -> Dict:
        """Return article and episode counts plus total duration."""
        try:
            with self._connect() as conn:
                row = conn.execute("""
                    SELECT
                        (SELECT COUNT(*) FROM articles) AS total_articles,
                        (SELECT COUNT(*) FROM articles WHERE processed = 1) AS processed_articles,
                        (SELECT COUNT(*) FROM articles WHERE processed = 0) AS unprocessed_articles,
                        (SELECT COUNT(*) FROM episodes) AS total_episodes,
                        (SELECT COALESCE(SUM(duration_seconds), 0) FROM episodes) AS total_duration_seconds
                """).fetchone()
                return dict(row)
        except sqlite3.Error as e:
            logger.error(f"Error getting statistics: {e}")
            return {}

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _query(self, sql: str, params: tuple = ()) -> List[Dict]:
        try:
            with self._connect() as conn:
                return [dict(row) for row in conn.execute(sql, params).fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
