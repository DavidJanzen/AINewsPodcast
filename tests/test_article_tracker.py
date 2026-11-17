import json


def test_add_article_ignores_duplicates(tracker):
    assert tracker.add_article('https://x/a', 'A', '2026-01-15T08:00:00')
    assert not tracker.add_article('https://x/a', 'A again', '2026-01-15T08:00:00')
    assert [a['title'] for a in tracker.get_articles_by_date('2026-01-15')] == ['A']


def test_get_articles_by_date_matches_day_only(tracker):
    tracker.add_article('https://x/a', 'A', '2026-01-15T23:59:00')
    tracker.add_article('https://x/b', 'B', '2026-01-16T00:01:00')
    assert [a['title'] for a in tracker.get_articles_by_date('2026-01-15')] == ['A']


def test_mark_processed_stores_summary_and_episode(tracker):
    tracker.add_article('https://x/a', 'A', '2026-01-15T08:00:00')
    assert tracker.mark_processed('https://x/a', 'episode_2026-01-15', summary='S', original_content='O')
    assert not tracker.mark_processed('https://x/missing', 'episode_2026-01-15')

    [article] = tracker.get_episode_articles('episode_2026-01-15')
    assert (article['processed'], article['summary'], article['original_content']) == (1, 'S', 'O')


def test_original_content_backfill(tracker):
    tracker.add_article('https://x/a', 'A', '2026-01-15T08:00:00')
    assert [a['url'] for a in tracker.get_articles_without_content()] == ['https://x/a']

    assert tracker.set_original_content('https://x/a', 'Text')
    assert tracker.get_articles_without_content() == []


def test_episodes_and_statistics(tracker):
    tracker.add_article('https://x/a', 'A', '2026-01-15T08:00:00')
    tracker.add_article('https://x/b', 'B', '2026-01-15T09:00:00')
    tracker.mark_processed('https://x/a', 'episode_2026-01-15')
    links = json.dumps([{'title': 'A', 'url': 'https://x/a'}])
    tracker.add_episode('episode_2026-01-15', 'T', 'D', '2026-01-15T12:00:00', 'a.wav', 90.0, 1,
                        article_links=links)
    tracker.add_episode('episode_2026-01-15', 'T2', 'D', '2026-01-15T12:00:00', 'a.wav', 120.0, 1)  # replace

    [episode] = tracker.get_all_episodes()
    assert episode['title'] == 'T2'
    assert episode['article_links'] == []
    assert tracker.get_statistics() == {
        'total_articles': 2, 'processed_articles': 1, 'unprocessed_articles': 1,
        'total_episodes': 1, 'total_duration_seconds': 120.0,
    }
