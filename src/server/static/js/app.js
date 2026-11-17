/* ============================================================
   Der KI-osk — Client-side Application
   ============================================================ */

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('page-' + btn.dataset.page).classList.add('active');
    });
});

// ---------------------------------------------------------------------------
// Episode Browser / Player
// ---------------------------------------------------------------------------

let episodes = [];
let currentEpisodeId = null;
const audioPlayer = document.getElementById('audio-player');

async function loadEpisodes() {
    try {
        const res = await fetch('/api/episodes');
        episodes = await res.json();
        renderEpisodeList();
    } catch (e) {
        document.getElementById('episode-list').innerHTML =
            '<div class="loading">Fehler beim Laden der Episoden</div>';
    }
}

function renderEpisodeList() {
    const list = document.getElementById('episode-list');
    if (!episodes.length) {
        list.innerHTML = '<div class="loading">Keine Episoden vorhanden</div>';
        return;
    }
    list.innerHTML = episodes.map(ep => {
        const date = ep.published_date ? ep.published_date.split('T')[0] : ep.id.replace('episode_', '');
        const duration = formatDuration(ep.duration_seconds);
        const active = ep.id === currentEpisodeId ? ' active' : '';
        return `
            <div class="episode-card${active}" data-id="${escapeHtml(ep.id)}">
                <div class="ep-date">${formatDate(date)}</div>
                <div class="ep-title">${escapeHtml(ep.title)}</div>
                <div class="ep-meta">
                    <span>${duration}</span>
                    <span>${ep.article_count || 0} Artikel</span>
                </div>
            </div>
        `;
    }).join('');
}

document.getElementById('episode-list').addEventListener('click', (event) => {
    const card = event.target.closest('.episode-card');
    if (card) playEpisode(card.dataset.id);
});

async function playEpisode(episodeId) {
    const ep = episodes.find(e => e.id === episodeId);
    if (!ep) return;

    currentEpisodeId = episodeId;
    renderEpisodeList();

    // Show player content
    const panel = document.getElementById('player-panel');
    panel.querySelector('.player-placeholder').style.display = 'none';
    panel.querySelector('.player-content').style.display = 'block';

    // Set title and meta
    const date = ep.published_date ? ep.published_date.split('T')[0] : ep.id.replace('episode_', '');
    document.getElementById('now-playing-title').textContent = ep.title;
    document.getElementById('now-playing-meta').textContent =
        `${formatDate(date)} — ${formatDuration(ep.duration_seconds)} — ${ep.article_count || 0} Artikel`;

    // Set audio source
    const audioFilename = ep.audio_filename || ep.id + '.wav';
    audioPlayer.src = '/audio/' + audioFilename;

    // Load chapters
    await loadChapters(episodeId);

    // Render article links
    renderArticleLinks(ep.article_links || []);

    // Load article comparison
    loadArticleComparison(episodeId);

    audioPlayer.play().catch(() => {});
}

let chapters = [];

async function loadChapters(episodeId) {
    const container = document.getElementById('chapter-list');
    chapters = [];
    try {
        const res = await fetch('/api/episodes/' + encodeURIComponent(episodeId) + '/chapters');
        const data = await res.json();
        chapters = data.chapters || [];
    } catch (e) {
        chapters = [];
    }

    if (!chapters.length) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = '<h3>Kapitel</h3>' + chapters.map((ch, i) => `
        <div class="chapter-item" data-index="${i}">
            <span class="chapter-time">${formatTime(ch.startTime)}</span>
            <span class="chapter-title">${escapeHtml(ch.title)}</span>
        </div>
    `).join('');
}

document.getElementById('chapter-list').addEventListener('click', (event) => {
    const item = event.target.closest('.chapter-item');
    const chapter = item && chapters[Number(item.dataset.index)];
    if (chapter) {
        audioPlayer.currentTime = chapter.startTime;
        audioPlayer.play().catch(() => {});
    }
});

// Highlight active chapter during playback
audioPlayer.addEventListener('timeupdate', () => {
    if (!chapters.length) return;
    const t = audioPlayer.currentTime;
    let activeIdx = 0;
    for (let i = chapters.length - 1; i >= 0; i--) {
        if (t >= chapters[i].startTime) {
            activeIdx = i;
            break;
        }
    }
    document.querySelectorAll('.chapter-item').forEach((el, i) => {
        el.classList.toggle('active-chapter', i === activeIdx);
    });
});

function renderArticleLinks(links) {
    const container = document.getElementById('article-links');
    if (!links || !links.length) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = '<h3>Artikel</h3>' + links.filter(l => isHttpUrl(l.url)).map(l =>
        `<a class="article-link" href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.title)}</a>`
    ).join('');
}

// ---------------------------------------------------------------------------
// Article Comparison
// ---------------------------------------------------------------------------

async function loadArticleComparison(episodeId) {
    const container = document.getElementById('article-comparison');
    container.innerHTML = '';
    try {
        const res = await fetch('/api/episodes/' + encodeURIComponent(episodeId) + '/articles');
        const articles = await res.json();
        if (!articles.length) return;

        let html = '<h3>Artikel &amp; Zusammenfassungen</h3>';
        articles.forEach((art, i) => {
            const hasOriginal = !!art.original_content;
            html += `
                <div class="comparison-card">
                    <div class="comparison-header" data-index="${i}">
                        <span class="comparison-toggle" id="toggle-icon-${i}">&#9654;</span>
                        <span class="comparison-title">${escapeHtml(art.title)}</span>
                    </div>
                    <div class="comparison-body" id="comparison-body-${i}" style="display:none;">
                        <div class="comparison-columns">
                            <div class="comparison-col">
                                <h4>Original-Artikel</h4>
                                <div class="comparison-text">${hasOriginal ? formatArticleText(art.original_content) : '<em>Originalartikel nicht verf\u00fcgbar</em>'}</div>
                            </div>
                            <div class="comparison-col">
                                <h4>KI-Zusammenfassung</h4>
                                <div class="comparison-text">${art.summary ? formatArticleText(art.summary) : '<em>Keine Zusammenfassung</em>'}</div>
                            </div>
                        </div>
                    </div>
                </div>`;
        });
        container.innerHTML = html;
    } catch (e) {
        // Ignore
    }
}

document.getElementById('article-comparison').addEventListener('click', (event) => {
    const header = event.target.closest('.comparison-header');
    if (header) toggleComparison(header.dataset.index);
});

function toggleComparison(index) {
    const body = document.getElementById('comparison-body-' + index);
    const icon = document.getElementById('toggle-icon-' + index);
    if (body.style.display === 'none') {
        body.style.display = 'block';
        icon.innerHTML = '&#9660;';
    } else {
        body.style.display = 'none';
        icon.innerHTML = '&#9654;';
    }
}

function formatArticleText(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
}

// ---------------------------------------------------------------------------
// Episode Generator
// ---------------------------------------------------------------------------

const selDay = document.getElementById('sel-day');
const selMonth = document.getElementById('sel-month');
const selYear = document.getElementById('sel-year');
const btnGenerate = document.getElementById('btn-generate');
const logOutput = document.getElementById('log-output');
const statusEl = document.getElementById('generation-status');
const statusText = document.getElementById('status-text');
const statusDot = statusEl.querySelector('.status-dot');

const MONTHS = [
    'Januar', 'Februar', 'M\u00e4rz', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
];

function initDateSelector() {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);

    const yNow = yesterday.getFullYear();
    const mNow = yesterday.getMonth(); // 0-based
    const dNow = yesterday.getDate();

    // Year: current year and previous
    selYear.innerHTML = '';
    for (let y = yNow; y >= yNow - 1; y--) {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y;
        selYear.appendChild(opt);
    }
    selYear.value = yNow;

    // Month
    selMonth.innerHTML = '';
    MONTHS.forEach((name, i) => {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = name;
        selMonth.appendChild(opt);
    });
    selMonth.value = mNow;

    // Days
    updateDays();
    selDay.value = dNow;

    selYear.addEventListener('change', updateDays);
    selMonth.addEventListener('change', updateDays);
}

function updateDays() {
    const y = parseInt(selYear.value);
    const m = parseInt(selMonth.value);
    const prevDay = selDay.value;
    const daysInMonth = new Date(y, m + 1, 0).getDate();

    selDay.innerHTML = '';
    for (let d = 1; d <= daysInMonth; d++) {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = String(d).padStart(2, '0');
        selDay.appendChild(opt);
    }

    // Restore previous day if still valid
    if (parseInt(prevDay) <= daysInMonth) {
        selDay.value = prevDay;
    }
}

function getSelectedDate() {
    const y = selYear.value;
    const m = String(parseInt(selMonth.value) + 1).padStart(2, '0');
    const d = String(selDay.value).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

let eventSource = null;

btnGenerate.addEventListener('click', startGeneration);

async function startGeneration() {
    const dateStr = getSelectedDate();

    btnGenerate.disabled = true;
    statusEl.style.display = 'flex';
    statusDot.className = 'status-dot';
    statusText.textContent = `Generierung f\u00fcr ${dateStr} l\u00e4uft...`;
    logOutput.innerHTML = '';

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: dateStr }),
        });
        const data = await res.json();

        if (!data.success) {
            statusDot.className = 'status-dot error';
            statusText.textContent = data.message || 'Fehler';
            btnGenerate.disabled = false;
            return;
        }

        attachLogStream();
    } catch (e) {
        statusDot.className = 'status-dot error';
        statusText.textContent = 'Netzwerkfehler: ' + e.message;
        btnGenerate.disabled = false;
    }
}

function attachLogStream() {
    eventSource = new EventSource('/api/generate/logs');

    eventSource.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.done) {
            eventSource.close();
            eventSource = null;
            const ok = msg.exit_code === 0;
            statusDot.className = 'status-dot ' + (ok ? 'done' : 'error');
            statusText.textContent = ok
                ? 'Generierung abgeschlossen!'
                : `Generierung fehlgeschlagen (Exit-Code: ${msg.exit_code})`;
            btnGenerate.disabled = false;
            loadEpisodes();
            loadStats();
            return;
        }
        if (msg.line !== undefined) {
            appendLogLine(msg.line);
        }
    };

    eventSource.onerror = () => {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        statusDot.className = 'status-dot error';
        statusText.textContent = 'Verbindung zum Log-Stream verloren';
        btnGenerate.disabled = false;
    };
}

function appendLogLine(line) {
    const span = document.createElement('span');
    if (line.includes('ERROR')) {
        span.className = 'log-error';
    } else if (line.includes('WARNING')) {
        span.className = 'log-warn';
    } else if (line.includes('INFO')) {
        span.className = 'log-info';
    } else {
        span.className = 'log-line';
    }
    span.textContent = line + '\n';
    logOutput.appendChild(span);
    logOutput.scrollTop = logOutput.scrollHeight;
}

document.getElementById('btn-clear-log').addEventListener('click', () => {
    logOutput.innerHTML = '';
});

// Check if a generation is already running on page load
async function checkGenerationStatus() {
    try {
        const res = await fetch('/api/generate/status');
        const data = await res.json();
        if (data.running) {
            btnGenerate.disabled = true;
            statusEl.style.display = 'flex';
            statusDot.className = 'status-dot';
            statusText.textContent = `Generierung f\u00fcr ${data.date} l\u00e4uft...`;

            attachLogStream();
        }
    } catch (e) {
        // Ignore
    }
}

// ---------------------------------------------------------------------------
// Stats (footer)
// ---------------------------------------------------------------------------

async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const stats = await res.json();
        const totalMin = Math.round((stats.total_duration_seconds || 0) / 60);
        document.getElementById('stats').textContent =
            `${stats.total_episodes || 0} Episoden \u2022 ${stats.total_articles || 0} Artikel \u2022 ${totalMin} Minuten Gesamtdauer`;
    } catch (e) {
        // Ignore
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(seconds) {
    const m = Math.floor((seconds || 0) / 60);
    const s = Math.floor((seconds || 0) % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
}

function formatDuration(seconds) {
    return seconds ? formatTime(seconds) : '--:--';
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    if (parts.length !== 3) return dateStr;
    const day = parseInt(parts[2]);
    const month = MONTHS[parseInt(parts[1]) - 1] || parts[1];
    return `${day}. ${month} ${parts[0]}`;
}

function isHttpUrl(url) {
    try {
        return ['http:', 'https:'].includes(new URL(url).protocol);
    } catch (e) {
        return false;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

initDateSelector();
loadEpisodes();
loadStats();
checkGenerationStatus();
