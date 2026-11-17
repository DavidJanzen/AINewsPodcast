"""Shared test fixtures."""

import pytest

from src.database.article_tracker import ArticleTracker


@pytest.fixture
def tracker(tmp_path):
    return ArticleTracker(str(tmp_path / 'test.db'))


@pytest.fixture
def config(tmp_path):
    return {
        'rss': {'source_url': 'https://the-decoder.de/feed', 'max_articles_per_fetch': 50},
        'database': {'path': str(tmp_path / 'test.db')},
        'episode': {'min_articles': 1, 'max_articles_per_episode': 2},
        'podcast': {'title': 'Test Podcast', 'author': 'Tester', 'explicit': False},
        'server': {'public_ip': '10.0.0.1', 'port': 8080},
        'storage': {'output_dir': str(tmp_path / 'output'), 'audio_dir': str(tmp_path / 'output' / 'audio')},
        'logging': {'file': str(tmp_path / 'test.log')},
    }
