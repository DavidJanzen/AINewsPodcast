#!/usr/bin/env python3
"""
Store the original article text for all articles in the database that don't have it yet.

The web player shows this text next to the AI summary. Articles processed by older
versions have no stored text; this script scrapes it from the-decoder.de.

Usage:
    python scripts/backfill_article_content.py [--config config/default_config.yaml]
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.article_tracker import ArticleTracker  # noqa: E402
from src.fetchers.article_scraper import ArticleScraper  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill original article text in the database")
    parser.add_argument('--config', default='config/default_config.yaml', help='Path to configuration file')
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    os.chdir(PROJECT_ROOT)
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    tracker = ArticleTracker(config.get('database', {}).get('path', 'data/podcast.db'))
    articles = [a for a in tracker.get_articles_without_content() if 'the-decoder.de' in a['url']]
    if not articles:
        print("No articles need backfilling.")
        return 0

    print(f"Found {len(articles)} articles to backfill.")
    scraper = ArticleScraper()  # waits between requests
    success = 0

    for i, article in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {article['title'][:60]}...")
        content = scraper.fetch_article_content(article['url'])
        if content and tracker.set_original_content(article['url'], content):
            success += 1
            print(f"  OK ({len(content)} chars)")
        else:
            print("  SKIPPED (no content found)")

    print(f"\nDone. Success: {success}, Failed: {len(articles) - success}, Total: {len(articles)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
