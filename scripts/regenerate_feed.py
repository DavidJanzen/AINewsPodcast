#!/usr/bin/env python3
"""
Rebuild output/feed.xml from all episodes stored in the database.

Usage:
    python scripts/regenerate_feed.py [--config config/default_config.yaml]
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.main import PodcastWorkflow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the podcast RSS feed from the database")
    parser.add_argument('--config', default='config/default_config.yaml', help='Path to configuration file')
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    os.chdir(PROJECT_ROOT)

    workflow = PodcastWorkflow(str(config_path))
    if not workflow.generate_rss_feed():
        print("ERROR: Failed to regenerate the RSS feed, see logs/podcast_generator.log")
        return 1

    print(f"RSS feed regenerated: {workflow.rss_feed_path}")
    print(f"Feed URL: {workflow.rss_generator.base_url}/feed.xml")
    return 0


if __name__ == '__main__':
    sys.exit(main())
