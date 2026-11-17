"""
Podcast Generator Module

Generates German podcast scripts (intro, article summaries, outro) with a local LLM via Ollama.
"""

import logging
import random
from typing import Dict, List, Optional

import requests

from ..fetchers.article_scraper import ArticleScraper


logger = logging.getLogger(__name__)

# Scraped articles shorter than this are still used, but logged as suspicious
SHORT_ARTICLE_CHARS = 500
SPOKEN_WORDS_PER_MINUTE = 150

DEFAULT_GREETING = "Willkommen im K-I-osk! Hey David, ich hoffe es ist alles o-KI bei dir."
FALLBACK_OUTRO = "Das waren die KI-News für heute aus dem K-I-osk. Bleib o-KI und bis zum nächsten Mal! Dein David."


def fallback_intro(article_count: int, greeting: str = DEFAULT_GREETING) -> str:
    """Intro used when the LLM is unavailable or skipped."""
    return f"{greeting} Heute gibt es wieder {article_count} spannende KI-News. Los geht's!"


class PodcastGenerator:
    """Generates podcast scripts from articles using a local LLM."""

    def __init__(self, config: Dict):
        self.config = config
        llm_config = config.get('llm', {})
        episode_config = config.get('episode', {})

        self.api_url = llm_config.get('api_url', 'http://localhost:11434/api/generate')
        self.model = llm_config.get('model', 'gpt-oss:20b')
        self.temperature = llm_config.get('temperature', 0.7)
        self.max_tokens = llm_config.get('max_tokens', -1)
        self.timeout = llm_config.get('timeout', 21600)
        self.system_prompt = llm_config.get('system_prompt', '')

        # Summary length as a percentage of the article length
        self.summary_percentage = episode_config.get('summary_percentage', 50)
        self.summary_tolerance = episode_config.get('summary_tolerance', 20)

        self.greetings = config.get('podcast', {}).get('greeting_variations') or [DEFAULT_GREETING]

        self.scraper = ArticleScraper()

        logger.info(f"PodcastGenerator initialized with model: {self.model}")
        logger.info(f"Timeout: {self.timeout}s, Summary: {self.summary_percentage}% "
                    f"±{self.summary_tolerance}% of article length")

    def generate_article_summary(self, article: Dict) -> Optional[Dict]:
        """
        Generate a podcast-style summary for a single article.

        Args:
            article: Article dictionary with 'title' and 'url' (the text is scraped from the url)

        Returns:
            Dict with 'summary' and 'original_content', or None if generation fails
        """
        try:
            title = article.get('title', '')
            url = article.get('url', '')

            logger.info(f"Generating summary for article: {title}")

            content = self.scraper.fetch_article_content(url) if 'the-decoder.de' in url else None
            if not content:
                logger.error(f"No article content available for: {title}")
                return None
            if len(content) < SHORT_ARTICLE_CHARS:
                logger.warning(f"Article text is short ({len(content)} characters), summary may be thin")

            # Target length derived from the article length
            article_word_count = len(content.split())
            target_words = int(article_word_count * self.summary_percentage / 100)
            tolerance_words = int(target_words * self.summary_tolerance / 100)
            min_words = target_words - tolerance_words
            max_words = target_words + tolerance_words
            target_minutes = target_words / SPOKEN_WORDS_PER_MINUTE

            logger.info(f"Article: {article_word_count} words → Target: {target_words} words "
                        f"({min_words}-{max_words} acceptable, {target_minutes:.1f} min)")

            prompt = f"""Erstelle eine ausführliche und detaillierte Podcast-Zusammenfassung für folgende KI-News auf Deutsch.

WICHTIG: Du bist David vom "K-I-osk" Podcast. Sprich den Hörer direkt an und erkläre die News so, als würdest du sie einem interessierten Freund erzählen.

Die Zusammenfassung MUSS:
- EXAKT ca. {target_words} Wörter lang sein ({target_minutes:.1f} Minuten Sprechzeit)
- ALLE wichtigen Informationen aus dem Artikel enthalten
- Technische Details präzise erklären
- Hintergründe, Kontext und Zusammenhänge ausführlich erläutern
- Mögliche Auswirkungen und Bedeutung für die KI-Branche diskutieren
- Konkrete Zahlen, Namen und Fakten aus dem Artikel nennen
- In natürlichem, gesprochenem Deutsch verfasst sein
- Unterhaltsam und verständlich geschrieben sein
- KEINE Überschriften, Aufzählungen oder Formatierungen enthalten
- Direkt mit dem Inhalt beginnen (NICHT mit "Willkommen" oder "Heute")

VERMEIDE:
- Zu kurze oder zu lange Zusammenfassungen - halte dich an ca. {target_words} Wörter!
- Nur den Titel zu wiederholen
- Oberflächliche Beschreibungen
- Abrupte Enden

Artikel:
Titel: {title}
Vollständiger Inhalt:
{content}

Ausführliche und detaillierte Zusammenfassung (ca. {target_words} Wörter):"""

            summary = self._generate_with_ollama(prompt)

            # Retry once if empty (a thinking model may have exhausted its token budget)
            if not summary:
                logger.warning(f"First attempt returned empty summary for: {title}, retrying...")
                summary = self._generate_with_ollama(prompt)

            if not summary:
                logger.error(f"Failed to generate summary for: {title}")
                return None

            word_count = len(summary.split())
            if not min_words <= word_count <= max_words:
                logger.warning(f"Summary outside tolerance ({word_count} words, "
                               f"acceptable: {min_words}-{max_words}), retrying")
                retry_prompt = (f"{prompt}\n\nDIESE ZUSAMMENFASSUNG HAT {word_count} WÖRTER! "
                                f"Schreibe eine Version mit ca. {target_words} Wörtern "
                                f"(zwischen {min_words} und {max_words} ist akzeptabel)!")
                retry_summary = self._generate_with_ollama(retry_prompt)
                if retry_summary:
                    summary = retry_summary
                    word_count = len(summary.split())
                else:
                    logger.warning("Retry failed, keeping the first summary")

            logger.info(f"Generated summary for: {title} ({word_count} words, target: {target_words})")
            return {'summary': summary.strip(), 'original_content': content}

        except Exception as e:
            logger.error(f"Error generating article summary: {e}", exc_info=True)
            return None

    def generate_episode_intro(self, date: str, article_count: int) -> str:
        """Generate the episode introduction (falls back to a fixed text)."""
        logger.info(f"Generating episode intro for {date}")
        greeting = random.choice(self.greetings)

        prompt = f"""Erstelle eine unterhaltsame Einleitung für den "K-I-osk" KI-News Podcast auf Deutsch.

Informationen:
- Datum: {date}
- Anzahl der KI-Nachrichten: {article_count}
- Podcast-Name: "K-I-osk" (gesprochen als "K-I-osk")
- Host: David
- Begrüßung: "{greeting}"

Die Einleitung sollte:
- Mit der vorgegebenen Begrüßung beginnen
- Dann kurz erwähnen: "Heute gibt es wieder {article_count} spannende KI-News."
- Maximal 40-50 Sekunden lang sein (ca. 80-100 Wörter)
- Enthusiastisch und persönlich klingen
- Kreative Wortspiele mit "KI" und "o-KI" nutzen
- Keine Überschriften enthalten
- In natürlichem Sprachstil

Einleitung:"""

        intro = self._generate_with_ollama(prompt)
        if intro:
            return intro.strip()

        logger.warning("Failed to generate intro, using fallback")
        return fallback_intro(article_count, greeting)

    def generate_episode_outro(self) -> str:
        """Generate the episode outro (falls back to a fixed text)."""
        logger.info("Generating episode outro")

        prompt = """Erstelle einen freundlichen, persönlichen Abschluss für den "K-I-osk" KI-News Podcast auf Deutsch.

Der Abschluss sollte:
- Maximal 30 Sekunden lang sein (ca. 60-80 Wörter)
- Den Hörer persönlich verabschieden
- Einen kreativen KI-Wortspiel-Abschiedsgruß enthalten (z.B. "Bleib o-KI", "Bis zum nächsten Mal im K-I-osk")
- Auf die nächste Folge hinweisen
- Warm und freundlich klingen
- Host ist David
- Keine Überschriften enthalten

Abschluss:"""

        outro = self._generate_with_ollama(prompt)
        if outro:
            return outro.strip()

        logger.warning("Failed to generate outro, using fallback")
        return FALLBACK_OUTRO

    def generate_episode_script(self, articles: List[Dict], date: str) -> Dict:
        """
        Generate the complete episode script.

        Returns:
            Dict with 'intro', 'summaries' (url → text), 'original_contents' (url → text) and 'outro'
        """
        logger.info(f"Generating complete episode script for {len(articles)} articles")

        intro = self.generate_episode_intro(date, len(articles))

        summaries: Dict[str, str] = {}
        original_contents: Dict[str, str] = {}
        for i, article in enumerate(articles, 1):
            logger.info(f"Processing article {i}/{len(articles)}")
            url = article['url']
            result = self.generate_article_summary(article)
            if result:
                summaries[url] = result['summary']
                if result.get('original_content'):
                    original_contents[url] = result['original_content']
            else:
                logger.warning(f"Using title as fallback for: {article.get('title')}")
                summaries[url] = article.get('title', '')

        outro = self.generate_episode_outro()

        logger.info("Successfully generated complete episode script")
        return {
            'intro': intro,
            'summaries': summaries,
            'original_contents': original_contents,
            'outro': outro,
        }

    def _generate_with_ollama(self, prompt: str) -> Optional[str]:
        """Send a prompt to the Ollama API and return the generated text (None on failure)."""
        payload = {
            'model': self.model,
            'prompt': prompt,
            'stream': False,
            'think': True,
            'options': {
                'temperature': self.temperature,
                'num_predict': self.max_tokens,
            },
        }
        if self.system_prompt:
            payload['system'] = self.system_prompt

        try:
            response = requests.post(self.api_url, json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout:
            logger.error("Ollama API request timeout")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to Ollama API. Is Ollama running?")
            return None

        if response.status_code != 200:
            logger.error(f"Ollama API error: {response.status_code} - {response.text}")
            return None

        try:
            result = response.json()
        except ValueError:
            logger.error("Ollama API returned invalid JSON")
            return None

        generated_text = result.get('response', '')
        thinking = result.get('thinking', '')
        done_reason = result.get('done_reason', '')

        if thinking:
            logger.info(f"LLM thinking length: {len(thinking)} chars")
        if done_reason == 'length':
            logger.warning("LLM stopped due to token limit - response may be truncated")
        if not generated_text and thinking:
            logger.warning("LLM produced thinking but no response (token budget exhausted)")

        return generated_text or None

    def test_llm_connection(self) -> bool:
        """Check that the LLM answers a trivial prompt."""
        logger.info("Testing LLM connection")
        if self._generate_with_ollama("Sage einfach 'Hallo' auf Deutsch."):
            logger.info("LLM connection test successful")
            return True
        logger.error("LLM connection test failed")
        return False
