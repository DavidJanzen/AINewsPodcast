import pytest
from bs4 import BeautifulSoup

from src.fetchers.website_fetcher import extract_title_and_url, parse_german_date


@pytest.mark.parametrize('text, expected', [
    ('5. April 2026', '2026-04-05'),
    ('12. März 2025', '2025-03-12'),
    (' 1. Dezember 2026 ', '2026-12-01'),
    ('5. Foo 2026', None),
    ('April 2026', None),
    ('x. April 2026', None),
])
def test_parse_german_date(text, expected):
    assert parse_german_date(text) == expected


def article(html):
    return BeautifulSoup(f'<article>{html}</article>', 'html.parser').article


def test_layout_a_flex_link():
    tag = article('<a class="flex-1 font-bold" href="https://x/a">Titel A</a>')
    assert extract_title_and_url(tag) == ('Titel A', 'https://x/a')


def test_layout_b_overlay_link_strips_prefix():
    tag = article('<a class="absolute inset-0 z-10" href="https://x/b">Read full article about: Titel B</a>')
    assert extract_title_and_url(tag) == ('Titel B', 'https://x/b')


def test_layout_c_heading_and_copy_link():
    tag = article('<h2>Titel C</h2><a class="copy-url-link" href="https://x/c">Link kopieren</a>')
    assert extract_title_and_url(tag) == ('Titel C', 'https://x/c')


def test_class_match_requires_whole_class_names():
    tag = article('<a class="flex-10" href="https://x/d">Kein Treffer</a>')
    assert extract_title_and_url(tag) == (None, None)
