from xml.etree import ElementTree as ET

from src.generators.rss_feed_generator import RSSFeedGenerator, _format_duration

ITUNES = '{http://www.itunes.com/dtds/podcast-1.0.dtd}'


def test_format_duration():
    assert _format_duration(0) == '00:00:00'
    assert _format_duration(3725.9) == '01:02:05'


def episode(**overrides):
    data = {
        'id': 'episode_2026-01-15',
        'title': 'Tech News - 2026-01-15',
        'description': 'Tech-News vom 2026-01-15:\n- A & B',
        'published_date': '2026-01-15T12:00:00',
        'audio_file': 'output/audio/episode_2026-01-15.wav',
        'file_size_bytes': 1234,
        'duration_seconds': 61,
        'chapters_file': 'output/chapters/episode_2026-01-15_chapters.json',
        'article_links': [{'title': 'A & B', 'url': 'https://the-decoder.de/a?x=1&y=2'}],
    }
    data.update(overrides)
    return data


def parse(config, episodes):
    xml = ET.tostring(RSSFeedGenerator(config).generate_feed(episodes).getroot())
    return ET.fromstring(xml)


def test_feed_contains_episode_with_enclosure_and_chapters(config):
    root = parse(config, [episode()])
    item = root.find('channel/item')

    assert root.find('channel/title').text == 'Test Podcast'
    assert item.find('guid').text == 'episode_2026-01-15'
    assert item.find('pubDate').text == 'Thu, 15 Jan 2026 12:00:00 +0000'
    enclosure = item.find('enclosure')
    assert enclosure.get('url') == 'http://10.0.0.1:8080/audio/episode_2026-01-15.wav'
    assert enclosure.get('type') == 'audio/wav'
    assert enclosure.get('length') == '1234'
    assert item.find(f'{ITUNES}duration').text == '00:01:01'
    chapters = item.find('{https://podcastindex.org/namespace/1.0}chapters')
    assert chapters.get('url') == 'http://10.0.0.1:8080/chapters/episode_2026-01-15_chapters.json'


def test_description_html_is_escaped(config):
    description = parse(config, [episode()]).find('channel/item/description').text
    assert 'A &amp; B' in description
    assert 'href="https://the-decoder.de/a?x=1&amp;y=2"' in description


def test_explicit_flag_is_used_for_channel_and_items(config):
    config['podcast']['explicit'] = True
    root = parse(config, [episode()])
    assert root.find(f'channel/{ITUNES}explicit').text == 'true'
    assert root.find(f'channel/item/{ITUNES}explicit').text == 'true'


def test_invalid_date_does_not_break_feed(config):
    root = parse(config, [episode(published_date='kaputt')])
    assert root.find('channel/item/pubDate').text
