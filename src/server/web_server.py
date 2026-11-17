"""
Web Server for Der KI-osk Podcast

A single Flask server for everything:
- Podcast apps: RSS feed, audio files (with range requests), chapter files, logo
- Web UI: episode browser/player and an episode generation page with live log streaming (SSE)
- REST API used by the web UI
"""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import yaml
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

# Project root: two levels up from src/server/
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.article_tracker import ArticleTracker  # noqa: E402

DEFAULT_CONFIG_PATH = PROJECT_ROOT / 'config' / 'default_config.yaml'
EPISODE_ID_PATTERN = re.compile(r'episode_\d{4}-\d{2}-\d{2}')
SERVER_DIR = Path(__file__).parent

logger = logging.getLogger(__name__)


def detect_image_type(path: Path) -> str:
    """Return the MIME type of a PNG/JPEG file from its header (the logo is a JPEG named .png)."""
    with open(path, 'rb') as f:
        header = f.read(8)
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header.startswith(b'\x89PNG'):
        return 'image/png'
    return 'application/octet-stream'


def load_config(config_path: Path) -> Dict:
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Generation Manager
# ---------------------------------------------------------------------------

class GenerationManager:
    """Runs one episode generation subprocess at a time and streams its log file."""

    def __init__(self, config_path: Path, log_file: Path):
        self.config_path = config_path
        self.log_file = log_file
        self.process = None
        self.lock = threading.Lock()
        self.running = False
        self.current_date = None
        self.log_start_pos = 0
        self.exit_code = None

    def start(self, date_str: str):
        with self.lock:
            if self.running:
                return False, "Generierung läuft bereits"
            self.running = True
            self.current_date = date_str
            self.exit_code = None

        # Only stream log lines written after this point
        self.log_start_pos = self._file_size()

        venv_python = PROJECT_ROOT / 'venv' / 'bin' / 'python'
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable
        cmd = [
            python_cmd, str(PROJECT_ROOT / 'src' / 'main.py'),
            '--fetch', '--generate', '--date', date_str,
            '--config', str(self.config_path),
        ]

        # Output goes to the log file (streamed below). Stdout is discarded: an unread
        # PIPE would fill up and block the generator process.
        try:
            self.process = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT),
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            with self.lock:
                self.running = False
            return False, f"Generierung konnte nicht gestartet werden: {e}"

        threading.Thread(target=self._monitor, daemon=True).start()
        return True, "Generierung gestartet"

    def _monitor(self):
        self.process.wait()
        with self.lock:
            self.exit_code = self.process.returncode
            self.running = False

    def _file_size(self) -> int:
        try:
            return self.log_file.stat().st_size
        except OSError:
            return 0

    def _read_from(self, pos: int):
        """Return (new lines, new position) of the log file starting at pos."""
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(pos)
                content = f.read()
                return content.splitlines(), f.tell()
        except OSError:
            return [], pos

    def stream_logs(self):
        """Generator yielding SSE events with new log lines until the generation finishes."""
        pos = self.log_start_pos
        while True:
            size = self._file_size()
            if size < pos:
                pos = 0  # log file was truncated or replaced
            if size > pos:
                lines, pos = self._read_from(pos)
                for line in lines:
                    yield f"data: {json.dumps({'line': line})}\n\n"
            else:
                time.sleep(0.5)

            if not self.running:
                lines, pos = self._read_from(pos)
                for line in lines:
                    yield f"data: {json.dumps({'line': line})}\n\n"
                yield f"data: {json.dumps({'done': True, 'exit_code': self.exit_code})}\n\n"
                break


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config_path: Optional[Path] = None) -> Flask:
    config_path = Path(config_path or DEFAULT_CONFIG_PATH).resolve()
    config = load_config(config_path)
    storage = config.get('storage', {})

    # Relative paths in the config are relative to the project root
    output_dir = PROJECT_ROOT / storage.get('output_dir', 'output')
    audio_dir = PROJECT_ROOT / storage.get('audio_dir', 'output/audio')
    chapters_dir = output_dir / 'chapters'
    rss_feed_path = output_dir / 'feed.xml'
    logo_path = output_dir / 'logo.png'
    db_path = PROJECT_ROOT / config.get('database', {}).get('path', 'data/podcast.db')
    log_file = PROJECT_ROOT / config.get('logging', {}).get('file', 'logs/podcast_generator.log')

    db_tracker = ArticleTracker(str(db_path))
    generation_manager = GenerationManager(config_path, log_file)

    app = Flask(__name__, static_folder=str(SERVER_DIR / 'static'))
    app.config['PODCAST_CONFIG'] = config

    # --- Podcast app routes -------------------------------------------------

    @app.route('/feed.xml')
    def serve_feed():
        if not rss_feed_path.exists():
            return 'RSS feed not found', 404
        return send_file(rss_feed_path, mimetype='application/rss+xml')

    @app.route('/audio/<path:filename>')
    def serve_audio(filename):
        # send_from_directory blocks path traversal and supports range requests (seeking)
        return send_from_directory(audio_dir, filename)

    @app.route('/chapters/<path:filename>')
    def serve_chapters(filename):
        response = send_from_directory(chapters_dir, filename, mimetype='application/json+chapters')
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    @app.route('/logo.png')
    def serve_logo():
        if not logo_path.exists():
            return 'Logo not found', 404
        response = send_file(logo_path, mimetype=detect_image_type(logo_path))
        response.headers['Cache-Control'] = 'public, max-age=86400'
        return response

    # --- Web UI -------------------------------------------------------------

    @app.route('/')
    def index():
        return send_file(SERVER_DIR / 'templates' / 'index.html')

    # --- API ----------------------------------------------------------------

    @app.route('/api/episodes')
    def api_episodes():
        episodes = db_tracker.get_all_episodes()
        for ep in episodes:
            ep['audio_filename'] = os.path.basename(ep.get('audio_file') or '')
            ep['chapters_filename'] = os.path.basename(ep['chapters_file']) if ep.get('chapters_file') else None
        return jsonify(episodes)

    @app.route('/api/episodes/<episode_id>/chapters')
    def api_episode_chapters(episode_id):
        chapters_file = chapters_dir / f"{episode_id}_chapters.json"
        if not EPISODE_ID_PATTERN.fullmatch(episode_id) or not chapters_file.exists():
            return jsonify({'chapters': []})
        try:
            with open(chapters_file, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except (json.JSONDecodeError, OSError):
            return jsonify({'chapters': []})

    @app.route('/api/episodes/<episode_id>/articles')
    def api_episode_articles(episode_id):
        if not EPISODE_ID_PATTERN.fullmatch(episode_id):
            return jsonify([])
        fields = ('title', 'url', 'summary', 'original_content')
        articles = db_tracker.get_episode_articles(episode_id)
        return jsonify([{key: article.get(key) for key in fields} for article in articles])

    @app.route('/api/stats')
    def api_stats():
        return jsonify(db_tracker.get_statistics())

    @app.route('/api/generate', methods=['POST'])
    def api_generate():
        data = request.get_json(force=True, silent=True) or {}
        date_str = data.get('date') or ''
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'message': 'Ungültiges oder fehlendes Datum (YYYY-MM-DD)'}), 400

        success, message = generation_manager.start(date_str)
        return jsonify({'success': success, 'message': message}), 200 if success else 409

    @app.route('/api/generate/status')
    def api_generate_status():
        return jsonify({
            'running': generation_manager.running,
            'date': generation_manager.current_date,
            'exit_code': generation_manager.exit_code,
        })

    @app.route('/api/generate/logs')
    def api_generate_logs():
        return Response(generation_manager.stream_logs(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    return app


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(config_path: Optional[Path] = None):
    """Start the server (blocks until Ctrl+C)."""
    app = create_app(config_path)
    server_config = app.config['PODCAST_CONFIG'].get('server', {})
    host = server_config.get('host', '0.0.0.0')
    port = server_config.get('port', 8080)
    address = server_config.get('public_ip') or 'localhost'

    logger.info("=" * 80)
    logger.info(f"Der KI-osk server listening on {host}:{port}")
    logger.info(f"Web player:   http://{address}:{port}/")
    logger.info(f"RSS feed URL: http://{address}:{port}/feed.xml  (add this to your podcast app)")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 80)

    app.run(host=host, port=port, threaded=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    run(os.environ.get('PODCAST_CONFIG'))
