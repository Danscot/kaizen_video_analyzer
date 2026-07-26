# Kaizen Video Analyst

A Django-powered tool that decodes TikTok and short-form videos down to their DNA.
Upload a file or paste a URL and get back a structured breakdown of content strategy,
hooks, scenes, emotional arc, and frame-by-frame motion and design analysis — all
exportable as JSON or a detailed PDF brief.

---

## How it works

```
Video / Audio / URL
       |
       v
  [yt-dlp]           (URL input only — downloads video first)
       |
       v
  [ffmpeg]           (extracts 16 kHz mono WAV from video)
       |
  [Whisper]          (local speech-to-text — timestamped transcript)
       |
  [Gemini]           (content analysis: hooks, scenes, CTA, reproduction notes)
       |
       +---------> AnalysisJob saved to SQLite
       |
  [OpenCV]           (visual track — MAE frame diffing)
       |
  [Gemma 4 31B]      (per-frame vision: layout, colors, animation state, mood)
       |
  [Design Context]   (distils frames into color system, animation DNA, mood arc)
       |
       v
  JSON export  /  PDF Brief  /  Sidebar job history
```

---

## Project structure

```
kaizen_django/
├── manage.py
├── requirements.txt
├── deploy.sh                        # one-shot VPS setup
├── gunicorn.conf.py                 # production server config
├── kaizen.service                   # systemd unit file
├── nginx.conf                       # reverse proxy config
│
├── kaizen/                          # Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── analyser/                        # main Django app
│   ├── models.py                    # AnalysisJob model (SQLite, UUID PK)
│   ├── views.py                     # HTTP views: SSE streams, exports, API
│   ├── streaming.py                 # SSE generator pipelines
│   ├── urls.py                      # 8 routes
│   ├── migrations/
│   └── templates/analyser/
│       └── index.html               # full UI (no JS framework, no build step)
│
└── core/                            # AI engine — framework-agnostic
    ├── transcriber.py               # ffmpeg + Whisper
    ├── analyser.py                  # Gemini content analysis
    ├── frame_extractor.py           # OpenCV MAE frame diffing
    ├── visual_analyser.py           # Gemma vision batching with retry
    ├── design_context.py            # design context distiller
    ├── pdf_exporter.py              # ReportLab PDF brief generator
    └── utils.py                     # shared logging helpers
```

---

## API routes

| Method | URL | Description |
|--------|-----|-------------|
| GET  | `/` | Web UI |
| POST | `/analyse/content/` | SSE stream: Whisper + Gemini content analysis |
| POST | `/analyse/visual/` | SSE stream: OpenCV + Gemma visual analysis |
| POST | `/fetch-url/` | SSE stream: yt-dlp download then hand off to analysis |
| GET  | `/download/json/<uuid>/` | Download full result as JSON |
| GET  | `/download/pdf/<uuid>/` | Generate and download PDF brief |
| GET  | `/api/jobs/` | Last 50 jobs (sidebar history) |
| GET  | `/api/jobs/<uuid>/` | Full job detail (reload past results) |

---

## Requirements

**System packages**
```bash
# Ubuntu / Debian
sudo apt install ffmpeg python3 python3-pip python3-venv

# macOS
brew install ffmpeg
```

**Python packages** — installed via `requirements.txt`:
- `django` — web framework
- `whitenoise` — static file serving
- `gunicorn` — production WSGI server
- `google-genai` — Gemini / Gemma API
- `openai-whisper` — local speech-to-text
- `opencv-python-headless` — frame extraction
- `numpy`, `Pillow` — image processing
- `reportlab` — PDF generation
- `yt-dlp` — video download from URLs

---

## Local development

```bash
# 1. Clone / extract the project
cd kaizen_django

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export GEMINI_API_KEY=your_key_here
export DJANGO_DEBUG=true

# 5. Run migrations
python manage.py migrate

# 6. Start the dev server
python manage.py runserver

# Open http://127.0.0.1:8000
```

Get a free Gemini API key at https://aistudio.google.com/apikey

---

## Production deployment (Ubuntu 22.04 / 24.04)

The `deploy.sh` script handles everything in one shot:

```bash
# Copy the project to your server
scp -r kaizen_django/ user@your-vps:/tmp/

# SSH in and run deploy
ssh user@your-vps
cd /tmp/kaizen_django
sudo bash deploy.sh YOUR_GEMINI_API_KEY yourdomain.com
```

The script:
1. Installs `ffmpeg`, `nginx`, `python3`, `certbot` via apt
2. Creates `/opt/kaizen` and copies the project
3. Creates a Python virtual environment and installs all dependencies
4. Injects a generated `DJANGO_SECRET_KEY` and your `GEMINI_API_KEY`
5. Registers and starts the `kaizen.service` systemd unit
6. Configures and reloads nginx

**Add HTTPS after deploy:**
```bash
sudo certbot --nginx -d yourdomain.com
```

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | — | Google AI Studio API key |
| `DJANGO_SECRET_KEY` | Yes (prod) | insecure dev key | Long random string |
| `ALLOWED_HOSTS` | Yes (prod) | `localhost 127.0.0.1` | Space-separated hostnames |
| `DJANGO_DEBUG` | No | `false` | Set `true` for local dev only |

---

## Analysis tracks

### Content Analysis
Transcribes audio with Whisper then sends the transcript to Gemini for structured extraction of:
- Title, niche, platform style, duration estimate, language
- Summary and core message
- Target audience
- Hooks with timestamps and psychological technique breakdown
- Scene-by-scene breakdown with spoken content, tone, and B-roll suggestions
- Emotional journey arc
- Call to action
- Reproduction notes (tone guide, visual style, music, complexity)
- Keywords and topics

### Visual / Motion Analysis
Extracts visually distinct frames using OpenCV Mean Absolute Error diffing, sends them in batches to Gemma 4 vision, then distils the results into:
- Color system (primary background, text, accent, full palette)
- Typography DNA (dominant size, weight, heading/body hints)
- Animation DNA (steady / transition / enter percentages, dominant enter type)
- Layout patterns (dominant layout, focal point distribution)
- Emotional arc across frames
- Scene patterns per mood phase (layout, enter animation, focal position, avg text elements)
- Signature visual elements
- Design insights
- Planner context block (Markdown — ready to paste into a reproduction LLM prompt)

---

## Whisper model guide

| Model | Speed | Accuracy | VRAM needed |
|-------|-------|----------|-------------|
| tiny | Fastest | Lowest | ~1 GB |
| base | Fast | Good | ~1 GB |
| small | Medium | Better | ~2 GB |
| medium | Slow | Great | ~5 GB |
| large | Slowest | Best | ~10 GB |

`base` is the default and works well for most TikToks.
Use `small` or `medium` for heavy accents or noisy audio.

---

## Frame sensitivity guide

The **MAE threshold** slider in Visual Analysis controls how different two consecutive
frames must be before a new frame is captured.

| Value | Effect |
|-------|--------|
| 1–3 | Very sensitive — captures subtle cuts and text changes |
| 4–6 | Balanced — good for most TikToks (default: 5) |
| 7–10 | Coarse — only captures major scene changes |
| 11–15 | Very coarse — minimal frames, fastest analysis |

**Min Frame Gap** (default 30) prevents burst-capturing during fast motion by enforcing
a minimum number of frames between captures.

---

## PDF brief

The PDF export generates a dark-themed creative brief including all analysis data,
ready to hand to a writer or production team. It includes:
- Cover page with source, timestamp, and model info
- All content analysis sections (hooks, scenes, CTA, reproduction notes)
- Color swatches, animation DNA bars, scene pattern table
- Full transcript (capped at 120 lines)
- Planner context block

---

## Useful commands

```bash
# Check service status
systemctl status kaizen

# Live logs
journalctl -u kaizen -f

# Restart after code changes
systemctl restart kaizen

# Nginx reload after config change
nginx -t && systemctl reload nginx

# Django shell
cd /opt/kaizen
source venv/bin/activate
python manage.py shell

# View all past jobs
python manage.py shell -c "from analyser.models import AnalysisJob; [print(j) for j in AnalysisJob.objects.all()]"

# Run tests
python manage.py test
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Web framework | Django 5+ |
| WSGI server | Gunicorn |
| Reverse proxy | Nginx |
| Static files | WhiteNoise |
| Database | SQLite (single-file, zero config) |
| Transcription | OpenAI Whisper (runs locally) |
| Content AI | Google Gemini (gemini-2.5-flash default) |
| Vision AI | Google Gemma 4 31B (gemma-4-31b-it default) |
| Video download | yt-dlp |
| Frame extraction | OpenCV |
| PDF generation | ReportLab |
| Frontend | Vanilla JS + SSE (no build step, no framework) |
