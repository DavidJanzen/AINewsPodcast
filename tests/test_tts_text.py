import wave

import numpy as np

from src.generators.tts_generator import split_text_into_chunks, write_wav


def test_short_text_is_one_chunk():
    assert split_text_into_chunks("Hallo Welt. Wie geht's?") == ["Hallo Welt. Wie geht's?"]


def test_chunks_respect_max_length_and_sentence_boundaries():
    text = " ".join(f"Das ist Satz Nummer {i}." for i in range(50))
    chunks = split_text_into_chunks(text, max_chars=100)

    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert all(chunk.endswith('.') for chunk in chunks)
    assert " ".join(chunks) == text


def test_sentence_longer_than_limit_is_kept_whole():
    long_sentence = "A" * 150 + "."
    assert split_text_into_chunks(f"Kurz. {long_sentence}", max_chars=100) == ["Kurz.", long_sentence]


def test_write_wav_writes_16bit_mono(tmp_path):
    path = tmp_path / 'out.wav'
    write_wav(path, np.array([0.0, 0.5, -0.5, 2.0], dtype=np.float32), 24000)

    with wave.open(str(path), 'rb') as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24000
        frames = np.frombuffer(wav.readframes(4), dtype='<i2')
    assert frames.tolist() == [0, 16383, -16383, 32767]  # values above 1.0 are clipped
