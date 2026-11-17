"""
Chapters Generator Module

Writes Podcasting 2.0 chapter JSON files
(https://github.com/Podcastindex-org/podcast-namespace/blob/main/docs/1.0.md#chapters).
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)

CHAPTERS_VERSION = "1.2.0"


class ChaptersGenerator:
    """Generates Podcasting 2.0 chapter JSON files."""

    def __init__(self, config: Dict):
        output_dir = Path(config.get('storage', {}).get('output_dir', 'output'))
        self.chapters_dir = output_dir / 'chapters'
        self.chapters_dir.mkdir(parents=True, exist_ok=True)

    def generate_chapters_file(self, chapters: List[Dict], episode_id: str) -> Optional[str]:
        """
        Write <episode_id>_chapters.json.

        Args:
            chapters: Dicts with 'startTime' (seconds), 'title' and optional 'url' / 'img'
            episode_id: Episode ID used for the filename

        Returns:
            Path of the written file, or None if there are no chapters or writing fails
        """
        if not chapters:
            logger.error("Cannot generate chapters file from empty chapters list")
            return None

        entries = []
        for chapter in chapters:
            entry = {'startTime': chapter.get('startTime', 0.0)}
            entry.update({key: chapter[key] for key in ('title', 'url', 'img') if chapter.get(key)})
            entries.append(entry)

        chapters_path = self.chapters_dir / f"{episode_id}_chapters.json"
        try:
            with open(chapters_path, 'w', encoding='utf-8') as f:
                json.dump({'version': CHAPTERS_VERSION, 'chapters': entries}, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Error writing chapters file {chapters_path}: {e}")
            return None

        logger.info(f"Wrote chapters file with {len(entries)} markers: {chapters_path}")
        return str(chapters_path)
