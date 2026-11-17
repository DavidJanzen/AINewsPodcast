# Der KI-osk — Self-Hosted AI News Podcast Generator

> An end-to-end pipeline that turns a daily news feed into a fully produced, German-language audio podcast — running **100% locally**, with no cloud APIs, no subscriptions, and no data leaving the machine.

Every morning, a cron job fetches the latest AI articles, summarizes them with a local LLM in the voice of a podcast host, narrates the script with a cloned voice, packages it as an audio episode with chapter markers, and publishes a standards-compliant RSS feed that any podcast app (Apple Podcasts, Pocket Casts, AntennaPod, …) can subscribe to.

---

## Why this project matters

This is a complete, autonomous content-production system — not a script, but a **product**. It demonstrates the ability to design and ship a multi-stage data pipeline that integrates scraping, large language models, speech synthesis, persistence, and web delivery into a single hands-off workflow.

- **Privacy-first by design.** LLM inference, text-to-speech, storage, and serving all run on local hardware. Nothing is sent to third-party APIs.
- **Real ML integration, not just API calls.** It self-hosts a 20B-parameter LLM via Ollama and runs neural voice-cloning TTS (Qwen3-TTS) locally.
- **Fully autonomous.** A single cron entry produces a new episode every day with zero human input — fetch, dedupe, summarize, narrate, publish.
- **Production concerns handled.** Duplicate detection, persistence, length-calibrated summaries, chapter markers, RSS-spec compliance, logging, and a live monitoring UI.

---

## How it works

```
the-decoder.de RSS  ─▶  Article scraper  ─▶  SQLite tracker (dedup)
                                                     │
                                                     ▼
                                      Local LLM summarization (Ollama)
                                      "host-voice" scripting in German
                                                     │
                                                     ▼
                                     Local voice cloning (Qwen3-TTS)
                                                     │
                                                     ▼
                           WAV episode + chapter markers + RSS feed.xml
                                                     │
                                                     ▼
               Flask server: RSS feed + audio (podcast apps) + web player
```

1. **Fetch** — Pulls articles from the [the-decoder.de](https://the-decoder.de/) RSS feed. If the feed no longer contains a requested day, the article listing pages are scraped instead.
2. **Track** — Records every article in SQLite so nothing is processed twice; one episode is produced per day.
3. **Summarize** — A local LLM (default `gpt-oss:20b` via Ollama) rewrites each article into a German podcast segment whose length is a configurable percentage of the original article, plus a generated intro and outro.
4. **Narrate** — Qwen3-TTS converts the script to speech, cloning the host's voice from a short reference recording.
5. **Package** — Writes the episode as WAV plus a [Podcasting 2.0](https://podcastindex.org/namespace/1.0) chapter file, so listeners can jump between stories.
6. **Publish** — Builds an RSS feed with iTunes and Podcasting 2.0 tags and serves it, together with a web player, from one Flask server on the local network.

---

## Tech stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.10+ |
| **LLM inference** | [Ollama](https://ollama.com/) (self-hosted, default `gpt-oss:20b`) |
| **Text-to-Speech** | [Qwen3-TTS](https://huggingface.co/Qwen) voice cloning (`qwen-tts`, PyTorch) |
| **Data ingestion** | `feedparser` (RSS) · `requests` + `BeautifulSoup` (article scraping) |
| **Persistence** | SQLite (article tracking, summaries, episodes) |
| **Web server / API** | Flask (RSS feed, audio with range requests, chapters, web player, REST API, live log streaming via SSE) |
| **Frontend** | Vanilla HTML / CSS / JavaScript |
| **Configuration** | One YAML file (`config/default_config.yaml`) |
| **Automation** | cron |

### Project structure

```
config/default_config.yaml   all settings (LLM, voice, podcast metadata, ports)
src/main.py                  CLI entry point and workflow orchestration
src/fetchers/                RSS fetcher, article scraper, website listing fallback
src/database/                SQLite article/episode tracker
src/generators/              LLM script, Qwen3-TTS, chapters and RSS feed generation
src/server/                  Flask server: feed, audio, web player (+ static UI)
scripts/                     maintenance scripts (rebuild feed, backfill article text)
tests/                       pytest unit tests (no LLM, TTS or network needed)
voices/                      your reference recording for voice cloning (not in git)
data/, output/               database, audio, chapter files and feed (generated, not in git)
```

---

## Quick start

```bash
# 1. Local LLM
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull gpt-oss:20b

# 2. Python environment (installs PyTorch + qwen-tts)
./setup.sh
source venv/bin/activate

# 3. Configure: set server.public_ip to this machine's LAN address,
#    and tts.ref_audio / tts.ref_text for your voice recording
nano config/default_config.yaml

# 4. Validate, then generate yesterday's episode
python src/main.py --validate
python src/main.py --fetch --generate

# 5. Start the server
./START_SERVER.sh
```

| What | URL |
|---|---|
| Web player + episode generator | `http://<public_ip>:8080/` |
| RSS feed for podcast apps | `http://<public_ip>:8080/feed.xml` |

The server is reachable only from your local network.

### Command reference

```bash
python src/main.py                                # fetch + generate yesterday's episode, then start the server
python src/main.py --validate                     # check RSS feed, Ollama and Qwen3-TTS
python src/main.py --fetch                        # only fetch new articles
python src/main.py --fetch --generate             # generate yesterday's episode
python src/main.py --generate --date 2026-01-15   # (re)generate a specific day
python src/main.py --tts-only --date 2026-01-15   # re-record audio from stored summaries (no LLM)
python src/main.py --server                       # only start the server (feed, audio, web player)
python scripts/regenerate_feed.py                 # rebuild feed.xml from the database
```

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover text chunking, WAV output, website parsing, the database, article selection, chapter files, RSS feed XML and the Flask API. They use temporary databases and need no Ollama, GPU or network.

### Voice cloning

Record 10–30 seconds of clear speech without background noise, save it as WAV in `voices/`, and set in the config:

```yaml
tts:
  ref_audio: "voices/my_voice.wav"
  ref_text: "The exact words spoken in the recording."
```

`ref_text` must match the recording word for word. The Qwen3-TTS model is downloaded from HuggingFace on first use. On a CPU, generation is slow; set `device: "cuda"` and `dtype: "float16"` if you have a GPU.

### Daily automation

Add one line with `crontab -e` (adjust the path). Episodes are generated for the previous day:

```cron
0 3 * * * cd /path/to/AINewsPodcast && venv/bin/python src/main.py --fetch --generate >> logs/cron.log 2>&1
```

---

## Configuration

Everything lives in [`config/default_config.yaml`](config/default_config.yaml):

| Section | What it controls |
|---|---|
| `rss` | News source URL and number of articles per fetch |
| `episode` | Articles per episode, summary length (`summary_percentage`, `summary_tolerance`) |
| `llm` | Ollama model, temperature, timeout, host persona (`system_prompt`) |
| `tts` | Qwen3-TTS model, device, reference voice recording and transcript |
| `podcast` | Feed title, description, author, intro greetings |
| `server` | LAN address used in feed links, server port |
| `storage`, `logging` | Output folders and log file |

---

## License

[MIT](LICENSE)

---

*Built as a self-hosted, privacy-first demonstration of an end-to-end AI content pipeline — combining web scraping, local LLM inference, neural speech synthesis, and standards-based publishing into one autonomous system.*
