"""
RSS Feed Generator Module

Builds a podcast RSS 2.0 feed with iTunes and Podcasting 2.0 extensions.
"""

import html
import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Dict, List
from xml.etree import ElementTree as ET


logger = logging.getLogger(__name__)

AUDIO_MIME_TYPES = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.ogg': 'audio/ogg'}


def _rfc2822(dt: datetime) -> str:
    """Format a datetime for RSS. Naive datetimes are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class RSSFeedGenerator:
    """Generates podcast RSS feed XML from episode data."""

    def __init__(self, config: Dict):
        podcast_config = config.get('podcast', {})
        server_config = config.get('server', {})

        self.title = podcast_config.get('title', 'Der KI-osk')
        self.description = podcast_config.get('description', '')
        self.author = podcast_config.get('author', 'AI Podcast Generator')
        self.email = podcast_config.get('email', 'podcast@localhost')
        self.language = podcast_config.get('language', 'de')
        self.category = podcast_config.get('category', 'Technology')
        self.copyright = podcast_config.get('copyright', str(datetime.now().year))
        self.explicit = podcast_config.get('explicit', False)

        # Public address used in all feed links (audio, chapters, logo)
        address = server_config.get('public_ip') or server_config.get('host', 'localhost')
        self.base_url = f"http://{address}:{server_config.get('port', 8080)}"
        self.image_url = podcast_config.get('image_url') or f"{self.base_url}/logo.png"

        logger.info(f"RSSFeedGenerator initialized with base URL: {self.base_url}")

    def generate_feed(self, episodes: List[Dict]) -> ET.ElementTree:
        """Build the RSS feed tree for the given episodes."""
        logger.info(f"Generating RSS feed for {len(episodes)} episodes")

        rss = ET.Element('rss', {
            'version': '2.0',
            'xmlns:itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
            'xmlns:content': 'http://purl.org/rss/1.0/modules/content/',
            'xmlns:podcast': 'https://podcastindex.org/namespace/1.0',
        })
        channel = ET.SubElement(rss, 'channel')
        self._add_channel_metadata(channel)

        for episode in episodes:
            self._add_episode_item(channel, episode)

        tree = ET.ElementTree(rss)
        ET.indent(tree, space='  ')
        return tree

    def save_feed(self, episodes: List[Dict], output_file: str) -> bool:
        """Generate the feed and write it to output_file."""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.generate_feed(episodes).write(output_path, encoding='utf-8', xml_declaration=True)
            logger.info(f"Saved RSS feed to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving RSS feed: {e}", exc_info=True)
            return False

    def _add_channel_metadata(self, channel: ET.Element):
        def add(tag: str, text: str = None, **attrs) -> ET.Element:
            elem = ET.SubElement(channel, tag, attrs)
            if text is not None:
                elem.text = text
            return elem

        add('title', self.title)
        add('description', self.description)
        add('link', self.base_url)
        add('language', self.language)
        add('copyright', self.copyright)
        add('lastBuildDate', _rfc2822(datetime.now(timezone.utc)))
        add('itunes:author', self.author)
        add('itunes:summary', self.description)
        add('itunes:explicit', 'true' if self.explicit else 'false')
        ET.SubElement(channel, 'itunes:category', {'text': self.category})

        owner = add('itunes:owner')
        ET.SubElement(owner, 'itunes:name').text = self.author
        ET.SubElement(owner, 'itunes:email').text = self.email

        add('itunes:image', href=self.image_url)
        image = add('image')
        ET.SubElement(image, 'url').text = self.image_url
        ET.SubElement(image, 'title').text = self.title
        ET.SubElement(image, 'link').text = self.base_url

    def _add_episode_item(self, channel: ET.Element, episode: Dict):
        try:
            item = ET.SubElement(channel, 'item')
            ET.SubElement(item, 'title').text = episode.get('title', 'Untitled Episode')

            base_description = episode.get('description', '') or ''
            article_links = episode.get('article_links') or []

            # Plain-text version (iTunes summary)
            plain = base_description
            if article_links:
                plain += "\n\n📰 Artikel-Links:\n" + "".join(
                    f"• {link.get('title', 'Artikel')}\n  {link.get('url', '')}\n" for link in article_links
                )
            ET.SubElement(item, 'itunes:summary').text = plain

            # HTML version (description). ElementTree escapes it, which is the
            # standard way to embed HTML in an RSS <description>.
            html_description = html.escape(base_description).replace('\n', '<br/>')
            if article_links:
                html_description += "<br/><br/>📰 <strong>Artikel-Links:</strong><br/>"
                for link in article_links:
                    title = html.escape(link.get('title', 'Artikel'))
                    url = html.escape(link.get('url', ''), quote=True)
                    html_description += f'<br/>➡️ <a href="{url}"><strong>{title}</strong></a><br/>'
            ET.SubElement(item, 'description').text = html_description

            # Publication date
            try:
                pub_dt = datetime.fromisoformat(episode.get('published_date', ''))
            except ValueError:
                pub_dt = datetime.now(timezone.utc)
            ET.SubElement(item, 'pubDate').text = _rfc2822(pub_dt)

            guid = ET.SubElement(item, 'guid', {'isPermaLink': 'false'})
            guid.text = episode.get('id', '')

            audio_file = episode.get('audio_file')
            if audio_file:
                audio_name = Path(audio_file).name
                ET.SubElement(item, 'enclosure', {
                    'url': f"{self.base_url}/audio/{audio_name}",
                    'type': AUDIO_MIME_TYPES.get(Path(audio_name).suffix.lower(), 'audio/wav'),
                    'length': str(episode.get('file_size_bytes') or 0),
                })

            duration = episode.get('duration_seconds')
            if duration:
                ET.SubElement(item, 'itunes:duration').text = _format_duration(duration)

            ET.SubElement(item, 'itunes:explicit').text = 'true' if self.explicit else 'false'

            chapters_file = episode.get('chapters_file')
            if chapters_file:
                ET.SubElement(item, 'podcast:chapters', {
                    'url': f"{self.base_url}/chapters/{Path(chapters_file).name}",
                    'type': 'application/json+chapters',
                })

        except Exception as e:
            logger.error(f"Error adding episode item {episode.get('id')}: {e}", exc_info=True)
