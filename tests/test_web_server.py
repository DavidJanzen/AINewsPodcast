import json

import pytest
import yaml

from src.server.web_server import create_app


@pytest.fixture
def client(tmp_path, config, tracker):
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(yaml.safe_dump(config), encoding='utf-8')

    tracker.add_article('https://x/a', 'A', '2026-01-15T08:00:00')
    tracker.mark_processed('https://x/a', 'episode_2026-01-15', summary='S')
    tracker.add_episode('episode_2026-01-15', 'T', 'D', '2026-01-15T12:00:00',
                        str(tmp_path / 'output' / 'audio' / 'episode_2026-01-15.wav'), 60.0, 1)

    audio_dir = tmp_path / 'output' / 'audio'
    audio_dir.mkdir(parents=True)
    (audio_dir / 'episode_2026-01-15.wav').write_bytes(b'RIFF' + b'\0' * 100)

    return create_app(config_path).test_client()


def test_episodes_api(client):
    [episode] = client.get('/api/episodes').get_json()
    assert episode['id'] == 'episode_2026-01-15'
    assert episode['audio_filename'] == 'episode_2026-01-15.wav'


def test_episode_articles_api(client):
    assert client.get('/api/episodes/episode_2026-01-15/articles').get_json() == [
        {'title': 'A', 'url': 'https://x/a', 'summary': 'S', 'original_content': None}]
    assert client.get('/api/episodes/invalid/articles').get_json() == []


def test_audio_supports_range_requests_and_blocks_traversal(client):
    response = client.get('/audio/episode_2026-01-15.wav', headers={'Range': 'bytes=0-3'})
    assert response.status_code == 206
    assert response.data == b'RIFF'
    assert client.get('/audio/../config.yaml').status_code == 404


def test_missing_feed_returns_404(client):
    assert client.get('/feed.xml').status_code == 404


def test_generate_rejects_invalid_date(client):
    response = client.post('/api/generate', data=json.dumps({'date': '2026-13-01'}),
                           content_type='application/json')
    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_stats_api(client):
    assert client.get('/api/stats').get_json()['total_episodes'] == 1
