import json

from src.generators.chapters_generator import ChaptersGenerator


def test_writes_podcasting20_chapters(config):
    path = ChaptersGenerator(config).generate_chapters_file([
        {'startTime': 0.0, 'title': 'Intro'},
        {'startTime': 12.5, 'title': 'Artikel', 'url': 'https://x/a', 'img': ''},
    ], 'episode_2026-01-15')

    assert path.endswith('episode_2026-01-15_chapters.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert data == {
        'version': '1.2.0',
        'chapters': [
            {'startTime': 0.0, 'title': 'Intro'},
            {'startTime': 12.5, 'title': 'Artikel', 'url': 'https://x/a'},
        ],
    }


def test_empty_chapters_return_none(config):
    assert ChaptersGenerator(config).generate_chapters_file([], 'episode_2026-01-15') is None
