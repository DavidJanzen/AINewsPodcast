"""
Text-to-Speech Generator Module

Converts German text to speech with Qwen3-TTS voice cloning.
A short reference recording plus its exact transcript defines the voice.
"""

import logging
import re
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


logger = logging.getLogger(__name__)

# Qwen3-TTS produces the best results with short inputs
MAX_CHUNK_CHARS = 500


def split_text_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """Split text into chunks at sentence boundaries, respecting max_chars."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks or [text]


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write a mono float waveform (-1.0 .. 1.0) as 16-bit PCM WAV."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


class TTSGenerator:
    """Generates German speech from text using Qwen3-TTS voice cloning."""

    def __init__(self, config: Dict):
        tts_config = config.get('tts', {})
        self.model_name = tts_config.get('model_name', 'Qwen/Qwen3-TTS-12Hz-1.7B-Base')
        self.device = tts_config.get('device', 'cpu')
        self.dtype = tts_config.get('dtype', 'float32')
        self.language = tts_config.get('language', 'German')
        self.ref_audio = Path(tts_config.get('ref_audio', 'voices/david.wav'))
        self.ref_text = tts_config.get('ref_text', '')

        self._model = None  # lazy-loaded on first use

        self.audio_dir = Path(config.get('storage', {}).get('audio_dir', 'output/audio'))
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"TTSGenerator initialized with Qwen3-TTS model: {self.model_name} ({self.device})")

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def generate_speech_with_chapters(self, segments: List[Dict], output_file: str) -> Optional[Dict]:
        """
        Generate one audio file from multiple segments and track chapter start times.

        Args:
            segments: List of dicts with 'text', 'title' and optional 'url'
            output_file: Output filename (relative to audio_dir)

        Returns:
            Dict with 'audio_path', 'chapters' and 'duration' (seconds), or None on failure
        """
        if not segments:
            logger.error("Cannot generate speech from empty segments")
            return None

        logger.info(f"Generating speech with chapters for {len(segments)} segments")

        parts: List[np.ndarray] = []
        chapters: List[Dict] = []
        sample_rate: Optional[int] = None
        current_time = 0.0

        for i, segment in enumerate(segments):
            text = segment.get('text', '')
            title = segment.get('title', f'Segment {i + 1}')
            if not text:
                logger.warning(f"Segment {i} ({title}) has no text, skipping")
                continue

            result = self._synthesize(text)
            if result is None:
                logger.error(f"Failed to generate audio for segment {i} ({title}), skipping")
                continue

            audio, sr = result
            if sample_rate is None:
                sample_rate = sr
            elif sr != sample_rate:
                logger.error(f"Segment {i} has sample rate {sr}, expected {sample_rate}, skipping")
                continue

            chapter = {'startTime': round(current_time, 3), 'title': title}
            if segment.get('url'):
                chapter['url'] = segment['url']
            chapters.append(chapter)

            duration = len(audio) / sr
            logger.info(f"Segment {i} ({title}): {duration:.1f}s, starts at {current_time:.1f}s")
            current_time += duration
            parts.append(audio)

        if not parts:
            logger.error("No audio segments generated")
            return None

        output_path = self.audio_dir / output_file
        write_wav(output_path, np.concatenate(parts), sample_rate)

        logger.info(f"Generated audio with {len(chapters)} chapters, total duration {current_time:.1f}s")
        return {
            'audio_path': str(output_path),
            'chapters': chapters,
            'duration': current_time,
        }

    def test_tts_engine(self) -> bool:
        """Check that Qwen3-TTS can load and synthesize a short sentence."""
        logger.info("Testing Qwen3-TTS")
        if self._synthesize("Dies ist ein Test.") is None:
            logger.error("TTS engine test failed")
            return False
        logger.info("TTS engine test successful")
        return True

    # -----------------------------------------------------------------------
    # Qwen3-TTS
    # -----------------------------------------------------------------------

    def _load_model(self):
        """Lazy-load the Qwen3-TTS model (cached after first use)."""
        if self._model is not None:
            return self._model

        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError:
            logger.error("qwen-tts is not installed. Install with: pip install -r requirements.txt")
            return None

        try:
            logger.info(f"Loading Qwen3-TTS model '{self.model_name}' on {self.device} (this may take a moment)...")
            self._model = Qwen3TTSModel.from_pretrained(
                self.model_name,
                device_map=self.device,
                dtype=getattr(torch, self.dtype, torch.float32),
            )
            logger.info("Qwen3-TTS model loaded successfully")
            return self._model
        except Exception as e:
            logger.error(f"Failed to load Qwen3-TTS model: {e}", exc_info=True)
            return None

    def _synthesize(self, text: str) -> Optional[Tuple[np.ndarray, int]]:
        """
        Synthesize text into a single waveform.

        Long text is split into sentence-based chunks which are generated
        one after another and joined in memory.

        Returns:
            (waveform, sample_rate) or None on failure
        """
        if not text or not text.strip():
            logger.error("Cannot generate speech from empty text")
            return None

        if not self.ref_audio.exists():
            logger.error(f"Reference audio not found: {self.ref_audio} (set tts.ref_audio in the config)")
            return None
        if not self.ref_text:
            logger.error("tts.ref_text is missing: it must contain the exact transcript of the reference audio")
            return None

        model = self._load_model()
        if model is None:
            return None

        chunks = split_text_into_chunks(text)
        if len(chunks) > 1:
            logger.info(f"Text ({len(text)} chars) split into {len(chunks)} chunks")

        parts: List[np.ndarray] = []
        sample_rate: Optional[int] = None
        try:
            for i, chunk in enumerate(chunks, 1):
                logger.debug(f"Generating chunk {i}/{len(chunks)} ({len(chunk)} chars)")
                wavs, sr = model.generate_voice_clone(
                    text=chunk,
                    language=self.language,
                    ref_audio=str(self.ref_audio),
                    ref_text=self.ref_text,
                )
                if sample_rate is None:
                    sample_rate = sr
                parts.append(np.asarray(wavs[0], dtype=np.float32).reshape(-1))
        except Exception as e:
            logger.error(f"Error generating speech with Qwen3-TTS: {e}", exc_info=True)
            return None

        return np.concatenate(parts), sample_rate
