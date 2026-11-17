import pytest

from src.generators.news_manager import NewsManager


class FakeWebsiteFetcher:
    def __init__(self, articles):
        self.articles = articles
        self.calls = []

    def fetch_articles_for_date(self, date):
        self.calls.append(date)
        return self.articles


@pytest.fixture
def manager(config, tracker):
    manager = NewsManager(config, tracker)
    manager.website_fetcher = FakeWebsiteFetcher([])
    return manager


def add(tracker, url, published):
    tracker.add_article(url, url.rsplit('/', 1)[-1], published)


def test_selects_unprocessed_articles_of_the_day_newest_first(manager, tracker):
    add(tracker, 'https://x/a', '2026-01-15T08:00:00')
    add(tracker, 'https://x/b', '2026-01-15T10:00:00')
    add(tracker, 'https://x/other-day', '2026-01-16T08:00:00')
    add(tracker, 'https://x/done', '2026-01-15T09:00:00')
    tracker.mark_processed('https://x/done', 'episode_2026-01-15')

    articles = manager.get_articles_for_daily_episode('2026-01-15')
    assert [a['url'] for a in articles] == ['https://x/b', 'https://x/a']


def test_force_regenerate_includes_processed_and_respects_max(manager, tracker):
    for hour in (8, 9, 10):
        add(tracker, f'https://x/{hour}', f'2026-01-15T{hour:02d}:00:00')
        tracker.mark_processed(f'https://x/{hour}', 'episode_2026-01-15')

    articles = manager.get_articles_for_daily_episode('2026-01-15', force_regenerate=True)
    assert [a['url'] for a in articles] == ['https://x/10', 'https://x/9']  # max_articles_per_episode = 2


def test_website_fallback_when_database_has_no_articles(manager):
    manager.website_fetcher = FakeWebsiteFetcher([
        {'url': 'https://x/web', 'title': 'Web', 'published_date': '2026-01-15T07:00:00+01:00'},
    ])

    articles = manager.get_articles_for_daily_episode('2026-01-15')
    assert [a['url'] for a in articles] == ['https://x/web']
    assert manager.website_fetcher.calls == ['2026-01-15']


def test_no_fallback_when_database_has_articles(manager, tracker):
    add(tracker, 'https://x/a', '2026-01-15T08:00:00')
    manager.get_articles_for_daily_episode('2026-01-15')
    assert manager.website_fetcher.calls == []


def test_mark_articles_processed(manager, tracker):
    add(tracker, 'https://x/a', '2026-01-15T08:00:00')
    ok = manager.mark_articles_processed([{'url': 'https://x/a'}], 'episode_2026-01-15',
                                         summaries={'https://x/a': 'S'})
    assert ok
    assert tracker.get_episode_articles('episode_2026-01-15')[0]['summary'] == 'S'
    assert not manager.mark_articles_processed([{'url': 'https://x/missing'}], 'episode_2026-01-15')
