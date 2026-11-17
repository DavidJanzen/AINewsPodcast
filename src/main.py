"""
Main Entry Point for Der KI-osk Podcast Generator

Workflow:
1. Fetch articles from the-decoder.de RSS feed
2. Track articles in SQLite to prevent duplicates
3. Select the articles of one day for a daily episode
4. Generate the podcast script with a local LLM (German)
5. Convert the script to speech with Qwen3-TTS voice cloning
6. Write chapter markers and the podcast RSS feed
7. Serve the RSS feed, audio files and web player via HTTP
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.article_tracker import ArticleTracker  # noqa: E402
from src.generators.chapters_generator import ChaptersGenerator  # noqa: E402
from src.generators.news_manager import NewsManager  # noqa: E402
from src.generators.podcast_generator import FALLBACK_OUTRO, PodcastGenerator, fallback_intro  # noqa: E402
from src.generators.rss_feed_generator import RSSFeedGenerator  # noqa: E402
from src.generators.tts_generator import TTSGenerator  # noqa: E402
from src.server import web_server  # noqa: E402


logger = logging.getLogger(__name__)


def setup_logging(config: Dict):
    """Log to the configured file and to stdout."""
    log_config = config.get('logging', {})
    log_file = Path(log_config.get('file', 'logs/podcast_generator.log'))
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, str(log_config.get('level', 'INFO')).upper(), logging.INFO),
        format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_config(config_path: str) -> Dict:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"Error loading config '{config_path}': {e}")
        sys.exit(1)


class PodcastWorkflow:
    """Orchestrates fetching, script generation, TTS, chapters and the RSS feed."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = load_config(config_path)
        setup_logging(self.config)

        logger.info("=" * 80)
        logger.info("Der KI-osk Podcast Generator - Starting")
        logger.info("=" * 80)

        storage = self.config.get('storage', {})
        self.rss_feed_path = Path(storage.get('output_dir', 'output')) / 'feed.xml'
        self.rss_feed_path.parent.mkdir(parents=True, exist_ok=True)

        self.db_tracker = ArticleTracker(self.config.get('database', {}).get('path', 'data/podcast.db'))
        self.news_manager = NewsManager(self.config, self.db_tracker)
        self.podcast_generator = PodcastGenerator(self.config)
        self.tts_generator = TTSGenerator(self.config)
        self.rss_generator = RSSFeedGenerator(self.config)
        self.chapters_generator = ChaptersGenerator(self.config)

    # -----------------------------------------------------------------------
    # Steps
    # -----------------------------------------------------------------------

    def validate_setup(self) -> bool:
        """Check the RSS feed, the LLM connection and the TTS engine."""
        logger.info("Validating setup...")

        if not self.news_manager.validate_feed():
            logger.error("RSS feed validation failed")
            return False

        if not self.podcast_generator.test_llm_connection():
            logger.error("LLM connection test failed. Is Ollama running? Start it with: ollama serve")
            logger.error(f"Ensure the model is available: ollama pull {self.podcast_generator.model}")
            return False

        if not self.tts_generator.test_tts_engine():
            logger.error("TTS engine test failed. Check the qwen-tts installation and tts.ref_audio / tts.ref_text")
            return False

        logger.info("Validation successful!")
        return True

    def fetch_and_store_articles(self) -> int:
        """Fetch articles from the RSS feed and store new ones. Returns the number of new articles."""
        return len(self.news_manager.fetch_new_articles())

    def generate_daily_episode(self, date: Optional[str] = None, force_regenerate: bool = False) -> Optional[str]:
        """
        Generate the episode for one day.

        Args:
            date: YYYY-MM-DD. Defaults to yesterday (the cron job runs early in the morning).
            force_regenerate: Delete an existing episode and regenerate it from all articles of that day

        Returns:
            Episode ID if successful, None otherwise
        """
        try:
            date = date or (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            episode_id = f"episode_{date}"
            logger.info(f"Generating daily episode for {date} (force_regenerate={force_regenerate})")

            # An existing episode is only replaced once the new audio was generated
            # successfully, so a failed regeneration keeps the old episode.
            articles = self.news_manager.get_articles_for_daily_episode(date, force_regenerate=force_regenerate)
            if not articles:
                logger.warning(f"No unprocessed articles for {date}")
                return None
            logger.info(f"Found {len(articles)} articles for episode")

            script = self.podcast_generator.generate_episode_script(articles, date)
            summaries = script['summaries']

            article_segments = [
                {'text': summaries[a['url']], 'title': a.get('title', 'Artikel'), 'url': a['url']}
                for a in articles if summaries.get(a['url'])
            ]
            if not article_segments:
                logger.error("No article summaries generated")
                return None

            if not self._produce_episode(episode_id, date, script['intro'], article_segments, script['outro']):
                return None

            self.news_manager.mark_articles_processed(
                articles=articles,
                episode_id=episode_id,
                summaries=summaries,
                original_contents=script['original_contents'],
            )
            return episode_id

        except Exception as e:
            logger.error(f"Error generating daily episode: {e}", exc_info=True)
            return None

    def regenerate_audio_only(self, date: str) -> Optional[str]:
        """
        Regenerate only the audio of an existing episode from the summaries stored in the database.
        The LLM is not used; intro and outro are fixed texts.
        """
        try:
            episode_id = f"episode_{date}"
            logger.info(f"TTS-only mode: regenerating audio for {episode_id}")

            articles = (self.db_tracker.get_episode_articles(episode_id)
                        or self.db_tracker.get_articles_by_date(date))
            articles = [a for a in articles if a.get('summary')]
            if not articles:
                logger.error(f"No stored summaries found for {date}. Run --generate first.")
                return None
            logger.info(f"Found {len(articles)} articles with existing summaries")

            article_segments = [
                {'text': a['summary'], 'title': a.get('title', 'Artikel'), 'url': a.get('url', '')}
                for a in articles
            ]

            if not self._produce_episode(episode_id, date, fallback_intro(len(articles)),
                                         article_segments, FALLBACK_OUTRO):
                return None
            return episode_id

        except Exception as e:
            logger.error(f"Error regenerating audio: {e}", exc_info=True)
            return None

    def generate_rss_feed(self) -> bool:
        """Write the RSS feed for all episodes in the database."""
        episodes = self.db_tracker.get_all_episodes()
        if not episodes:
            logger.warning("No episodes found in database")
            return False

        logger.info(f"Generating RSS feed for {len(episodes)} episodes")
        return self.rss_generator.save_feed(episodes, str(self.rss_feed_path))

    def start_server(self):
        """Serve the RSS feed, audio files and web player (blocks until Ctrl+C)."""
        try:
            web_server.run(self.config_path)
        except KeyboardInterrupt:
            logger.info("Server stopped by user")

    def run_once(self):
        """Fetch articles, generate yesterday's episode and update the feed."""
        self.fetch_and_store_articles()

        episode_id = self.generate_daily_episode()
        if episode_id:
            logger.info(f"Generated episode: {episode_id}")
        else:
            logger.info("No episode generated")

        self.generate_rss_feed()

        stats = self.db_tracker.get_statistics()
        logger.info("=" * 80)
        logger.info("Database Statistics:")
        logger.info(f"  Total articles:       {stats.get('total_articles', 0)}")
        logger.info(f"  Processed articles:   {stats.get('processed_articles', 0)}")
        logger.info(f"  Unprocessed articles: {stats.get('unprocessed_articles', 0)}")
        logger.info(f"  Total episodes:       {stats.get('total_episodes', 0)}")
        logger.info(f"  Total duration:       {stats.get('total_duration_seconds', 0) / 60:.1f} minutes")
        logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _produce_episode(self, episode_id: str, date: str, intro: str,
                         article_segments: List[Dict], outro: str) -> bool:
        """Generate audio + chapters for the segments and save the episode to the database."""
        segments = [{'text': intro, 'title': 'Intro'}, *article_segments, {'text': outro, 'title': 'Outro'}]

        logger.info("Generating audio with chapter markers...")
        tts_result = self.tts_generator.generate_speech_with_chapters(segments, f"{episode_id}.wav")
        if not tts_result:
            logger.error("Failed to generate audio")
            return False

        audio_path = tts_result['audio_path']
        duration = tts_result['duration']
        chapters_file = self.chapters_generator.generate_chapters_file(tts_result['chapters'], episode_id)

        titles = [segment['title'] for segment in article_segments]
        links = [{'title': segment['title'], 'url': segment.get('url', '')} for segment in article_segments]

        saved = self.db_tracker.add_episode(
            episode_id=episode_id,
            title=f"Tech News - {date}",
            description=f"Tech-News vom {date}:\n" + "\n".join(f"- {title}" for title in titles),
            published_date=f"{date}T12:00:00",
            audio_file=audio_path,
            duration=duration,
            article_count=len(article_segments),
            file_size=os.path.getsize(audio_path),
            article_links=json.dumps(links, ensure_ascii=False),
            chapters_file=chapters_file,
        )
        if saved:
            logger.info(f"Episode {episode_id} saved: {duration:.1f}s, {audio_path}")
        return saved


def valid_date(value: str) -> str:
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD")
    return value


def main():
    parser = argparse.ArgumentParser(description="Der KI-osk - German AI news podcast generator")
    parser.add_argument('--config', default='config/default_config.yaml', help='Path to configuration file')
    parser.add_argument('--validate', action='store_true', help='Validate RSS feed, LLM and TTS, then exit')
    parser.add_argument('--fetch', action='store_true', help='Fetch new articles')
    parser.add_argument('--generate', action='store_true',
                        help='Generate an episode (default: yesterday; with --date the episode is regenerated)')
    parser.add_argument('--server', action='store_true', help='Start the server (RSS feed, audio, web player)')
    parser.add_argument('--date', type=valid_date, help='Episode date (YYYY-MM-DD)')
    parser.add_argument('--tts-only', action='store_true', dest='tts_only',
                        help='Regenerate audio from stored summaries (skips the LLM, requires --date)')
    args = parser.parse_args()

    # All relative paths in the config are relative to the project root
    config_path = Path(args.config).resolve()
    os.chdir(PROJECT_ROOT)

    if args.tts_only and not args.date:
        parser.error("--tts-only requires --date YYYY-MM-DD")

    workflow = PodcastWorkflow(str(config_path))

    if args.validate:
        sys.exit(0 if workflow.validate_setup() else 1)

    if args.tts_only:
        success = workflow.regenerate_audio_only(args.date) is not None
        workflow.generate_rss_feed()
        sys.exit(0 if success else 1)

    if args.fetch or args.generate:
        success = True
        if args.fetch:
            workflow.fetch_and_store_articles()
        if args.generate:
            # With an explicit --date the episode is regenerated (overwritten)
            episode_id = workflow.generate_daily_episode(args.date, force_regenerate=args.date is not None)
            success = episode_id is not None
            workflow.generate_rss_feed()
        sys.exit(0 if success else 1)

    if args.server:
        workflow.start_server()
        return

    # Default: run once, then serve
    workflow.run_once()
    workflow.start_server()


if __name__ == '__main__':
    main()
