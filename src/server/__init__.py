"""Server package: Flask server for the RSS feed, audio files and web player."""

from .web_server import create_app, run

__all__ = ['create_app', 'run']
