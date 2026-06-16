# KhmerFox

**Compact, fast, Cambodia-focused Google Maps scraper powered by Camoufox.**

Built for Khmer and English business listings. Small codebase, big features.

> ⚠️ **Safe use only.** This tool is intended for personal research, data you own, or publicly available listings you have permission to scrape. Always respect [Google Maps Terms of Service](https://www.google.com/intl/en/help/terms_maps.html), robots.txt, rate limits, and local laws. Use at your own risk.

---

## Features

- **Compact** — entire scraper in one `core.py` module
- **Fast** — async concurrent place extraction
- **Khmer-styled** — Cambodian flag theme, Noto Sans Khmer font, bilingual UI
- **Camoufox anti-detect** — stealth-hardened Firefox
- **Cambodia defaults** — Khmer query default, phone normalization, name splitting
- **Place IDs** — extracts `ChIJ...` Google Maps Place IDs
- **Coordinates** — latitude / longitude from Maps URLs
- **Export formats** — CSV (Excel-safe UTF-8 BOM), JSON, Markdown, Excel
- **Web UI** — single-file Flask app with live logs, progress, dark mode, and downloads
- **Proxy support** — HTTP/SOCKS5
- **Cross-platform** — Windows, macOS, and Linux

---

## Extracted Fields

`place_id`, `name`, `name_kh`, `name_en`, `rating`, `reviews`, `category`, `address`, `phone`, `website`, `hours`, `price_level`, `plus_code`, `latitude`, `longitude`, `maps_url`

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- ~2 GB free disk space for Camoufox browser binaries

Install `uv`:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## Install

```bash
git clone <repository-url>
cd khmerfox
uv sync
python -m camoufox fetch
```

`python -m camoufox fetch` downloads the Camoufox browser binaries for your platform (Windows, macOS, or Linux). Run it again after switching OS or after updating `camoufox`.

---

## CLI

```bash
# Default Khmer query: coffee shops in Phnom Penh
uv run khmerfox

# English query, all formats, 8 concurrent workers
uv run khmerfox -q "Tube Coffee in Phnom Penh" --format all --concurrency 8

# Excel only, max 50 places
uv run khmerfox -q "hotels in Siem Reap" --format xlsx --max-results 50

# Headed browser with screenshots for debugging
uv run khmerfox -q "banks in Phnom Penh" --no-headless --screenshots
```

### CLI options

| Option | Description |
|--------|-------------|
| `-q, --query` | Search query (default: `ហាងកាហ្វេនៅភ្នំពេញ`) |
| `-t, --territory` | Territory for phone normalization (default: `Cambodia`) |
| `--headless / --no-headless` | Run browser in headless mode (default: headless) |
| `--max-results` | Limit number of results, `0` = unlimited |
| `--concurrency` | Concurrent pages, `1`–`8` (default: `4`) |
| `--format` | `csv`, `json`, `md`, `xlsx`, comma-separated, or `all` |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--proxy` | HTTP/SOCKS5 proxy, e.g. `http://127.0.0.1:8080` |
| `--screenshots` | Save debug screenshots on errors |
| `--session` | Session name for Camoufox state |
| `--scroll-delay` | Seconds between scrolls in result list |
| `--page-delay` | Seconds between place page opens |
| `--retries` | Retries per failed place |

---

## Web UI

```bash
uv run khmerfox-web
```

Open http://127.0.0.1:5000

The web UI includes:
- Live progress bar and stats
- Color-coded logs with copy/clear
- Dark / light mode toggle
- Toast notifications
- One-click result downloads

---

## Project Structure

```
khmerfox/
├── khmerfox/
│   ├── __init__.py
│   ├── core.py      # models, scraper, extractor, exporter, utils
│   ├── cli.py       # command-line interface
│   └── web.py       # Flask app + embedded UI
├── data/            # output files (ignored by git except .gitkeep)
├── sessions/        # saved browser sessions (ignored by git except .gitkeep)
├── screenshots/     # debug screenshots (ignored by git except .gitkeep)
├── .env.example     # example environment variables
├── pyproject.toml   # project config
├── uv.lock          # locked dependencies
├── LICENSE          # MIT
└── README.md
```

---

## macOS Notes

1. Install `uv` using the command above.
2. On Apple Silicon (M1/M2/M3) or Intel, Camoufox will download the correct browser binary automatically when you run `python -m camoufox fetch`.
3. If you see a "developer cannot be verified" dialog from macOS, go to **System Settings → Privacy & Security → Security** and click **Allow Anyway** for the Camoufox/Playwright browser, or run:

   ```bash
   xattr -rd com.apple.quarantine ~/.cache/uv/
   ```

4. Use `uv run khmerfox` and `uv run khmerfox-web` exactly as on other platforms.

---

## Safe Usage & Rate Limits

- Keep `--concurrency` low (`2`–`4`) to avoid aggressive requests.
- Use `--proxy` to rotate IP addresses if you run repeated scrapes.
- Run with `--no-headless --screenshots` first to visually verify behavior.
- Do not scrape private or copyrighted data you are not authorized to access.
- Google Maps may block or CAPTCHA your IP if abused. KhmerFox provides no guarantee of uninterrupted access.

---

## Environment Variables

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

Supported variables: `QUERY`, `TERRITORY`, `HEADLESS`, `FORMAT`, `MAX_RESULTS`, `CONCURRENCY`, `PROXY`, `SCREENSHOTS`.

> Note: CLI flags override environment variables.

---

## Development

```bash
# Install dev dependencies
uv sync --dev

# Lint
uv run ruff check khmerfox/
```

---

## License

MIT — see [LICENSE](LICENSE).
